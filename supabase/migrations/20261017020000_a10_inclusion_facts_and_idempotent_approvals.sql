-- A10: versioned organizer inclusion facts and idempotent, recoverable approval creation.
-- Additive. Facts are per event (venue facts survive event revisions) with their own version
-- for optimistic concurrency; `event_revision` records which event revision they were saved at.

create table public.event_inclusion_facts (
  event_id uuid primary key references public.events(id) on delete cascade,
  owner_id uuid not null references auth.users(id),
  version integer not null check (version > 0),
  event_revision integer not null check (event_revision > 0),
  facts jsonb not null check (jsonb_typeof(facts) = 'object'),
  updated_at timestamptz not null default now()
);
create index event_inclusion_facts_owner_idx on public.event_inclusion_facts(owner_id);

alter table public.event_inclusion_facts enable row level security;
revoke all on public.event_inclusion_facts from anon, authenticated;
grant select, insert, update on public.event_inclusion_facts to authenticated;
grant all on public.event_inclusion_facts to service_role;
create policy owner_scope on public.event_inclusion_facts to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id and exists(
    select 1 from public.events e where e.id = event_id and e.owner_id = (select auth.uid())));

-- Direct Data API writes cannot skip versions, move rows between events/owners, or forge revisions.
create function public.organizer_inclusion_guard() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if not exists(select 1 from public.events where id = new.event_id and owner_id = new.owner_id
      and revision = new.event_revision) then
    raise exception 'revision_conflict';
  end if;
  if tg_op = 'INSERT' and new.version <> 1 then raise exception 'revision_conflict'; end if;
  if tg_op = 'UPDATE' and (new.event_id <> old.event_id or new.owner_id <> old.owner_id
      or new.version <> old.version + 1) then
    raise exception 'revision_conflict';
  end if;
  new.updated_at = now();
  return new;
end $$;
create trigger inclusion_guard before insert or update on public.event_inclusion_facts
for each row execute function public.organizer_inclusion_guard();

-- Compare-and-set save. expected_version 0 means "no facts saved yet".
create function public.organizer_save_inclusion(
  p_owner uuid, p_event uuid, p_expected_version integer, p_facts jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare e public.events; f public.event_inclusion_facts; begin
  -- Locks the event row, which serializes concurrent first saves for the same event.
  e = public.organizer_current(p_owner, p_event, null);
  if p_expected_version is null or p_expected_version < 0 then raise exception 'revision_conflict'; end if;
  if jsonb_typeof(p_facts) is distinct from 'object' then raise exception 'invalid_facts'; end if;
  select * into f from public.event_inclusion_facts where event_id = p_event for update;
  if found then
    if f.version <> p_expected_version then raise exception 'revision_conflict'; end if;
    update public.event_inclusion_facts set version = version + 1, event_revision = e.revision,
      facts = p_facts where event_id = p_event returning * into f;
  else
    if p_expected_version <> 0 then raise exception 'revision_conflict'; end if;
    insert into public.event_inclusion_facts(event_id, owner_id, version, event_revision, facts)
    values (p_event, p_owner, 1, e.revision, p_facts) returning * into f;
  end if;
  return to_jsonb(f);
end $$;
revoke all on function public.organizer_save_inclusion(uuid,uuid,integer,jsonb) from public, anon;
grant execute on function public.organizer_save_inclusion(uuid,uuid,integer,jsonb) to authenticated, service_role;
revoke all on function public.organizer_inclusion_guard() from public, anon;
grant execute on function public.organizer_inclusion_guard() to authenticated, service_role;

-- Approval creation is idempotent on (owner, event, revision, action, exact content): a reload
-- or retry returns the original approval instead of a second one. `replayed` tells the API
-- which status to use; it is not stored. The event row lock (organizer_current) serializes
-- concurrent attempts, so no unique index is needed (and none can fail on existing rows).
create or replace function public.organizer_approve(p_owner uuid,p_event uuid,p_expected integer,p_content uuid,
  p_action text,p_acknowledged boolean) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare c public.generated_content; a public.approvals; v_hash text; begin
  perform public.organizer_current(p_owner,p_event,p_expected);
  select * into c from public.generated_content where id=p_content and event_id=p_event
    and event_revision=p_expected and state='ready' and producer in ('superhuman_go','organizer')
    and kind in ('invitation','change_notice');
  if not found or p_acknowledged is not true then raise exception 'needs_review'; end if;
  v_hash = md5(coalesce(c.subject,'')||c.body);
  select * into a from public.approvals where owner_id=p_owner and event_id=p_event
    and event_revision=p_expected and action=p_action and invitation_content_id=p_content
    and content_hash=v_hash order by approved_at, id limit 1;
  if found then return to_jsonb(a)||'{"replayed":true}'::jsonb; end if;
  insert into public.approvals(owner_id,event_id,event_revision,action,invitation_content_id,content_hash,acknowledged_unknowns)
  values(p_owner,p_event,p_expected,p_action,p_content,v_hash,true)
  returning * into a;
  return to_jsonb(a)||'{"replayed":false}'::jsonb;
end $$;
