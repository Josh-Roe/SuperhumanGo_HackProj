-- Live rollback tests caught polymorphic trigger field resolution. Read shared trigger
-- records as JSON so Postgres does not resolve a nonexistent field on another table.
create or replace function public.organizer_validate_child() returns trigger
language plpgsql security invoker set search_path='' as $$
declare expected integer; j jsonb:=to_jsonb(new); begin
  expected=case when tg_table_name='inclusion_facts' then (j->>'revision')::integer
    else (j->>'event_revision')::integer end;
  if tg_op='INSERT' and expected is not null and tg_table_name<>'rsvps' and not exists(
    select 1 from public.events where id=(j->>'event_id')::uuid and revision=expected) then
    raise exception 'revision_conflict';
  end if;
  if tg_table_name='rsvps' then
    if not exists(select 1 from public.invitees where id=(j->>'invitee_id')::uuid
      and event_id=(j->>'event_id')::uuid) then raise exception 'forbidden'; end if;
  end if;
  if tg_table_name in ('go_work','approvals','provider_bindings','inbound_replies') then
    if not exists(select 1 from public.events where id=(j->>'event_id')::uuid
      and owner_id=(j->>'owner_id')::uuid) then raise exception 'forbidden'; end if;
  end if;
  if tg_op='UPDATE' and old.event_id<>new.event_id then raise exception 'forbidden'; end if;
  return new;
end $$;

create policy server_only on public.provider_secrets to service_role using (true) with check (true);
-- This existing managed event trigger needs no public RPC grant. Invocation by its DDL
-- event trigger is unaffected. Do not recreate or change its implementation.
do $$ begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public,anon,authenticated;
  end if;
end $$;

create function public.organizer_operation_immutable() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if new.id<>old.id or new.event_id<>old.event_id or new.event_revision<>old.event_revision
    or new.idempotency_key<>old.idempotency_key or new.approval_id is distinct from old.approval_id
    or new.kind<>old.kind or (old.state='succeeded' and to_jsonb(new)<>to_jsonb(old)) then
    raise exception 'idempotency_conflict';
  end if;
  return new;
end $$;
create trigger immutable_operation before update on public.operations
for each row execute function public.organizer_operation_immutable();
revoke execute on function public.organizer_operation_immutable() from public,anon;
grant execute on function public.organizer_operation_immutable() to authenticated,service_role;

create or replace function public.organizer_record_rsvp(p_owner uuid,p_data jsonb) returns void
language plpgsql security invoker set search_path='' as $$
declare e public.events; observation text; previous jsonb; begin
  e=public.organizer_current(p_owner,(p_data->>'event_id')::uuid,null);
  if (p_data->>'event_revision')::integer>e.revision then raise exception 'revision_conflict'; end if;
  if p_data->>'status' not in ('attending','maybe','not_attending','no_response','needs_review')
    or p_data->>'source' not in ('calendar','email') then raise exception 'invalid_rsvp'; end if;
  select data into previous from public.rsvps where event_id=e.id
    and invitee_id=(p_data->>'invitee_id')::uuid and source=p_data->>'source'
    and data->>'source_id'=p_data->>'source_id' order by observed_at desc,id desc limit 1;
  if previous is not null and previous-'observed_at'=p_data-'observed_at' then return; end if;
  observation=md5(p_owner::text||p_data::text);
  insert into public.rsvps(event_id,invitee_id,status,source,source_message_id,observed_at,event_revision,data,observation_key)
  values(e.id,(p_data->>'invitee_id')::uuid,p_data->>'status',p_data->>'source',
    (p_data->>'source_id')||':'||observation,(p_data->>'observed_at')::timestamptz,
    (p_data->>'event_revision')::integer,p_data,observation) on conflict(observation_key) do nothing;
end $$;

alter table public.generated_content add constraint content_kind_check check (kind in
 ('description','summary','invitation','change_notice','document','notion_note','flyer_brief',
  'flyer_copy','event_document','plain_language_summary','flyer_alt_text'));
alter table public.generated_content add constraint content_producer_check
 check (producer in ('superhuman_go','organizer','gemini'));
alter table public.generated_content add constraint content_state_check
 check (state in ('needs_review','ready','superseded'));
alter table public.go_work add constraint work_state_check
 check (state in ('awaiting_go','running','succeeded','superseded','failed'));
alter table public.operations add constraint operation_state_check
 check (state in ('queued','running','succeeded','failed','superseded'));
