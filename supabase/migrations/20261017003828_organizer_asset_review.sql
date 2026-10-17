-- Exact immutable export review, separate from Canva transaction/preview approval.
-- Browser sessions cannot edit trusted artifact metadata or forge review receipts.
create table public.artifact_reviews (
  artifact_id uuid primary key references public.artifacts(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  event_revision integer not null check(event_revision>0),
  sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
  approved_at timestamptz not null default now()
);
create index artifact_reviews_owner_idx on public.artifact_reviews(owner_id);
create index artifact_reviews_event_idx on public.artifact_reviews(event_id);
alter table public.artifact_reviews enable row level security;
revoke all on public.artifact_reviews from public,anon,authenticated;
grant select on public.artifact_reviews to authenticated;
grant all on public.artifact_reviews to service_role;
create policy organizer_reads_export_review on public.artifact_reviews for select to authenticated
  using (owner_id=(select auth.uid()) and exists (
    select 1 from public.events e where e.id=event_id and e.owner_id=(select auth.uid())
  ));

create function public.organizer_review_asset(
  p_owner uuid,p_event uuid,p_asset uuid,p_expected integer,p_hash text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare a public.artifacts; c public.generated_content; begin
  perform public.organizer_current(p_owner,p_event,p_expected);
  select * into a from public.artifacts where id=p_asset and event_id=p_event for update;
  if not found then raise exception 'not_found'; end if;
  if not a.is_current or a.event_revision<>p_expected then raise exception 'revision_conflict'; end if;
  if p_hash is null or p_hash<>a.content_hash or p_hash<>a.data->>'sha256' then
    raise exception 'revision_conflict';
  end if;
  if (a.data->>'owner_id')::uuid<>p_owner or (a.data->>'event_id')::uuid<>p_event
    or (a.data->>'event_revision')::integer<>p_expected then raise exception 'forbidden'; end if;
  select * into c from public.generated_content where id=(a.data->>'go_generation_id')::uuid
    and event_id=p_event and event_revision=p_expected and producer='superhuman_go' and state='ready';
  if not found or c.kind<>(case when a.kind='flyer_png' then 'flyer_alt_text' else 'event_document' end) then
    raise exception 'needs_review';
  end if;
  if a.kind='flyer_png' and (
    coalesce(a.data->>'canva_design_id','')='' or coalesce(a.data->>'canva_export_id','')=''
    or coalesce(a.data->>'canva_generation_id','')=''
  ) then raise exception 'needs_review'; end if;
  insert into public.artifact_reviews(artifact_id,owner_id,event_id,event_revision,sha256)
    values(p_asset,p_owner,p_event,p_expected,p_hash) on conflict(artifact_id) do nothing;
  update public.artifacts set data=jsonb_set(data,'{review_state}','"reviewed"')
    where id=p_asset returning * into a;
  return jsonb_build_object('id',a.id,'event_id',p_event,'event_revision',p_expected,
    'sha256',p_hash,'review_state','reviewed');
end $$;
revoke execute on function public.organizer_review_asset(uuid,uuid,uuid,integer,text)
  from public,anon,authenticated;
grant execute on function public.organizer_review_asset(uuid,uuid,uuid,integer,text) to service_role;
