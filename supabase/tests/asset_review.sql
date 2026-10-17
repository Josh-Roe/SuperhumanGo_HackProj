-- Synthetic export metadata only; no object upload/provider write. Everything rolls back.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-8000-000000000001','organizer-a@example.invalid'),
 ('00000000-0000-4000-8000-000000000002','organizer-b@example.invalid');
set local role service_role;
do $$ declare e jsonb; c jsonb; a public.artifacts; result jsonb;
  owner uuid:='00000000-0000-4000-8000-000000000001';
  other_owner uuid:='00000000-0000-4000-8000-000000000002';
begin
  e=public.organizer_write_record(owner,'events',null,null,'asset-review-event',
    '{"title":"Synthetic asset review","description":"Fixture only","location":"Room A","starts_at":"2026-11-01T18:00:00Z", "ends_at":"2026-11-01T19:00:00Z","timezone":"UTC","links":[],"organizer_contact":"test@example.invalid","invitees":[]}');
  c=public.organizer_save_content(owner,1,jsonb_build_object('id',gen_random_uuid(),'event_id',e->>'id',
    'event_revision',1,'kind','event_document','body','Synthetic prose','producer','superhuman_go',
    'state','needs_review'));
  perform public.organizer_publish_asset(owner,1,jsonb_build_object('owner_id',owner,'event_id',e->>'id',
    'event_revision',1,'kind','event_document','go_generation_id',c->>'id','review_state','needs_review',
    'sha256',repeat('a',64),'object_key',owner||'/events/'||(e->>'id')||'/r1/event_document/'||repeat('a',64)||'.html'));
  select * into a from public.artifacts where event_id=(e->>'id')::uuid;
  begin
    perform public.organizer_review_asset(owner,a.event_id,a.id,1,repeat('a',64));
    raise exception 'Unreviewed prose accepted';
  exception when raise_exception then if sqlerrm<>'needs_review' then raise; end if; end;
  perform public.organizer_review_content(owner,(c->>'id')::uuid,1,null,null);
  begin
    perform public.organizer_review_asset(other_owner,a.event_id,a.id,1,repeat('a',64));
    raise exception 'Foreign owner reviewed asset';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
  begin
    perform public.organizer_review_asset(owner,a.event_id,a.id,1,repeat('b',64));
    raise exception 'Different bytes reviewed';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
  result=public.organizer_review_asset(owner,a.event_id,a.id,1,repeat('a',64));
  assert result->>'review_state'='reviewed';
  perform public.organizer_review_asset(owner,a.event_id,a.id,1,repeat('a',64));
  assert (select count(*) from public.artifact_reviews)=1, 'Review retry duplicated receipt';
  update public.artifacts set is_current=false where id=a.id;
  begin
    perform public.organizer_review_asset(owner,a.event_id,a.id,1,repeat('a',64));
    raise exception 'Superseded export approved';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
end $$;
set local role authenticated;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}';
do $$ begin
  assert (select count(*) from public.artifact_reviews)=1, 'Owner review unreadable';
  begin
    perform public.organizer_review_asset('00000000-0000-4000-8000-000000000001',gen_random_uuid(),gen_random_uuid(),1,repeat('a',64));
    raise exception 'Browser forged trusted review';
  exception when insufficient_privilege then null; end;
  begin
    update public.artifacts set data='{"review_state":"reviewed"}';
    raise exception 'Browser forged metadata';
  exception when insufficient_privilege then null; end;
end $$;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000002","role":"authenticated"}';
do $$ begin
  assert (select count(*) from public.artifact_reviews)=0, 'Foreign review leaked';
end $$;
reset role;
set local role anon;
do $$ begin
  begin
    perform * from public.artifact_reviews;
    raise exception 'Anonymous review read';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'passed: exact export review, revision/hash CAS, isolation, immutable provenance, retry' as result;
rollback;
