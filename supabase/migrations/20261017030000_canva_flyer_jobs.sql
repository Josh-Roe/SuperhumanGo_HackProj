-- A11 (Canva part): durable per-event Canva flyer job state plus a cross-process lease.
-- Replaces flyer state held in provider_secrets (`canva_flyer:<event>`) and the backend's
-- in-process lock. Additive. Server-only like provider_secrets: the state ciphertext holds
-- Canva's continuation token, so organizers read flyer status through the backend API.

create table public.canva_flyer_jobs (
  owner_id uuid not null references auth.users(id),
  event_id uuid not null references public.events(id) on delete cascade,
  event_revision integer check (event_revision > 0),
  stage text,
  -- Fernet(CREDENTIAL_ENCRYPTION_KEY) envelope bound to owner_id/event_id; null = lease only.
  ciphertext text,
  version bigint not null default 0,
  lease_holder text,
  lease_expires_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (owner_id, event_id),
  check ((lease_holder is null) = (lease_expires_at is null))
);

alter table public.canva_flyer_jobs enable row level security;
revoke all on public.canva_flyer_jobs from public, anon, authenticated;
grant all on public.canva_flyer_jobs to service_role;
create policy server_only on public.canva_flyer_jobs to service_role using (true) with check (true);

-- Take (or re-take, or steal an expired) lease. Returns false while another holder's lease
-- is live. The event must belong to the owner.
create function public.canva_flyer_acquire(
  p_owner uuid, p_event uuid, p_holder text, p_ttl_seconds integer
) returns boolean language plpgsql security invoker set search_path='' as $$
declare n integer; begin
  if p_holder is null or length(p_holder) = 0 or p_ttl_seconds is null
     or p_ttl_seconds < 1 or p_ttl_seconds > 900 then
    raise exception 'invalid_lease';
  end if;
  if not exists(select 1 from public.events where id = p_event and owner_id = p_owner) then
    raise exception 'not_found';
  end if;
  insert into public.canva_flyer_jobs as j (owner_id, event_id, lease_holder, lease_expires_at)
  values (p_owner, p_event, p_holder, now() + make_interval(secs => p_ttl_seconds))
  on conflict (owner_id, event_id) do update
    set lease_holder = excluded.lease_holder, lease_expires_at = excluded.lease_expires_at
    where j.lease_holder is null or j.lease_expires_at <= now() or j.lease_holder = p_holder;
  get diagnostics n = row_count;
  return n = 1;
end $$;

-- Fenced write: only the current, unexpired lease holder may replace the state.
create function public.canva_flyer_save(
  p_owner uuid, p_event uuid, p_holder text, p_event_revision integer, p_stage text,
  p_ciphertext text
) returns bigint language plpgsql security invoker set search_path='' as $$
declare v bigint; begin
  update public.canva_flyer_jobs
     set ciphertext = p_ciphertext, stage = p_stage, event_revision = p_event_revision,
         version = version + 1, updated_at = now()
   where owner_id = p_owner and event_id = p_event
     and lease_holder = p_holder and lease_expires_at > now()
  returning version into v;
  if v is null then raise exception 'operation_in_progress'; end if;  -- lease lost
  return v;
end $$;

create function public.canva_flyer_release(p_owner uuid, p_event uuid, p_holder text)
returns void language sql security invoker set search_path='' as $$
  update public.canva_flyer_jobs set lease_holder = null, lease_expires_at = null
   where owner_id = p_owner and event_id = p_event and lease_holder = p_holder;
$$;

revoke execute on function public.canva_flyer_acquire(uuid, uuid, text, integer),
  public.canva_flyer_save(uuid, uuid, text, integer, text, text),
  public.canva_flyer_release(uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.canva_flyer_acquire(uuid, uuid, text, integer),
  public.canva_flyer_save(uuid, uuid, text, integer, text, text),
  public.canva_flyer_release(uuid, uuid, text)
  to service_role;
