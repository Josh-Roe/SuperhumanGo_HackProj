-- Run on a migrated Supabase database with a privileged test connection.
-- Every fixture, including Auth users and Storage metadata, rolls back.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-8000-000000000001','organizer-a@example.invalid'),
 ('00000000-0000-4000-8000-000000000002','organizer-b@example.invalid');
set local role authenticated;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}';

do $$ declare e jsonb; t jsonb; same jsonb; c jsonb; a jsonb; op jsonb; w jsonb; b jsonb;
  owner uuid:='00000000-0000-4000-8000-000000000001';
  other_owner uuid:='00000000-0000-4000-8000-000000000002';
  event_data jsonb:='{"title":"Synthetic event","description":"Fixture only","location":"Room A", "starts_at":"2026-11-01T18:00:00-08:00","ends_at":"2026-11-01T19:00:00-08:00","timezone":"America/Los_Angeles","links":[],"organizer_contact":"test@example.invalid","invitees":[{"email":"guest@example.invalid","display_name":"Synthetic guest"}]}';
begin
  e=public.organizer_write_record(owner,'events',null,null,'test-event',event_data);
  same=public.organizer_write_record(owner,'events',null,null,'test-event',event_data);
  assert same=e, 'Event retry created a duplicate';
  begin
    perform public.organizer_write_record(owner,'events',null,null,'test-event',event_data||'{"title":"different"}');
    raise exception 'Missing idempotency conflict';
  exception when raise_exception then if sqlerrm<>'idempotency_conflict' then raise; end if; end;
  begin
    perform public.organizer_write_record(other_owner,'tasks',null,null,'forged','{"title":"x"}');
    raise exception 'Forged owner accepted';
  exception when raise_exception then if sqlerrm<>'forbidden' then raise; end if; end;
  t=public.organizer_write_record(owner,'tasks',null,null,'test-task',
    jsonb_build_object('title','Synthetic task','description','','status','todo','event_id',e->>'id'));
  same=public.organizer_write_record(owner,'tasks',null,null,'test-task',
    jsonb_build_object('title','Synthetic task','description','','status','todo','event_id',e->>'id'));
  assert same=t, 'Task retry created a duplicate';
  perform public.organizer_write_record(owner,'tasks',(t->>'id')::uuid,1,null,
    jsonb_build_object('title','Updated task','description','','status','done','event_id',e->>'id'));
  begin
    perform public.organizer_write_record(owner,'tasks',(t->>'id')::uuid,1,null,
      jsonb_build_object('title','Stale edit','description','','status','todo'));
    raise exception 'Stale task edit accepted';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
  begin
    perform public.organizer_write_record(owner,'events',null,null,'bad-zone',event_data||'{"timezone":"Mars/Olympus"}');
    raise exception 'Invalid timezone accepted';
  exception when raise_exception then if sqlerrm<>'invalid_timezone' then raise; end if; end;
  begin
    perform public.organizer_write_record(owner,'events',null,null,'bad-times',event_data||'{"ends_at":"2026-11-01T17:00:00-08:00"}');
    raise exception 'Invalid event interval accepted';
  exception when check_violation then null; end;

  w=jsonb_build_object('id',gen_random_uuid(),'owner_id',owner,'event_id',e->>'id',
    'event_revision',1,'kind','prepare_content','state','awaiting_go','payload',
    '{"kinds":["invitation"],"idempotency_key":"synthetic-work"}'::jsonb,'created_at',now(),'claimed_at',null);
  same=public.organizer_put_work(owner,w);
  b=public.organizer_put_work(owner,w||jsonb_build_object('id',gen_random_uuid()));
  assert same=b, 'Work retry created a duplicate';
  perform public.organizer_put_work(owner,w||'{"state":"running"}');
  begin
    perform public.organizer_put_work(owner,w||'{"state":"running"}');
    raise exception 'Double work claim accepted';
  exception when raise_exception then if sqlerrm<>'operation_in_progress' then raise; end if; end;

  -- The Go workflow is a server worker after connector-token resolution. Browser users
  -- cannot supply producer='superhuman_go' or forge provider receipts.
  begin
    perform public.organizer_save_content(owner,1,jsonb_build_object('id',gen_random_uuid(),'event_id',e->>'id',
      'event_revision',1,'kind','invitation','subject','Forged','body','Forged',
      'producer','superhuman_go','state','ready'));
    raise exception 'Browser forged Go provenance';
  exception when insufficient_privilege then null; end;
  execute 'set local role service_role';
  c=public.organizer_save_content(owner,1,jsonb_build_object('id',gen_random_uuid(),'event_id',e->>'id',
    'event_revision',1,'kind','invitation','subject','Synthetic invitation','body','Fixture prose',
    'producer','superhuman_go','state','ready'));
  execute 'set local role authenticated';
  c=public.organizer_review_content(owner,(c->>'id')::uuid,1,null,null);
  same=public.organizer_review_content(owner,(c->>'id')::uuid,1,'Organizer revised prose',null);
  assert same->>'producer'='organizer', 'Organizer edits falsely labeled as Go';
  a=public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'draft_only',true);
  execute 'set local role service_role';
  op=jsonb_build_object('id',gen_random_uuid(),'event_id',e->>'id','event_revision',1,
    'kind','calendar_upsert','idempotency_key','synthetic-calendar','approval_id',a->>'id',
    'state','running','attempts',1,'receipt','{}'::jsonb,'updated_at',now());
  perform public.organizer_put_operation(owner,op);
  begin
    perform public.organizer_put_operation(owner,op);
    raise exception 'Double provider claim accepted';
  exception when raise_exception then if sqlerrm<>'operation_in_progress' then raise; end if; end;
  begin
    perform public.organizer_write_record(owner,'events',(e->>'id')::uuid,1,null,event_data);
    raise exception 'Event changed during provider write';
  exception when raise_exception then if sqlerrm<>'operation_in_progress' then raise; end if; end;
  perform public.organizer_put_operation(owner,op||'{"state":"succeeded","receipt":{"remote_id":"synthetic"}}');
  begin
    perform public.organizer_put_operation(owner,op||'{"state":"succeeded","receipt":{"remote_id":"changed"}}');
    raise exception 'Successful receipt overwritten';
  exception when raise_exception then if sqlerrm<>'idempotency_conflict' then raise; end if; end;
  begin
    perform public.organizer_put_operation(owner,op||jsonb_build_object('id',gen_random_uuid(),
      'kind','gmail_send','idempotency_key','synthetic-send'));
    raise exception 'Draft-only approval sent email';
  exception when raise_exception then if sqlerrm<>'needs_review' then raise; end if; end;

  op=op||jsonb_build_object('id',gen_random_uuid(),'kind','gmail_draft',
    'idempotency_key','synthetic-uncertain-draft','state','running','receipt','{}'::jsonb);
  perform public.organizer_put_operation(owner,op);
  perform public.organizer_put_operation(owner,op||'{"state":"failed","error_code":"provider_failed:504"}');
  begin
    perform public.organizer_put_operation(owner,op);
    raise exception 'Uncertain Gmail create blindly retried';
  exception when raise_exception then if sqlerrm<>'reconciliation_required' then raise; end if; end;
  perform public.organizer_reconcile_operation(owner,'synthetic-uncertain-draft',1,'not_applied',
    '{"source":"synthetic provider read-back","remote_draft_exists":false}');
  op=public.organizer_put_operation(owner,op);
  assert (op->>'attempts')::integer=2, 'Reconciled retry did not advance attempt';
  perform public.organizer_put_operation(owner,op||'{"state":"succeeded","receipt":{"draft_id":"synthetic-draft"}}');
  assert (select count(*) from public.operations where idempotency_key='synthetic-uncertain-draft')=1,
    'Retry created duplicate operations';

  perform public.organizer_record_rsvp(owner,jsonb_build_object('event_id',e->>'id',
    'invitee_id',e#>>'{invitees,0,id}','status','attending','source','calendar',
    'source_id','synthetic-calendar','observed_at',now(),'event_revision',1,
    'private_note','Synthetic private dietary note'));
  assert (select count(*) from public.rsvps)=1, 'RSVP was not stored';
  perform public.organizer_record_rsvp(owner,jsonb_build_object('event_id',e->>'id',
    'invitee_id',e#>>'{invitees,0,id}','status','attending','source','calendar',
    'source_id','synthetic-calendar','observed_at',now()+interval '1 minute','event_revision',1,
    'private_note','Synthetic private dietary note'));
  assert (select count(*) from public.rsvps)=1, 'Repeated Calendar polling duplicated the observation';
  execute 'set local role authenticated';
  e=public.organizer_write_record(owner,'events',(e->>'id')::uuid,1,null,event_data||'{"location":"Room B"}');
  assert (e->>'revision')::integer=2, 'Revision did not advance';
  assert (select count(*) from public.record_versions where kind='events')=2, 'Event history missing';
  assert (select bool_and(state='superseded') from public.go_work), 'Old generation work still active';
  begin
    perform public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'publish',true);
    raise exception 'Stale approval accepted';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
