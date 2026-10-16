-- Browser users may review Go content or create clearly labeled organizer edits.
-- Only the server-side MCP workflow can assert Go provenance/provider receipts.
alter table public.generated_content alter column producer set default 'organizer';
revoke insert,update on public.generated_content from authenticated;
grant insert(id,event_id,event_revision,kind,subject,body,state,provenance)
  on public.generated_content to authenticated;
grant update(state) on public.generated_content to authenticated;
revoke insert,update on public.operations,public.provider_bindings,public.inbound_replies,
  public.rsvps,public.artifacts from authenticated;

create function public.organizer_review_content(p_owner uuid,p_content uuid,p_expected integer,
  p_body text,p_subject text) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare c public.generated_content; result public.generated_content; begin
  perform public.organizer_owner(p_owner);
  select c0.* into c from public.generated_content c0 join public.events e on e.id=c0.event_id
    where c0.id=p_content and e.owner_id=p_owner;
  if not found then raise exception 'not_found'; end if;
  perform public.organizer_current(p_owner,c.event_id,p_expected);
  if c.event_revision<>p_expected or c.state='superseded' then raise exception 'revision_conflict'; end if;
  if p_body is null and p_subject is null then
    update public.generated_content set state='ready' where id=p_content returning * into result;
  else
    if length(coalesce(p_body,c.body)) not between 1 and 30000 or length(p_subject)>200 then
      raise exception 'needs_review';
    end if;
    insert into public.generated_content(id,event_id,event_revision,kind,body,subject,state,provenance)
    values(gen_random_uuid(),c.event_id,p_expected,c.kind,coalesce(p_body,c.body),coalesce(p_subject,c.subject),
      'ready',jsonb_build_object('reviewed_from',c.id,'reviewed_by',p_owner)) returning * into result;
  end if;
  return to_jsonb(result);
end $$;
revoke execute on function public.organizer_review_content(uuid,uuid,integer,text,text) from public,anon;
grant execute on function public.organizer_review_content(uuid,uuid,integer,text,text) to authenticated,service_role;
