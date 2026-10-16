
create index approvals_owner_idx on public.approvals(owner_id);
create or replace function public.organizer_put_operation(p_owner uuid,p_data jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare o public.operations; a public.approvals; next_state text:=p_data->>'state'; n integer; begin
  perform public.organizer_current(p_owner,(p_data->>'event_id')::uuid,(p_data->>'event_revision')::integer);
  select * into a from public.approvals where id=(p_data->>'approval_id')::uuid and owner_id=p_owner
    and event_id=(p_data->>'event_id')::uuid and event_revision=(p_data->>'event_revision')::integer;
  if not found then raise exception 'needs_review'; end if;
  if p_data->>'kind'='gmail_send' and a.action='draft_only' then raise exception 'needs_review'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_data->>'idempotency_key',0));
  if next_state='running' and exists(select 1 from public.operations where event_id=(p_data->>'event_id')::uuid and state='running' and idempotency_key<>p_data->>'idempotency_key') then raise exception 'operation_in_progress'; end if;
  select * into o from public.operations where idempotency_key=p_data->>'idempotency_key' for update;
  if found then
    if o.event_id<>(p_data->>'event_id')::uuid or o.approval_id<>(p_data->>'approval_id')::uuid then
      raise exception 'idempotency_conflict';
    end if;
    if o.state='succeeded' then
      if next_state<>'succeeded' or coalesce(o.provider_receipt,'{}')<>coalesce(p_data->'receipt','{}') then
        raise exception 'idempotency_conflict';
      end if;
      return o.data;
    end if;
    if next_state<>'running' and ((p_data->>'id')::uuid<>o.id or (p_data->>'attempts')::integer<>o.attempts) then raise exception 'idempotency_conflict'; end if;
    if next_state='running' and o.state='running' then raise exception 'operation_in_progress'; end if;
    -- Ambiguous Gmail create/send must reconcile before another attempt; never blindly re-send.
    if next_state='running' and o.state='failed' and o.kind in ('gmail_draft','gmail_send')
      and coalesce(o.error_code,'') not in ('integration_not_connected','confirmed_no_effect') then
      raise exception 'reconciliation_required';
    end if;
    n=case when next_state='running' then o.attempts+1 else o.attempts end;
    if next_state not in ('running','failed','succeeded') then raise exception 'needs_review'; end if;
    update public.operations set state=next_state,attempts=n,error_code=p_data->>'error_code',
      provider_receipt=coalesce(p_data->'receipt','{}'),data=p_data||jsonb_build_object('id',o.id,'attempts',n),
      updated_at=now() where id=o.id returning * into o;
  else
    if next_state<>'running' then raise exception 'needs_review'; end if;
    insert into public.operations(id,event_id,event_revision,kind,idempotency_key,approval_id,state,attempts,data)
    values((p_data->>'id')::uuid,(p_data->>'event_id')::uuid,(p_data->>'event_revision')::integer,
      p_data->>'kind',p_data->>'idempotency_key',(p_data->>'approval_id')::uuid,'running',1,p_data)
    returning * into o;
  end if;
  return o.data;
end $$;

create function public.organizer_block_uncertain_revision() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if exists(select 1 from public.operations where event_id=old.id
    and (state='running' or (state='failed' and kind in ('gmail_draft','gmail_send')
      and coalesce(error_code,'') not in ('integration_not_connected','confirmed_no_effect')))) then
    raise exception 'reconciliation_required';
  end if;
  return new;
end $$;
create trigger block_uncertain_revision before update on public.events
for each row execute function public.organizer_block_uncertain_revision();

create function public.organizer_reconcile_operation(p_owner uuid,p_key text,p_attempt integer,
  p_outcome text,p_receipt jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare o public.operations; next_state text; error text; begin
  if current_user<>'service_role' then raise exception 'forbidden'; end if;
  perform public.organizer_owner(p_owner);
  select op.* into o from public.operations op join public.events e on e.id=op.event_id
    where e.owner_id=p_owner and op.idempotency_key=p_key for update of op;
  if not found then raise exception 'not_found'; end if;
  if o.attempts<>p_attempt then raise exception 'idempotency_conflict'; end if;
  if o.state='succeeded' then return o.data; end if;
  if p_outcome not in ('succeeded','not_applied') or jsonb_typeof(p_receipt)<>'object'
    or p_receipt='{}'::jsonb then raise exception 'needs_review'; end if;
  next_state=case when p_outcome='succeeded' then 'succeeded' else 'failed' end;
  error=case when p_outcome='not_applied' then 'confirmed_no_effect' else null end;
  update public.operations set state=next_state,error_code=error,provider_receipt=p_receipt,
    updated_at=now(),data=data||jsonb_build_object('state',next_state,'error_code',error,
      'receipt',p_receipt,'updated_at',now())
    where id=o.id returning data into p_receipt;
  return p_receipt;
end $$;
revoke execute on function public.organizer_reconcile_operation(uuid,text,integer,text,jsonb)
  from public,anon,authenticated;
grant execute on function public.organizer_reconcile_operation(uuid,text,integer,text,jsonb) to service_role;
revoke execute on function public.organizer_block_uncertain_revision() from public,anon;
grant execute on function public.organizer_block_uncertain_revision() to authenticated,service_role;

create function public.organizer_binding_monotonic() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if new.owner_id<>old.owner_id or new.provider<>old.provider or new.event_revision<old.event_revision
    then raise exception 'revision_conflict'; end if;
  return new;
end $$;
create trigger monotonic_binding before update on public.provider_bindings
for each row execute function public.organizer_binding_monotonic();
revoke execute on function public.organizer_binding_monotonic() from public,anon;
grant execute on function public.organizer_binding_monotonic() to authenticated,service_role;