end $$;

-- A second authenticated account cannot read, modify, or reference any first-account rows.
set local role authenticated;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000002","role":"authenticated"}';
do $$ declare foreign_event uuid; begin
  assert (select count(*) from public.events)=0, 'Foreign events leaked';
  assert (select count(*) from public.tasks)=0, 'Foreign tasks leaked';
  assert (select count(*) from public.invitees)=0, 'Foreign invitees leaked';
  assert (select count(*) from public.rsvps)=0, 'Private RSVP notes leaked';
  assert (select count(*) from public.approvals)=0, 'Approvals leaked';
  assert (select count(*) from public.go_work)=0, 'Generation work leaked';
  assert (select count(*) from public.generated_content)=0, 'Content leaked';
  assert (select count(*) from public.record_versions)=0, 'History leaked';
  assert (select count(*) from public.operations)=0, 'Operation receipts leaked';
  begin
    perform * from public.provider_secrets;
    raise exception 'Provider vault readable by user';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
do $$ declare e uuid; begin
  select id into e from public.events where owner_id='00000000-0000-4000-8000-000000000001';
  perform set_config('test.foreign_event',e::text,true);
end $$;
set local role authenticated;
do $$ begin
  begin
    perform public.organizer_write_record('00000000-0000-4000-8000-000000000002','events',
      current_setting('test.foreign_event')::uuid,2,null,'{}');
    raise exception 'Foreign event was editable';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
  begin
    perform public.organizer_write_record('00000000-0000-4000-8000-000000000002','tasks',null,null,
      'foreign-linked-task',jsonb_build_object('title','Foreign link','description','','status','todo',
       'event_id',current_setting('test.foreign_event')));
    raise exception 'Foreign event linked to task';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
