-- User 2: hosted/CI regression for A11's server-only, fenced flyer leases.
-- Synthetic users, events and opaque fixture state all roll back.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-8000-0000000000c1','canva-lease-a@example.invalid'),
 ('00000000-0000-4000-8000-0000000000c2','canva-lease-b@example.invalid');
insert into public.events(id,owner_id,title,starts_at,ends_at,timezone) values
 ('00000000-0000-4000-8000-0000000000e1','00000000-0000-4000-8000-0000000000c1',
  'Canva lease rollback fixture',now()+interval '1 day',now()+interval '2 days','UTC');
set local role service_role;
do $$ declare
 a uuid:='00000000-0000-4000-8000-0000000000c1';
 b uuid:='00000000-0000-4000-8000-0000000000c2';
 e uuid:='00000000-0000-4000-8000-0000000000e1';
begin
 assert public.canva_flyer_acquire(a,e,'worker-a',300), 'First lease failed';
 assert not public.canva_flyer_acquire(a,e,'worker-b',300), 'Concurrent lease allowed';
 assert public.canva_flyer_save(a,e,'worker-a',1,'pending','synthetic-envelope')=1,
  'First state version wrong';
 begin
  perform public.canva_flyer_acquire(b,e,'foreign',300);
  raise exception 'Foreign owner acquired lease';
 exception when raise_exception then if sqlerrm<>'not_found' then raise; end if; end;
 update public.canva_flyer_jobs set lease_expires_at=now()-interval '1 second'
  where owner_id=a and event_id=e;
 assert public.canva_flyer_acquire(a,e,'worker-b',300), 'Expired lease not recoverable';
 begin
  perform public.canva_flyer_save(a,e,'worker-a',1,'failed','stale');
  raise exception 'Stale worker wrote state';
 exception when raise_exception then if sqlerrm<>'operation_in_progress' then raise; end if; end;
 assert public.canva_flyer_save(a,e,'worker-b',1,'complete','recovered-envelope')=2,
  'Recovered version wrong';
 perform public.canva_flyer_release(a,e,'worker-a');
 assert (select lease_holder='worker-b' from public.canva_flyer_jobs
  where owner_id=a and event_id=e), 'Stale release cleared live lease';
 perform public.canva_flyer_release(a,e,'worker-b');
 assert (select lease_holder is null and ciphertext='recovered-envelope'
  from public.canva_flyer_jobs where owner_id=a and event_id=e), 'Release lost durable state';
end $$;
set local role authenticated;
set local request.jwt.claims='{"sub":"00000000-0000-4000-8000-0000000000c1","role":"authenticated"}';
do $$ begin
 begin
  perform * from public.canva_flyer_jobs;
  raise exception 'Private state exposed';
 exception when insufficient_privilege then null; end;
 begin
  perform public.canva_flyer_acquire('00000000-0000-4000-8000-0000000000c1',
   '00000000-0000-4000-8000-0000000000e1','browser',300);
  raise exception 'Browser acquired server lease';
 exception when insufficient_privilege then null; end;
end $$;
rollback;
select 'passed: Canva flyer lease exclusion, recovery, fencing and browser privacy' as result;
