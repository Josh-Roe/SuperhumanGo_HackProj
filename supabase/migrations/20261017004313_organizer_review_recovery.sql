-- Serial event locking makes repeated clicks/timeouts recover the same approval.
create index approvals_recovery_idx on public.approvals
  (owner_id,event_id,event_revision,action,invitation_content_id);
create or replace function public.organizer_approve(p_owner uuid,p_event uuid,p_expected integer,p_content uuid,
  p_action text,p_acknowledged boolean) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare c public.generated_content; a public.approvals; begin
  perform public.organizer_current(p_owner,p_event,p_expected);
  select * into c from public.generated_content where id=p_content and event_id=p_event
    and event_revision=p_expected and state='ready' and producer in ('superhuman_go','organizer')
    and kind in ('invitation','change_notice');
  if not found or p_acknowledged is not true or p_action not in ('publish','update','draft_only')
    then raise exception 'needs_review'; end if;
  select * into a from public.approvals where owner_id=p_owner and event_id=p_event
    and event_revision=p_expected and action=p_action and invitation_content_id=p_content
    and content_hash=md5(coalesce(c.subject,'')||c.body)
    order by approved_at,id limit 1;
  if found then return to_jsonb(a); end if;
  insert into public.approvals(owner_id,event_id,event_revision,action,invitation_content_id,content_hash,acknowledged_unknowns)
    values(p_owner,p_event,p_expected,p_action,p_content,md5(coalesce(c.subject,'')||c.body),true)
    returning * into a;
  return to_jsonb(a);
end $$;

-- Preserve Member 4's exact sourced/private input shape. Legacy flattened fields
-- remain unknown; a single source field cannot stand in for separate confirmations.
alter table public.inclusion_facts add column inputs jsonb not null default '{}'
  check(jsonb_typeof(inputs)='object' and octet_length(inputs::text)<=64000);
revoke insert,update,delete on public.inclusion_facts from authenticated;
create function public.organizer_save_inclusion(
  p_owner uuid,p_event uuid,p_expected integer,p_inputs jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare saved jsonb; begin
  perform public.organizer_current(p_owner,p_event,p_expected);
  if p_inputs is null or jsonb_typeof(p_inputs)<>'object' or octet_length(p_inputs::text)>64000 then
    raise exception 'needs_review'; end if;
  saved=public.organizer_write_record(p_owner,'events',p_event,p_expected,null,
    public.organizer_event_json(p_owner,p_event));
  insert into public.inclusion_facts(event_id,revision,inputs)
    values(p_event,(saved->>'revision')::integer,p_inputs);
  return saved;
end $$;
revoke execute on function public.organizer_save_inclusion(uuid,uuid,integer,jsonb)
  from public,anon,authenticated;
grant execute on function public.organizer_save_inclusion(uuid,uuid,integer,jsonb) to service_role;
