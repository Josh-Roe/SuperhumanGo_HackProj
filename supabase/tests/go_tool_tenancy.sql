-- A18: Go organizer tools run through the server-side admin (service_role) client after the
-- connector token is resolved to one organizer. Tenancy then rests on p_owner in every RPC,
-- not on RLS. This proves two organizers stay isolated on that path. Everything rolls back.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-8000-0000000000a1','go-organizer-a@example.invalid'),
 ('00000000-0000-4000-8000-0000000000b2','go-organizer-b@example.invalid');
set local role service_role;

do $$ declare ea jsonb; eb jsonb; ta jsonb; f jsonb; a_event uuid;
  a uuid:='00000000-0000-4000-8000-0000000000a1';
  b uuid:='00000000-0000-4000-8000-0000000000b2';
  event_data jsonb:='{"title":"A picnic","description":"","location":"Room A","starts_at":"2026-11-01T18:00:00-08:00","ends_at":"2026-11-01T19:00:00-08:00","timezone":"America/Los_Angeles","links":[],"organizer_contact":"a@example.invalid","invitees":[]}';
begin
  -- The same tool idempotency key under two organizers creates two distinct events.
  ea=public.organizer_write_record(a,'events',null,null,'go-create-1',event_data);
  eb=public.organizer_write_record(b,'events',null,null,'go-create-1',event_data||'{"title":"B party"}');
  a_event=(ea->>'id')::uuid;
  assert a_event<>(eb->>'id')::uuid, 'Idempotency key shared across organizers';
  assert eb->>'owner_id'=b::text and eb->>'title'='B party', 'B replay returned A''s event';

  begin  -- update_event for another organizer's event id
    perform public.organizer_write_record(b,'events',a_event,1,null,event_data||'{"title":"hijacked"}');
    raise exception 'Cross-organizer event update accepted';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
  assert public.organizer_event_json(b,a_event) is null, 'Cross-organizer event read';

  begin  -- create_task pointing at another organizer's event
    perform public.organizer_write_record(b,'tasks',null,null,'go-task-1',
      jsonb_build_object('title','x','description','','status','todo','event_id',a_event));
    raise exception 'Task attached to another organizer''s event';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;

  ta=public.organizer_write_record(a,'tasks',null,null,'go-task-1',
    jsonb_build_object('title','Chairs','description','','status','todo','event_id',a_event));
  begin  -- update_task for another organizer's task id
    perform public.organizer_write_record(b,'tasks',(ta->>'id')::uuid,1,null,
      jsonb_build_object('title','hijacked','description','','status','done'));
    raise exception 'Cross-organizer task update accepted';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;

  begin  -- a missing principal never falls through to "all owners"
    perform public.organizer_write_record(null,'events',null,null,'go-create-2',event_data);
    raise exception 'Null owner accepted';
  exception when raise_exception then if sqlerrm<>'forbidden' then raise; end if; end;

  -- A10 inclusion facts follow the same owner rule and version CAS.
  begin
    perform public.organizer_save_inclusion(b,a_event,0,'{}');
    raise exception 'Cross-organizer inclusion save accepted';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
  f=public.organizer_save_inclusion(a,a_event,0,'{"traditions":[]}');
  assert (f->>'version')::int=1, 'First inclusion save is not version 1';
  begin
    perform public.organizer_save_inclusion(a,a_event,0,'{"traditions":["jewish"]}');
    raise exception 'Stale inclusion version accepted';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;

  assert (select title from public.events where id=a_event)='A picnic', 'A''s event was modified';
  assert (select count(*) from public.tasks where owner_id=b)=0, 'B owns a stray task';
  assert (select count(*) from public.events where owner_id=b)=1, 'B event count wrong';
end $$;
rollback;
select 'passed: Go tool tenancy via service_role + p_owner (two organizers)' as result;
