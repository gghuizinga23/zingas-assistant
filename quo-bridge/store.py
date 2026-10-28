"""Where quo-bridge keeps its records.

SupabaseStore talks to the tables in schema.sql over Supabase's REST API
(standard library only). MemoryStore does the same in memory, for tests.
Both keep timestamps as ISO 8601 strings in UTC, so they sort as text.

claim_draft() is how two copies of the helper never act on one draft twice:
it changes a draft only if its status is still one of the expected ones, in
one database step, and returns the changed row (or None if someone else got
there first).
"""

from __future__ import annotations

import copy
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

FINISHED = ("sent", "skipped", "stopped", "blocked", "paused", "expired", "stopped_customer",
            "replaced", "own")      # replaced/own: Gerrit texted the customer himself in the Quo app


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


_FRACTION = re.compile(r"\.(\d+)")


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """Read a timestamp from either store. Python 3.9's fromisoformat wants
    exactly 3 or 6 fraction digits and no 'Z', so normalize first."""
    if not value:
        return None
    v = value.replace("Z", "+00:00").replace(" ", "T")
    v = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], v, count=1)
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class MemoryStore:
    def __init__(self):
        self.messages: Dict[str, dict] = {}
        self.drafts: Dict[str, dict] = {}
        self.calls: Dict[str, dict] = {}
        self.contacts: Dict[str, dict] = {}
        self.stats: Dict[str, dict] = {}
        self.events: List[dict] = []
        self.batches: Dict[str, dict] = {}

    # messages
    def add_message(self, row: dict) -> bool:
        if row["id"] in self.messages:
            return False
        self.messages[row["id"]] = dict(row, picked_at=row.get("picked_at"))
        return True

    def unpicked_messages(self, limit: int = 20) -> List[dict]:
        rows = [m for m in self.messages.values() if m["direction"] == "in" and not m.get("picked_at")]
        return copy.deepcopy(sorted(rows, key=lambda m: m["created_at"])[:limit])

    def ack_messages(self, ids: Iterable[str], at: str) -> None:
        for i in ids:
            if i in self.messages and not self.messages[i].get("picked_at"):
                self.messages[i]["picked_at"] = at

    def recent_messages(self, phone: str, limit: int = 10) -> List[dict]:
        rows = sorted((m for m in self.messages.values() if m["phone"] == phone),
                      key=lambda m: m["created_at"])
        return copy.deepcopy(rows[-limit:])

    def get_message(self, msg_id: str) -> Optional[dict]:
        m = self.messages.get(msg_id)
        return copy.deepcopy(m) if m else None

    def latest_inbound(self, phone: str) -> Optional[dict]:
        rows = [m for m in self.messages.values() if m["phone"] == phone and m["direction"] == "in"]
        return copy.deepcopy(max(rows, key=lambda m: m["created_at"])) if rows else None

    # calls
    def add_call(self, row: dict) -> bool:
        if row["id"] in self.calls:
            return False
        self.calls[row["id"]] = dict(row, picked_at=row.get("picked_at"))
        return True

    def unpicked_calls(self, limit: int = 20) -> List[dict]:
        rows = [c for c in self.calls.values() if not c.get("picked_at")]
        return copy.deepcopy(sorted(rows, key=lambda c: c["created_at"])[:limit])

    def ack_calls(self, ids: Iterable[str], at: str) -> None:
        for i in ids:
            if i in self.calls and not self.calls[i].get("picked_at"):
                self.calls[i]["picked_at"] = at

    def get_call(self, call_id: str) -> Optional[dict]:
        c = self.calls.get(call_id)
        return copy.deepcopy(c) if c else None

    # drafts
    def insert_draft(self, row: dict) -> None:
        self.drafts[row["id"]] = copy.deepcopy(row)

    def get_draft(self, draft_id: str) -> Optional[dict]:
        d = self.drafts.get(draft_id)
        return copy.deepcopy(d) if d else None

    def claim_draft(self, draft_id: str, from_statuses: Iterable[str], fields: dict,
                    require_null: Optional[str] = None) -> Optional[dict]:
        d = self.drafts.get(draft_id)
        if not d or d["status"] not in tuple(from_statuses):
            return None
        if require_null and d.get(require_null):
            return None
        d.update(fields)
        return copy.deepcopy(d)

    def update_draft(self, draft_id: str, fields: dict) -> None:
        if draft_id in self.drafts:
            self.drafts[draft_id].update(fields)

    def drafts_by_status(self, statuses: Iterable[str], limit: int = 100) -> List[dict]:
        wanted = tuple(statuses)
        rows = [d for d in self.drafts.values() if d["status"] in wanted]
        return copy.deepcopy(sorted(rows, key=lambda d: d["created_at"])[:limit])

    def find_draft_by_prompt(self, prompt_id: int) -> Optional[dict]:
        for d in self.drafts.values():
            if d.get("tg_prompt_id") == prompt_id:
                return copy.deepcopy(d)
        return None

    def unreported_outcomes(self, limit: int = 20, category: Optional[str] = None,
                            exclude_category: Optional[str] = None) -> List[dict]:
        rows = [d for d in self.drafts.values() if d["status"] in FINISHED and not d.get("reported_at")
                and (category is None or d["category"] == category)
                and (exclude_category is None or d["category"] != exclude_category)]
        return copy.deepcopy(sorted(rows, key=lambda d: d["created_at"])[:limit])

    def insert_draft_if_new(self, row: dict) -> bool:
        if row["id"] in self.drafts:
            return False
        self.drafts[row["id"]] = copy.deepcopy(row)
        return True

    def drafts_in_batch(self, batch_id: str) -> List[dict]:
        rows = [d for d in self.drafts.values() if d.get("batch_id") == batch_id]
        return copy.deepcopy(sorted(rows, key=lambda d: (d.get("due_at") or "", d["id"])))

    def followups_for(self, statuses: Iterable[str], phone: str = "", email: str = "") -> List[dict]:
        wanted = tuple(statuses)
        rows = [d for d in self.drafts.values() if d["category"] == "followup" and d["status"] in wanted
                and ((phone and d["phone"] == phone) or (email and (d.get("email_to") or "").lower() == email))]
        return copy.deepcopy(rows)

    def latest_outbound(self, phone: str) -> Optional[dict]:
        rows = [m for m in self.messages.values() if m["phone"] == phone and m["direction"] == "out"]
        return copy.deepcopy(max(rows, key=lambda m: m["created_at"])) if rows else None

    def messages_for_phones(self, phones: Iterable[str], limit: int = 2000) -> List[dict]:
        want = set(phones)
        rows = sorted((m for m in self.messages.values() if m["phone"] in want),
                      key=lambda m: m["created_at"], reverse=True)
        return copy.deepcopy(rows[:limit])

    def dnc_phones(self, phones: Iterable[str]) -> List[str]:
        return [p for p in phones if self.is_dnc(p)]

    def get_batch(self, batch_id: str) -> Optional[dict]:
        b = self.batches.get(batch_id)
        return dict(b) if b else None

    def save_batch(self, batch_id: str, fields: dict) -> None:
        self.batches.setdefault(batch_id, {"id": batch_id}).update(fields)

    def mark_reported(self, ids: Iterable[str], at: str) -> None:
        for i in ids:
            d = self.drafts.get(i)
            if d and d["status"] in FINISHED and not d.get("reported_at"):
                d["reported_at"] = at

    # contacts, stats, log
    def is_dnc(self, phone: str) -> bool:
        return bool(self.contacts.get(phone, {}).get("do_not_contact"))

    def set_dnc(self, phone: str, flag: bool, at: str) -> None:
        self.contacts[phone] = {"phone": phone, "do_not_contact": flag, "updated_at": at}

    def get_stats(self, category: str) -> dict:
        return dict(self.stats.get(category, {"category": category, "streak": 0, "enabled": False}))

    def save_stats(self, category: str, streak: int, enabled: bool) -> None:
        self.stats[category] = {"category": category, "streak": streak, "enabled": enabled}

    def log(self, kind: str, draft_id: Optional[str], detail: str, at: str) -> None:
        self.events.append({"at": at, "kind": kind, "draft_id": draft_id, "detail": detail})

    def last_event_at(self, kind: str) -> Optional[str]:
        return max((e["at"] for e in self.events if e["kind"] == kind), default=None)

    def log_many(self, rows: List[dict]) -> None:
        self.events.extend(dict(r) for r in rows)

    def events_since(self, since: str, limit: int = 500) -> List[dict]:
        rows = [(parse_time(e["at"]), n, e) for n, e in enumerate(self.events) if parse_time(e["at"]) >= parse_time(since)]
        return [{"at": e["at"], "kind": e["kind"], "detail": e.get("detail")}
                for _, _, e in sorted(rows, key=lambda r: r[:2], reverse=True)[:limit]]

    def recent_events(self, kind: str, limit: int = 10) -> List[dict]:
        rows = [(parse_time(e["at"]), n, e) for n, e in enumerate(self.events) if e["kind"] == kind]
        return [{"at": e["at"], "detail": e.get("detail")} for _, _, e in sorted(rows, key=lambda r: r[:2],
                                                                                 reverse=True)[:limit]]

    def last_event(self, kind: str, detail_prefix: str = "") -> Optional[dict]:
        rows = [(parse_time(e["at"]), n, e) for n, e in enumerate(self.events)
                if e["kind"] == kind and (e.get("detail") or "").startswith(detail_prefix)]
        if not rows:
            return None
        e = max(rows, key=lambda r: r[:2])[2]     # newest; of two at the same moment, the one written last
        return {"at": e["at"], "detail": e.get("detail")}

    # cost count (cost_count.py)
    def sent_drafts_since(self, since: str) -> List[dict]:
        rows = [{k: d.get(k) for k in ("phone", "body", "final_body", "sent_at")} for d in self.drafts.values()
                if d.get("sent_at") and parse_time(d["sent_at"]) >= parse_time(since)]
        return sorted(rows, key=lambda d: d["sent_at"])


