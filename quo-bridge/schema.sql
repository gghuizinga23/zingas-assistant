-- quo-bridge records, in their own Supabase project (not the dashboard's).
-- Only the helper's service key reads or writes these: row level security is on
-- with no policies, so the public "anon" key can't see anything.

create table if not exists messages (
  id          text primary key,              -- Quo message id (AC...)
  phone       text not null,                 -- the customer, E.164
  direction   text not null check (direction in ('in', 'out')),
  body        text not null,
  created_at  timestamptz not null default now(),
  picked_at   timestamptz                    -- when Val's computer took it
);
create index if not exists messages_phone_time on messages (phone, created_at desc);
create index if not exists messages_unpicked on messages (created_at) where direction = 'in' and picked_at is null;

create table if not exists drafts (
  id              text primary key,
  phone           text not null,
  customer_name   text,
  prospect_id     text,
  time_zone       text not null,
  category        text not null,
  body            text not null,             -- Val's draft
  final_body      text,                      -- Gerrit's edit, if any
  edited          boolean not null default false,
  reply_to        text,                      -- messages.id it answers
  customer_said   text not null default '',  -- copied from messages, never from Val
  status          text not null,
  reasons         text not null default '',
  created_at      timestamptz not null default now(),
  approved_at     timestamptz,
  send_after      timestamptz,
  sent_at         timestamptz,
  quo_message_id  text,
  error           text,
  escalated_at    timestamptz,
  missed_at       timestamptz,
  tg_message_id   bigint,
  tg_prompt_id    bigint,
  reported_at     timestamptz                -- when Val's computer took the outcome
);
create index if not exists drafts_status on drafts (status);

create table if not exists contacts (
  phone           text primary key,
  do_not_contact  boolean not null default false,
  updated_at      timestamptz not null default now()
);

create table if not exists auto_send_stats (
  category  text primary key,
  streak    integer not null default 0,
  enabled   boolean not null default false
);

create table if not exists events (
  id        bigserial primary key,
  at        timestamptz not null default now(),
  kind      text not null,
  draft_id  text,
  detail    text
);

alter table messages enable row level security;
alter table drafts enable row level security;
alter table contacts enable row level security;
alter table auto_send_stats enable row level security;
alter table events enable row level security;
