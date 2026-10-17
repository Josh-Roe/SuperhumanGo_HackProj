begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-8000-000000000001','organizer-a@example.invalid'),
 ('00000000-0000-4000-8000-000000000002','organizer-b@example.invalid');
set local role service_role;
do $$ declare e jsonb; c jsonb; a jsonb; same jsonb; saved jsonb;
  owner uuid:='00000000-0000-4000-8000-000000000001';
  facts jsonb:='{"step_free_entrance":{"value":"yes","source":{"label":"Synthetic venue confirmation","observed_at":"2026-10-16T10:00:00Z","confirmed_by":"Synthetic organizer"}},"required_diets":["synthetic private requirement"]}';
begin
  e=public.organizer_write_record(owner,'events',null,null,'review-recovery-event',
    '{"title":"Synthetic recovery","description":"Fixture only","location":"Room A","starts_at":"2026-11-01T18:00:00Z", "ends_at":"2026-11-01T19:00:00Z","timezone":"UTC","links":[],"organizer_contact":"test@example.invalid","invitees":[]}');
  c=public.organizer_save_content(owner,1,jsonb_build_object('id',gen_random_uuid(),'event_id',e->>'id',
    'event_revision',1,'kind','invitation','subject','Synthetic invitation','body','Synthetic prose',
    'producer','superhuman_go','state','ready'));
  a=public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'publish',true);
  same=public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'publish',true);
  assert same=a, 'Approval timeout retry changed saved identity';
  assert (select count(*) from public.approvals)=1, 'Approval was duplicated';
  same=public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'draft_only',true);
  assert same->>'id'<>a->>'id', 'Approval action silently changed';
  begin
    perform public.organizer_save_inclusion('00000000-0000-4000-8000-000000000002',(e->>'id')::uuid,1,facts);
    raise exception 'Foreign inclusion facts editable';
  exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
  saved=public.organizer_save_inclusion(owner,(e->>'id')::uuid,1,facts);
  assert saved->>'id'=e->>'id' and (saved->>'revision')::integer=2, 'Facts did not advance canonical revision';
  assert (select inputs from public.inclusion_facts where event_id=(e->>'id')::uuid and revision=2)=facts,
    'Dated/private inputs were altered';
  assert (select step_free from public.inclusion_facts where event_id=(e->>'id')::uuid and revision=2)='unknown',
    'Flattened legacy source falsely certified a fact';
  assert (select state from public.generated_content where id=(c->>'id')::uuid)='superseded',
    'Old prose remained ready after inclusion revision';
  begin
    perform public.organizer_save_inclusion(owner,(e->>'id')::uuid,1,facts);
    raise exception 'Stale inclusion save accepted';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
  begin
    perform public.organizer_approve(owner,(e->>'id')::uuid,1,(c->>'id')::uuid,'publish',true);
    raise exception 'Old approval remained current after inclusion change';
  exception when raise_exception then if sqlerrm<>'revision_conflict' then raise; end if; end;
end $$;
set local role authenticated;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}';
do $$ begin
  assert (select count(*) from public.approvals)=2, 'Recoverable approvals unreadable by owner';
  assert (select count(*) from public.inclusion_facts)=1, 'Private facts unreadable by owner';
  begin
    update public.inclusion_facts set inputs='{}';
    raise exception 'Fact revision bypass accepted';
  exception when insufficient_privilege then null; end;
end $$;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-000000000002","role":"authenticated"}';
do $$ begin
  assert (select count(*) from public.approvals)=0, 'Foreign approvals leaked';
  assert (select count(*) from public.inclusion_facts)=0, 'Private dietary facts leaked';
end $$;
reset role;
select 'passed: approval recovery, fact revision CAS, sourced/private persistence and isolation' as result;
rollback;