class StoreError(RuntimeError):
    pass


def _q(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _in_list(values: Iterable[str]) -> str:
    # PostgREST list syntax: in.("a","b"), percent-encoded for the URL.
    return "in." + _q("(" + ",".join('"' + str(v).replace('"', "") + '"' for v in values) + ")")


class SupabaseStore:
    def __init__(self, url: str, service_key: str, timeout: float = 10.0):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.key = service_key
        self.timeout = timeout

    def _call(self, method: str, path: str, body=None, prefer: str = "") -> list:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if not self.key.startswith("sb_"):
            # Older service_role keys are JWTs and go in both headers. Newer
            # sb_secret_ keys go only in apikey; Supabase rejects them as a Bearer.
            headers["Authorization"] = "Bearer " + self.key
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise StoreError(f"Supabase {method} {path.split('?')[0]}: HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise StoreError(f"Supabase {method} {path.split('?')[0]}: {e}") from None
        return json.loads(raw) if raw else []

    # messages
    def add_message(self, row: dict) -> bool:
        out = self._call("POST", "messages?on_conflict=id", [row],
                         prefer="resolution=ignore-duplicates,return=representation")
        return bool(out)

    def unpicked_messages(self, limit: int = 20) -> List[dict]:
        return self._call("GET", f"messages?direction=eq.in&picked_at=is.null&order=created_at.asc&limit={int(limit)}")

    def ack_messages(self, ids: Iterable[str], at: str) -> None:
        ids = list(ids)
        if ids:
            self._call("PATCH", f"messages?id={_in_list(ids)}&picked_at=is.null", {"picked_at": at},
                       prefer="return=minimal")

    def recent_messages(self, phone: str, limit: int = 10) -> List[dict]:
        rows = self._call("GET", f"messages?phone=eq.{_q(phone)}&order=created_at.desc&limit={int(limit)}")
        return list(reversed(rows))

    def get_message(self, msg_id: str) -> Optional[dict]:
        rows = self._call("GET", f"messages?id=eq.{_q(msg_id)}&limit=1")
        return rows[0] if rows else None

    def latest_inbound(self, phone: str) -> Optional[dict]:
        rows = self._call("GET", f"messages?phone=eq.{_q(phone)}&direction=eq.in&order=created_at.desc&limit=1")
        return rows[0] if rows else None

    # calls
    def add_call(self, row: dict) -> bool:
        out = self._call("POST", "calls?on_conflict=id", [row],
                         prefer="resolution=ignore-duplicates,return=representation")
        return bool(out)

    def unpicked_calls(self, limit: int = 20) -> List[dict]:
        return self._call("GET", f"calls?picked_at=is.null&order=created_at.asc&limit={int(limit)}")

    def ack_calls(self, ids: Iterable[str], at: str) -> None:
        ids = list(ids)
        if ids:
            self._call("PATCH", f"calls?id={_in_list(ids)}&picked_at=is.null", {"picked_at": at},
                       prefer="return=minimal")

    def get_call(self, call_id: str) -> Optional[dict]:
        rows = self._call("GET", f"calls?id=eq.{_q(call_id)}&limit=1")
        return rows[0] if rows else None

    # drafts
    def insert_draft(self, row: dict) -> None:
        self._call("POST", "drafts", [row], prefer="return=minimal")

    def get_draft(self, draft_id: str) -> Optional[dict]:
        rows = self._call("GET", f"drafts?id=eq.{_q(draft_id)}&limit=1")
        return rows[0] if rows else None

    def claim_draft(self, draft_id: str, from_statuses: Iterable[str], fields: dict,
                    require_null: Optional[str] = None) -> Optional[dict]:
        path = f"drafts?id=eq.{_q(draft_id)}&status={_in_list(from_statuses)}"
        if require_null:
            path += f"&{require_null}=is.null"
        rows = self._call("PATCH", path, fields, prefer="return=representation")
        return rows[0] if rows else None

    def update_draft(self, draft_id: str, fields: dict) -> None:
        self._call("PATCH", f"drafts?id=eq.{_q(draft_id)}", fields, prefer="return=minimal")

    def drafts_by_status(self, statuses: Iterable[str], limit: int = 100) -> List[dict]:
        return self._call("GET", f"drafts?status={_in_list(statuses)}&order=created_at.asc&limit={int(limit)}")

    def find_draft_by_prompt(self, prompt_id: int) -> Optional[dict]:
        rows = self._call("GET", f"drafts?tg_prompt_id=eq.{int(prompt_id)}&limit=1")
        return rows[0] if rows else None

    def unreported_outcomes(self, limit: int = 20, category: Optional[str] = None,
                            exclude_category: Optional[str] = None) -> List[dict]:
        path = f"drafts?status={_in_list(FINISHED)}&reported_at=is.null"
        if category:
            path += f"&category=eq.{_q(category)}"
        if exclude_category:
            path += f"&category=neq.{_q(exclude_category)}"
        return self._call("GET", path + f"&order=created_at.asc&limit={int(limit)}")

    def insert_draft_if_new(self, row: dict) -> bool:
        out = self._call("POST", "drafts?on_conflict=id", [row],
                         prefer="resolution=ignore-duplicates,return=representation")
        return bool(out)

    def drafts_in_batch(self, batch_id: str) -> List[dict]:
        return self._call("GET", f"drafts?batch_id=eq.{_q(batch_id)}&order=due_at.asc,id.asc&limit=200")

    def followups_for(self, statuses: Iterable[str], phone: str = "", email: str = "") -> List[dict]:
        rows: List[dict] = []
        base = f"drafts?category=eq.followup&status={_in_list(statuses)}"
        if phone:
            rows += self._call("GET", base + f"&phone=eq.{_q(phone)}")
        if email:
            seen = {r["id"] for r in rows}
            rows += [r for r in self._call("GET", base + f"&email_to=eq.{_q(email.lower())}") if r["id"] not in seen]
        return rows

    def latest_outbound(self, phone: str) -> Optional[dict]:
        rows = self._call("GET", f"messages?phone=eq.{_q(phone)}&direction=eq.out&order=created_at.desc&limit=1")
        return rows[0] if rows else None

    def messages_for_phones(self, phones: Iterable[str], limit: int = 2000) -> List[dict]:
        phones = list(phones)
        if not phones:
            return []
        return self._call("GET", f"messages?phone={_in_list(phones)}&order=created_at.desc&limit={int(limit)}")

    def dnc_phones(self, phones: Iterable[str]) -> List[str]:
        phones = list(phones)
        if not phones:
            return []
        rows = self._call("GET", f"contacts?phone={_in_list(phones)}&do_not_contact=is.true&select=phone")
        return [r["phone"] for r in rows]

    def get_batch(self, batch_id: str) -> Optional[dict]:
        rows = self._call("GET", f"batches?id=eq.{_q(batch_id)}&limit=1")
        return rows[0] if rows else None

    def save_batch(self, batch_id: str, fields: dict) -> None:
        self._call("POST", "batches?on_conflict=id", [dict(fields, id=batch_id)],
                   prefer="resolution=merge-duplicates,return=minimal")

    def mark_reported(self, ids: Iterable[str], at: str) -> None:
        ids = list(ids)
        if ids:
            self._call("PATCH", f"drafts?id={_in_list(ids)}&status={_in_list(FINISHED)}&reported_at=is.null",
                       {"reported_at": at}, prefer="return=minimal")

    # contacts, stats, log
    def is_dnc(self, phone: str) -> bool:
        rows = self._call("GET", f"contacts?phone=eq.{_q(phone)}&select=do_not_contact&limit=1")
        return bool(rows and rows[0].get("do_not_contact"))

    def set_dnc(self, phone: str, flag: bool, at: str) -> None:
        self._call("POST", "contacts?on_conflict=phone",
                   [{"phone": phone, "do_not_contact": flag, "updated_at": at}],
                   prefer="resolution=merge-duplicates,return=minimal")

    def get_stats(self, category: str) -> dict:
        rows = self._call("GET", f"auto_send_stats?category=eq.{_q(category)}&limit=1")
        return rows[0] if rows else {"category": category, "streak": 0, "enabled": False}

    def save_stats(self, category: str, streak: int, enabled: bool) -> None:
        self._call("POST", "auto_send_stats?on_conflict=category",
                   [{"category": category, "streak": streak, "enabled": enabled}],
                   prefer="resolution=merge-duplicates,return=minimal")

    def log(self, kind: str, draft_id: Optional[str], detail: str, at: str) -> None:
        self._call("POST", "events", [{"at": at, "kind": kind, "draft_id": draft_id, "detail": detail[:2000]}],
                   prefer="return=minimal")

    def last_event_at(self, kind: str) -> Optional[str]:
        rows = self._call("GET", f"events?kind=eq.{_q(kind)}&select=at&order=at.desc&limit=1")
        return rows[0]["at"] if rows else None

    def log_many(self, rows: List[dict]) -> None:
        self._call("POST", "events", [{"at": r["at"], "kind": r["kind"], "draft_id": r.get("draft_id"),
                                       "detail": (r.get("detail") or "")[:2000]} for r in rows],
                   prefer="return=minimal")

    def events_since(self, since: str, limit: int = 500) -> List[dict]:
        return self._call("GET", f"events?at=gte.{_q(since)}&select=at,kind,detail&order=at.desc&limit={int(limit)}")

    def recent_events(self, kind: str, limit: int = 10) -> List[dict]:
        return self._call("GET", f"events?kind=eq.{_q(kind)}&select=at,detail&order=at.desc&limit={int(limit)}")

    def last_event(self, kind: str, detail_prefix: str = "") -> Optional[dict]:
        like = ""
        if detail_prefix:   # PostgREST's like: * is any text. Characters LIKE treats specially match any one.
            like = "&detail=like." + _q(re.sub(r"[%_*\\]", "_", detail_prefix) + "*")
        rows = self._call("GET", f"events?kind=eq.{_q(kind)}{like}&select=at,detail&order=at.desc&limit=1")
        return rows[0] if rows else None

    # cost count (cost_count.py): only what a count needs, never names
    def sent_drafts_since(self, since: str, page: int = 1000) -> List[dict]:
        out: List[dict] = []
        while True:
            rows = self._call("GET", f"drafts?sent_at=gte.{_q(since)}&select=phone,body,final_body,sent_at"
                                     f"&order=sent_at.asc,id.asc&limit={page}&offset={len(out)}")
            out += rows
            if len(rows) < page:
                return out
