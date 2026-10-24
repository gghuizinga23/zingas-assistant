#!/usr/bin/env python3
"""zingas-backup: Val's nightly backup. Plain code, no AI.

Runs on Val's computer under supervisord. Every night at 2:30 AM (Indianapolis)
it packs Val's vault, her settings, skills, brief schedules, chat history and
our programs into one file, locks it with a password (gpg, AES-256), and
uploads it to Backblaze B2. If Val's computer is off at 2:30 it runs as soon
as it is back. A failed try is tried again every 30 minutes.

Why it's safe:
  - Val's B2 key can only ADD files. It can't read, list or delete backups,
    so nothing on this computer can spoil or read an old backup.
  - The file is locked before it leaves. Backblaze only ever sees locked data.
  - Keys and passwords are never put in the backup; they live in 1Password.
  - Restoring needs a second, read-only B2 key that is NOT on this computer.

Keys (1Password, Zingas Assistant > Assistant Secrets):
  B2_KEY_ID, B2_APP_KEY   the add-files-only key
  BACKUP_PASSPHRASE       the lock password
  B2_BUCKET               optional, only if the key can see more than one bucket
  BACKUP_PING_URL         optional healthchecks.io check for the backup

  zingas-backup run       the loop (supervisord runs it)
  zingas-backup now       one backup right now
  zingas-backup check     pack, lock, unlock and compare on this computer; uploads nothing
  zingas-backup status    when the last good backup was
  zingas-backup restore --to DIR [--name NAME] [--compare] [--apply]
        reads 3 lines on stdin: restore key id, restore key, backup password
        (optional 4th line: bucket name). Never saved anywhere.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets as pysecrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

TZ = ZoneInfo("America/Indiana/Indianapolis") if ZoneInfo else timezone.utc
HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
VAULT = os.environ.get("ZINGAS_VAULT", "/root/Documents/ZingasVault")
OP_ENV = os.path.join(HERMES_HOME, ".op.env")
OP_ITEM = "op://Zingas Assistant/Assistant Secrets/"
STATE = os.path.join(HERMES_HOME, "backup-state.json")
NAME = os.environ.get("BACKUP_NAME", "val")       # one prefix per rep later
PREFIX = "nightly/"
AT_HOUR, AT_MINUTE = 2, 30
RETRY_MINUTES = 30
WAITING_MINUTES = 60
WARN_HOURS = 30
WAITING = "waiting for keys in 1Password"
UA = "zingas-backup/1.0"

# What goes in. Directories are walked; missing paths are skipped.
INCLUDE = [
    VAULT,
    os.path.join(HERMES_HOME, "SOUL.md"),
    os.path.join(HERMES_HOME, "config.yaml"),
    os.path.join(HERMES_HOME, "memories"),
    os.path.join(HERMES_HOME, "skills"),
    os.path.join(HERMES_HOME, "cron"),
    os.path.join(HERMES_HOME, "scripts"),
    os.path.join(HERMES_HOME, "hooks"),
    os.path.join(HERMES_HOME, "pairing"),
    os.path.join(HERMES_HOME, "sessions"),
    os.path.join(HERMES_HOME, "state.db"),
    os.path.join(HERMES_HOME, "kanban.db"),
    os.path.join(HERMES_HOME, "channel_directory.json"),
    os.path.join(HERMES_HOME, "inbox-state.json"),
    os.path.join(HERMES_HOME, "quo-pickup-state.json"),
    "/usr/local/lib/zingas",
    "/usr/local/bin/zingas-assistant-heartbeat",
    "/usr/local/bin/zingas-assistant-op-enable",
    "/usr/local/bin/zingas-backup",
    "/usr/local/bin/zingas-inbox",
    "/usr/local/bin/zingas-plaud",
    "/usr/local/bin/zingas-quo",
    "/usr/local/bin/zingas-todo",
    "/etc/supervisor/conf.d/zingas-backup.conf",
    "/etc/supervisor/conf.d/zingas-heartbeat.conf",
    "/etc/supervisor/conf.d/zingas-inbox.conf",
    "/etc/supervisor/conf.d/zingas-plaud.conf",
    "/etc/supervisor/conf.d/zingas-quo-pickup.conf",
]

# Never in the backup: keys and passwords (1Password has them), locks, caches.
SECRET_NAMES = {".env", ".op.env", "auth.json", "quo-bridge.env", "token.json", "tokens.json", "credentials.json"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def skipped(path: str) -> bool:
    base = os.path.basename(path)
    return (base in SECRET_NAMES or base.endswith(".env") or base.endswith(".lock")
            or base.endswith(".pyc") or base.startswith(".fire-"))


def is_sqlite(path: str) -> bool:
    if not path.endswith(".db"):
        return False
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def files_to_back_up(include: List[str]) -> List[str]:
    out: List[str] = []
    for root in include:
        if os.path.islink(root) or not os.path.exists(root):
            continue
        if os.path.isfile(root):
            if not skipped(root):
                out.append(root)
            continue
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not os.path.islink(os.path.join(d, x)))
            for f in sorted(files):
                p = os.path.join(d, f)
                if not os.path.islink(p) and os.path.isfile(p) and not skipped(p):
                    out.append(p)
    return out


def arcname(path: str) -> str:
    return os.path.abspath(path).lstrip("/")


def pack(include: List[str], out_path: str, work: str) -> Dict[str, int]:
    """Writes a .tar.gz of everything in `include`. Databases are copied safely first."""
    count = skipped_n = 0
    with tarfile.open(out_path, "w:gz", compresslevel=6) as tar:
        for p in files_to_back_up(include):
            src = p
            try:
                if is_sqlite(p):
                    src = os.path.join(work, "db-" + hashlib.sha1(p.encode()).hexdigest() + ".db")
                    live, copy = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30), sqlite3.connect(src)
                    try:
                        live.backup(copy)
                    finally:
                        live.close()
                        copy.close()
                    os.chmod(src, os.stat(p).st_mode & 0o777)
                tar.add(src, arcname=arcname(p), recursive=False)
                count += 1
            except (OSError, sqlite3.Error):
                skipped_n += 1     # a file that vanished or is busy; the next night gets it
            finally:
                if src != p and os.path.exists(src):
                    os.remove(src)
    return {"files": count, "skipped": skipped_n, "bytes": os.path.getsize(out_path)}


# ------------------------------------------------------------ the lock (gpg)

class LockError(RuntimeError):
    pass


def _gpg(args: List[str], passphrase: str) -> None:
    if not shutil.which("gpg"):
        raise LockError("gpg is not installed")
    home = tempfile.mkdtemp(prefix="zb-gpg-")
    try:
        r = subprocess.run(["gpg", "--homedir", home, "--batch", "--yes", "--quiet", "--no-tty",
                            "--pinentry-mode", "loopback", "--passphrase-fd", "0", *args],
                           input=passphrase + "\n", text=True, capture_output=True, timeout=600)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    if r.returncode != 0:
        msg = (r.stderr or "").strip().splitlines()
        raise LockError("gpg failed: " + (msg[-1] if msg else f"exit {r.returncode}"))


def lock(src: str, dst: str, passphrase: str) -> None:
    _gpg(["--symmetric", "--cipher-algo", "AES256", "--s2k-digest-algo", "SHA512",
          "--compress-algo", "none", "-o", dst, src], passphrase)


def unlock(src: str, dst: str, passphrase: str) -> None:
    _gpg(["--decrypt", "-o", dst, src], passphrase)


def safe_extract(tar_path: str, to: str) -> List[str]:
    """Unpacks only plain files and folders, never outside `to`."""
    os.makedirs(to, mode=0o700, exist_ok=True)
    top = os.path.realpath(to)
    names = []
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar.getmembers():
            target = os.path.realpath(os.path.join(top, m.name))
            if m.name.startswith("/") or ".." in m.name.split("/") or not (m.isfile() or m.isdir()) \
                    or not (target == top or target.startswith(top + os.sep)):
                raise LockError(f"refused an unsafe entry in the backup: {m.name!r}")
            m.mode &= 0o777
        for m in tar.getmembers():
            if m.isdir():
                os.makedirs(os.path.join(top, m.name), exist_ok=True)
                continue
            dst = os.path.join(top, m.name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with tar.extractfile(m) as fh, open(dst, "wb") as out:  # type: ignore[union-attr]
                shutil.copyfileobj(fh, out)
            os.chmod(dst, m.mode or 0o600)
            os.utime(dst, (m.mtime, m.mtime))
            names.append(m.name)
    return names


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(path: str) -> str:
    """Databases are compared by their data; a safe copy is never byte-for-byte the same file."""
    if is_sqlite(path):
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
            try:
                h = hashlib.sha256()
                for line in con.iterdump():
                    h.update(line.encode() + b"\n")
                return "db:" + h.hexdigest()
            finally:
                con.close()
        except sqlite3.Error:
            pass
    return sha256(path)


def compare(restored: str, live_root: str = "/") -> Dict[str, List[str]]:
    same, changed, gone = [], [], []
    for d, _, files in os.walk(restored):
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, restored)
            live = os.path.join(live_root, rel)
            if not os.path.isfile(live):
                gone.append(rel)
            elif content_hash(live) == content_hash(p):
                same.append(rel)
            else:
                changed.append(rel)
    return {"same": sorted(same), "changed": sorted(changed), "missing_now": sorted(gone)}


# ------------------------------------------------------------ Backblaze B2

class B2Error(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"B2 {status}: {message}")
        self.status = status


class B2:
    """The few B2 calls we need, with plain urllib. Val's key: add files only."""

    API = "https://api.backblazeb2.com"

    def __init__(self, key_id: str, key: str, bucket: str = "", api: str = API, timeout: float = 120.0):
        self.key_id, self.key, self.bucket_name, self.api, self.timeout = key_id, key, bucket, api, timeout
        self.token = self.api_url = self.download_url = self.bucket_id = self.account = ""

    def _call(self, method: str, url: str, headers: Dict[str, str], data=None) -> bytes:
        req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **headers})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("message") or e.reason
            except ValueError:
                msg = e.reason
            raise B2Error(e.code, str(msg)) from None
        except (urllib.error.URLError, OSError) as e:
            raise B2Error(0, f"could not reach Backblaze ({e})") from None

    def _json(self, path: str, body: dict) -> dict:
        out = self._call("POST", f"{self.api_url}/b2api/v3/{path}",
                         {"Authorization": self.token, "Content-Type": "application/json"},
                         json.dumps(body).encode())
        return json.loads(out)

    def authorize(self) -> None:
        basic = base64.b64encode(f"{self.key_id}:{self.key}".encode()).decode()
        j = json.loads(self._call("GET", f"{self.api}/b2api/v3/b2_authorize_account",
                                  {"Authorization": "Basic " + basic}))
        s = j.get("apiInfo", {}).get("storageApi", {})
        self.token, self.account = j["authorizationToken"], j.get("accountId", "")
        self.api_url, self.download_url = s["apiUrl"], s["downloadUrl"]
        allowed = s.get("allowed") or {}
        buckets = [b for b in (allowed.get("buckets") or []) if b.get("id")]
        if not buckets and allowed.get("bucketId"):
            buckets = [{"id": allowed["bucketId"], "name": allowed.get("bucketName", "")}]
        if self.bucket_name:
            match = [b for b in buckets if b.get("name") == self.bucket_name]
            if match:
                buckets = match
            elif not buckets:
                found = self._json("b2_list_buckets", {"accountId": self.account, "bucketName": self.bucket_name})
                buckets = [{"id": b["bucketId"], "name": b["bucketName"]} for b in found.get("buckets", [])]
            else:
                raise B2Error(0, f"this key can't reach the bucket {self.bucket_name!r}")
        if len(buckets) != 1:
            raise B2Error(0, "make the key for one bucket only (or save B2_BUCKET in 1Password)")
        self.bucket_id, self.bucket_name = buckets[0]["id"], buckets[0].get("name") or self.bucket_name

    def upload(self, name: str, path: str, tries: int = 3) -> dict:
        digest = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        sha1, size = digest.hexdigest(), os.path.getsize(path)
        last: Optional[B2Error] = None
        for n in range(tries):
            up = self._json("b2_get_upload_url", {"bucketId": self.bucket_id})
            try:
                with open(path, "rb") as fh:
                    out = json.loads(self._call("POST", up["uploadUrl"], {
                        "Authorization": up["authorizationToken"],
                        "X-Bz-File-Name": urllib.parse.quote(name, safe="/"),
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(size),
                        "X-Bz-Content-Sha1": sha1,
                    }, fh))
            except B2Error as e:       # B2 asks clients to get a fresh upload link and try again
                last = e
                if e.status not in (0, 408, 429, 500, 503) or n == tries - 1:
                    raise
                time.sleep(2 * (n + 1))
                continue
            if out.get("contentSha1") not in (sha1, None):
                raise B2Error(0, "Backblaze got a different file than we sent")
            return out
        raise last or B2Error(0, "upload failed")

    def names(self, prefix: str = PREFIX) -> List[str]:
        out, start = [], None
        while True:
            body = {"bucketId": self.bucket_id, "prefix": prefix, "maxFileCount": 1000}
            if start:
                body["startFileName"] = start
            j = self._json("b2_list_file_names", body)
            out += [f["fileName"] for f in j.get("files", []) if f.get("action", "upload") == "upload"]
            start = j.get("nextFileName")
            if not start:
                return sorted(out)

    def download(self, name: str, dest: str) -> None:
        url = f"{self.download_url}/file/{urllib.parse.quote(self.bucket_name)}/{urllib.parse.quote(name, safe='/')}"
        req = urllib.request.Request(url, headers={"Authorization": self.token, "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r, open(dest, "wb") as out:
                shutil.copyfileobj(r, out)
        except urllib.error.HTTPError as e:
            raise B2Error(e.code, str(e.reason)) from None
        except (urllib.error.URLError, OSError) as e:
            raise B2Error(0, f"could not reach Backblaze ({e})") from None


# ------------------------------------------------------------ keys, state, ping

def op_read(name: str) -> str:
    token = ""
    try:
        with open(OP_ENV) as fh:
            for line in fh:
                if line.startswith("OP_SERVICE_ACCOUNT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    except OSError:
        return ""
    if not token:
        return ""
    env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=token)
    try:
        out = subprocess.run(["op", "read", OP_ITEM + name], env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


KEY_NAMES = ("B2_KEY_ID", "B2_APP_KEY", "BACKUP_PASSPHRASE", "B2_BUCKET", "BACKUP_PING_URL")


def read_keys(reader: Callable[[str], str] = op_read) -> Dict[str, str]:
    return {k: reader(k) for k in KEY_NAMES}


def load_state(path: str = STATE) -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: str = STATE) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def ping(url: str, fail: bool = False, note: str = "") -> None:
    if not url.startswith("https://"):
        return
    req = urllib.request.Request(url.rstrip("/") + ("/fail" if fail else ""), data=note.encode()[:2000],
                                 method="POST", headers={"User-Agent": UA})
    try:
        urllib.request.urlopen(req, timeout=15).close()
    except (urllib.error.URLError, OSError):
        log("healthchecks ping failed")


def _when(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def tonight_slot(now: datetime) -> datetime:
    local = now.astimezone(TZ)
    return local.replace(hour=AT_HOUR, minute=AT_MINUTE, second=0, microsecond=0)


def due(state: dict, now: datetime) -> bool:
    last_ok, last_try = _when(state.get("last_ok", "")), _when(state.get("last_try", ""))
    if last_try and (not last_ok or last_try > last_ok):
        gap = WAITING_MINUTES if state.get("last_error") == WAITING else RETRY_MINUTES
        if now - last_try < timedelta(minutes=gap):
            return False
    if last_ok is None:
        return True
    slot = tonight_slot(now)
    return now >= slot and last_ok < slot


def brief_line(state: dict, now: datetime) -> str:
    """One warning line for the brief, or "" when backups are fine (or not set up yet)."""
    err = state.get("last_error", "")
    last_ok = _when(state.get("last_ok", ""))
    if err == WAITING and not last_ok:
        return ""
    if last_ok and now - last_ok < timedelta(hours=WARN_HOURS):
        return ""
    if not last_ok and not err:
        return ""
    when = last_ok.astimezone(TZ).strftime("%A %-I:%M %p") if last_ok else "never"
    return f"BACKUP WARNING: last good backup {when}." + (f" Problem: {err}" if err else "")


# ------------------------------------------------------------ one backup

def backup_once(keys: Dict[str, str], now: Optional[datetime] = None, include: Optional[List[str]] = None,
                state_path: str = STATE, b2_factory: Callable[..., B2] = B2) -> dict:
    now = now or datetime.now(TZ)
    state = load_state(state_path)
    state["last_try"] = now.isoformat(timespec="seconds")
    if not (keys.get("B2_KEY_ID") and keys.get("B2_APP_KEY") and keys.get("BACKUP_PASSPHRASE")):
        state["last_error"] = WAITING
        save_state(state, state_path)
        log("no backup: " + WAITING)
        return state
    name = f"{PREFIX}{NAME}-{now.astimezone(TZ):%Y-%m-%d-%H%M}.tar.gz.gpg"
    work = tempfile.mkdtemp(prefix="zb-")
    try:
        raw, locked, back = (os.path.join(work, x) for x in ("b.tar.gz", "b.tar.gz.gpg", "check.tar.gz"))
        info = pack(include if include is not None else INCLUDE, raw, work)
        lock(raw, locked, keys["BACKUP_PASSPHRASE"])
        unlock(locked, back, keys["BACKUP_PASSPHRASE"])    # prove it opens before it leaves
        if sha256(back) != sha256(raw):
            raise LockError("the locked file didn't open back to the same data")
        b2 = b2_factory(keys["B2_KEY_ID"], keys["B2_APP_KEY"], keys.get("B2_BUCKET", ""))
        b2.authorize()
        b2.upload(name, locked)
        state.update(last_ok=now.isoformat(timespec="seconds"), last_ok_name=name,
                     last_ok_bytes=os.path.getsize(locked), last_ok_files=info["files"], last_error="")
        save_state(state, state_path)
        log(f"backup ok: {name} ({info['files']} files, {os.path.getsize(locked)} bytes, {info['skipped']} skipped)")
        ping(keys.get("BACKUP_PING_URL", ""), note=f"{name} {info['files']} files")
    except (B2Error, LockError, OSError, tarfile.TarError) as e:
        state["last_error"] = str(e)[:300]
        save_state(state, state_path)
        log(f"backup FAILED: {state['last_error']}")
        ping(keys.get("BACKUP_PING_URL", ""), fail=True, note=state["last_error"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return state


def self_check(include: Optional[List[str]] = None, live_root: str = "/") -> dict:
    """Pack, lock with a throwaway password, unlock, unpack and compare. Uploads nothing."""
    work = tempfile.mkdtemp(prefix="zb-check-")
    try:
        raw, locked, back = (os.path.join(work, x) for x in ("b.tar.gz", "b.gpg", "back.tar.gz"))
        pw = pysecrets.token_urlsafe(24)
        info = pack(include if include is not None else INCLUDE, raw, work)
        lock(raw, locked, pw)
        try:
            unlock(locked, back, "wrong-" + pw)
            wrong_pw_refused = False
        except LockError:
            wrong_pw_refused = True
        unlock(locked, back, pw)
        names = safe_extract(back, os.path.join(work, "out"))
        cmp_ = compare(os.path.join(work, "out"), live_root)
        leaked = [n for n in names if os.path.basename(n) in SECRET_NAMES or n.endswith(".env")]
        return {"files": info["files"], "locked_bytes": os.path.getsize(locked), "restored": len(names),
                "same": len(cmp_["same"]), "changed": cmp_["changed"], "missing_now": cmp_["missing_now"],
                "wrong_password_refused": wrong_pw_refused, "secrets_in_backup": leaked}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def restore(key_id: str, key: str, passphrase: str, to: str, bucket: str = "", name: str = "",
            do_compare: bool = False, apply: bool = False, b2_factory: Callable[..., B2] = B2,
            live_root: str = "/") -> dict:
    b2 = b2_factory(key_id, key, bucket)
    b2.authorize()
    all_names = b2.names(PREFIX)
    if not all_names:
        raise B2Error(0, "no backups found in the bucket")
    pick = name or all_names[-1]
    if pick not in all_names:
        raise B2Error(404, f"no backup named {pick!r}")
    work = tempfile.mkdtemp(prefix="zb-restore-")
    try:
        locked, raw = os.path.join(work, "b.gpg"), os.path.join(work, "b.tar.gz")
        b2.download(pick, locked)
        unlock(locked, raw, passphrase)
        names = safe_extract(raw, to)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = {"backup": pick, "backups_in_bucket": len(all_names), "restored_files": len(names), "to": to}
    if do_compare:
        c = compare(to, live_root)
        out.update(same=len(c["same"]), changed=c["changed"], missing_now=c["missing_now"])
    if apply:
        for n in names:
            dst = os.path.join(live_root, n)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(to, n), dst)
        out["applied"] = len(names)
    return out


# ------------------------------------------------------------ main

def run_loop() -> None:
    log("zingas-backup started; nightly at 2:30 AM Indianapolis")
    while True:
        now = datetime.now(TZ)
        if due(load_state(), now):
            backup_once(read_keys(), now)
        time.sleep(300)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="zingas-backup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("now")
    sub.add_parser("check")
    sub.add_parser("status")
    r = sub.add_parser("restore")
    r.add_argument("--to", required=True)
    r.add_argument("--name", default="")
    r.add_argument("--compare", action="store_true")
    r.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        run_loop()
    elif a.cmd == "now":
        st = backup_once(read_keys())
        return 0 if not st.get("last_error") else 1
    elif a.cmd == "check":
        res = self_check()
        print(json.dumps({**res, "changed": res["changed"][:20], "missing_now": res["missing_now"][:20]}, indent=1))
        return 0 if res["wrong_password_refused"] and not res["secrets_in_backup"] and res["restored"] == res["files"] else 1
    elif a.cmd == "status":
        st = load_state()
        print(json.dumps({k: st.get(k, "") for k in ("last_ok", "last_ok_name", "last_ok_bytes", "last_ok_files",
                                                       "last_try", "last_error")}, indent=1))
        line = brief_line(st, datetime.now(TZ))
        print(line or "Backups look fine (or are waiting for keys).")
    elif a.cmd == "restore":
        lines = [l.strip() for l in sys.stdin.read().splitlines()]
        if len(lines) < 3 or not all(lines[:3]):
            print("restore needs 3 lines on stdin: key id, key, backup password")
            return 2
        try:
            res = restore(lines[0], lines[1], lines[2], a.to, bucket=lines[3] if len(lines) > 3 else "",
                          name=a.name, do_compare=a.compare, apply=a.apply)
        except (B2Error, LockError) as e:
            print(f"Restore stopped: {e}")
            return 1
        if "changed" in res:
            res["changed"] = res["changed"][:30]
            res["missing_now"] = res["missing_now"][:30]
        print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
