-- F0 (quote follow-ups), added 2026-10-23. Safe to run more than once.
-- A follow-up is a draft with category 'followup': a text and/or an email for
-- one touch (48 hours, 7 days, ...). The day's list arrives as one batch, with
-- one Approve all / Review one by one card in Val Approvals.
alter table drafts add column if not exists customer_key   text;          -- the customer's email, lowercase
alter table drafts add column if not exists touch          text;          -- '48 hours', '7 days', 'day 14', ...
alter table drafts add column if not exists batch_id       text;          -- the day it was planned, YYYY-MM-DD
alter table drafts add column if not exists due_at         timestamptz;   -- when it sends once approved
alter table drafts add column if not exists email_to       text;
alter table drafts add column if not exists email_subject  text;
alter table drafts add column if not exists email_body     text;
alter table drafts add column if not exists email_thread_id text;         -- reply in the estimate's thread
alter table drafts add column if not exists email_status   text;          -- sent, failed, refused, not_set_up
alter table drafts add column if not exists email_sent_at  timestamptz;
alter table drafts add column if not exists email_error    text;
create index if not exists drafts_batch on drafts (batch_id) where batch_id is not null;

create table if not exists batches (
  id             text primary key,             -- YYYY-MM-DD
  tg_message_id  bigint,
  created_at     timestamptz not null default now()
);
alter table batches enable row level security;