end $$;
-- Storage policy checks use the real policy expressions, with synthetic object metadata only.
reset role;
insert into storage.objects(bucket_id,name) select 'event-assets',
 '00000000-0000-4000-8000-000000000001/events/'||id::text||'/r2/event_document/'||repeat('a',64)||'.html'
 from public.events where owner_id='00000000-0000-4000-8000-000000000001';
set local role authenticated;
do $$ begin
  assert (select count(*) from storage.objects where bucket_id='event-assets')=0,
    'Foreign private storage leaked';
  begin
    insert into storage.objects(bucket_id,name) values('event-assets',
      '00000000-0000-4000-8000-000000000002/events/'||current_setting('test.foreign_event')||'/r2/event_document/forged.html');
    raise exception 'Foreign event storage write accepted';
  exception when insufficient_privilege then null; end;
end $$;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}';
do $$ begin
  assert (select count(*) from storage.objects where bucket_id='event-assets')=1, 'Owner storage unreadable';
  update storage.objects set name=name||'.overwritten' where bucket_id='event-assets';
  assert not found, 'Immutable object replaced';
end $$;
reset role;
set local role anon;
set local request.jwt.claims='{}';
do $$ begin
  begin
    perform * from public.tasks;
    raise exception 'Anonymous task read accepted';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'passed: owner isolation, private RSVP/storage, validation, revisions, idempotency, claims, approvals, immutable receipts' as result;
rollback;
