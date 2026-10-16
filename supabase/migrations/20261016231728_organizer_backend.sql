-- Reproducible baseline plus additive upgrade of the initial connected-project schema.
-- Invoker RPCs preserve RLS. Service callers must supply an owner from a validated principal.
create table if not exists public.events (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  revision integer not null default 1 check (revision > 0), title text not null,
  description text not null default '', location text not null default '',
  starts_at timestamptz not null, ends_at timestamptz not null, timezone text not null,
  links jsonb not null default '[]', organizer_contact text not null default '',
  status text not null default 'draft', created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(), check (ends_at > starts_at)
);
create table if not exists public.invitees (
  id uuid primary key default gen_random_uuid(), event_id uuid not null references public.events(id),
  email text not null, display_name text, created_at timestamptz not null default now(),
  unique(event_id, email)
);
create table if not exists public.generated_content (
  id uuid primary key default gen_random_uuid(), event_id uuid not null references public.events(id),
  event_revision integer not null, kind text not null, body text not null, producer text not null,
  state text not null default 'needs_review', created_at timestamptz not null default now()
);
create table if not exists public.operations (
  id uuid primary key default gen_random_uuid(), event_id uuid not null references public.events(id),
  event_revision integer not null, kind text not null, idempotency_key text not null unique,
  authorization_reference text, state text not null default 'queued', attempts integer not null default 0,
  error_code text, provider_receipt jsonb, created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.rsvps (
  id uuid primary key default gen_random_uuid(), event_id uuid not null references public.events(id),
  invitee_id uuid not null references public.invitees(id), status text not null default 'no_response',
  source text not null, source_message_id text, observed_at timestamptz not null default now(),
  event_revision integer not null, unique(event_id, invitee_id, source_message_id)
);
create table if not exists public.artifacts (
  id uuid primary key default gen_random_uuid(), event_id uuid not null references public.events(id),
  event_revision integer not null, kind text not null, storage_path text, provider_design_id text,
  exported_version_id text, content_hash text, current_url text, access_policy text not null default 'private',
  created_at timestamptz not null default now()
);
create table if not exists public.inclusion_facts (
  event_id uuid not null references public.events(id), revision integer not null,
  step_free text not null default 'unknown', elevator text not null default 'unknown',
  captions text not null default 'unknown', diet_options text not null default 'unknown',
  loud_sound_strobes text not null default 'unknown', observance_notes text not null default '',
  source text, confirmed_by text, confirmed_at timestamptz, primary key(event_id, revision)
);
alter table public.invitees add column if not exists active boolean not null default true;
alter table public.generated_content add column if not exists subject text;
alter table public.generated_content add column if not exists provenance jsonb not null default '{}';
alter table public.rsvps add column if not exists data jsonb not null default '{}';
alter table public.artifacts add column if not exists data jsonb not null default '{}';
alter table public.artifacts add column if not exists is_current boolean not null default false;
alter table public.operations add column if not exists approval_id uuid;
alter table public.operations add column if not exists data jsonb not null default '{}';

create table public.tasks (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  revision integer not null default 1 check (revision > 0),
  title text not null check (length(btrim(title)) between 1 and 200),
  description text not null default '' check (length(description) <= 30000),
  status text not null default 'todo' check (status in ('todo','in_progress','done')),
  due_at timestamptz, event_id uuid references public.events(id),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.record_versions (
  owner_id uuid not null references auth.users(id), kind text not null check (kind in ('events','tasks')),
  record_id uuid not null, revision integer not null check (revision > 0), snapshot jsonb not null,
  created_at timestamptz not null default now(), primary key(owner_id,kind,record_id,revision)
);
create table public.request_keys (
  owner_id uuid not null references auth.users(id), kind text not null, key text not null,
  request_hash text not null, response jsonb not null, created_at timestamptz not null default now(),
  primary key(owner_id,kind,key)
);
create table public.go_work (
  id uuid primary key, owner_id uuid not null references auth.users(id),
  event_id uuid not null references public.events(id), event_revision integer not null,
  idempotency_key text not null, state text not null, data jsonb not null,
  unique(owner_id,idempotency_key)
);
create table public.approvals (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  event_id uuid not null references public.events(id), event_revision integer not null,
  action text not null check (action in ('publish','update','draft_only')),
  invitation_content_id uuid not null references public.generated_content(id),
  content_hash text not null, acknowledged_unknowns boolean not null check (acknowledged_unknowns),
  approved_at timestamptz not null default now()
);
alter table public.operations add constraint operation_approval_fk foreign key(approval_id) references public.approvals(id);
create table public.provider_bindings (
  owner_id uuid not null references auth.users(id), event_id uuid not null references public.events(id),
  provider text not null check (provider in ('calendar','gmail','canva')),
  event_revision integer not null, data jsonb not null, updated_at timestamptz not null default now(),
  primary key(owner_id,event_id,provider)
);
create table public.inbound_replies (
  owner_id uuid not null references auth.users(id), id text not null,
  event_id uuid not null references public.events(id), data jsonb not null, primary key(owner_id,id)
);
create table public.connector_tokens (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id),
  token_hash text not null unique check (length(token_hash)=64), label text not null,
  expires_at timestamptz not null, revoked_at timestamptz, created_at timestamptz not null default now()
);
-- Ciphertext only; API callers and MCP tools have no table grants. Server holds encryption key.
create table public.provider_secrets (
  owner_id uuid not null references auth.users(id), provider text not null,
  ciphertext text not null, updated_at timestamptz not null default now(),
  primary key(owner_id,provider)
);

create index events_owner_updated_idx on public.events(owner_id,updated_at desc);
create index tasks_owner_updated_idx on public.tasks(owner_id,updated_at desc);
create index tasks_event_idx on public.tasks(event_id);
create index invitees_event_idx on public.invitees(event_id);
create index content_revision_idx on public.generated_content(event_id,event_revision,kind,created_at desc);
create index operations_event_idx on public.operations(event_id,event_revision);
create index operations_approval_idx on public.operations(approval_id);
create index rsvps_event_idx on public.rsvps(event_id);
create index rsvps_invitee_idx on public.rsvps(invitee_id);
create index assets_revision_idx on public.artifacts(event_id,event_revision,kind);
create unique index assets_object_idx on public.artifacts(storage_path);
create unique index assets_current_idx on public.artifacts(event_id,kind) where is_current;
create index work_owner_state_idx on public.go_work(owner_id,state);
create index work_event_idx on public.go_work(event_id);
create index approvals_event_idx on public.approvals(event_id);
create index approvals_content_idx on public.approvals(invitation_content_id);
create index bindings_event_idx on public.provider_bindings(event_id);
create index replies_event_idx on public.inbound_replies(event_id);
create index connectors_owner_idx on public.connector_tokens(owner_id);
alter table public.rsvps add column observation_key text;
create unique index rsvp_observation_key_idx on public.rsvps(observation_key);

-- Replace the original broad policies with explicit authenticated ownership.
do $$ declare t text; p record; begin
  foreach t in array array['events','invitees','generated_content','operations','rsvps','artifacts',
    'inclusion_facts','tasks','record_versions','request_keys','go_work','approvals','provider_bindings',
    'inbound_replies','connector_tokens','provider_secrets'] loop
    execute format('alter table public.%I enable row level security',t);
    for p in select policyname from pg_policies where schemaname='public' and tablename=t loop
      execute format('drop policy %I on public.%I',p.policyname,t);
    end loop;
    execute format('revoke all on public.%I from anon, authenticated',t);
    if t <> 'provider_secrets' then
      execute format('grant select, insert, update on public.%I to authenticated',t);
      if t in ('events','tasks','record_versions','request_keys','go_work','approvals',
               'provider_bindings','inbound_replies','connector_tokens') then
        execute format('create policy owner_scope on public.%I to authenticated using '
          ||'((select auth.uid())=owner_id) with check ((select auth.uid())=owner_id)',t);
      else
        execute format('create policy owner_scope on public.%I to authenticated using '
          ||'(exists(select 1 from public.events e where e.id=event_id and e.owner_id=(select auth.uid()))) '
          ||'with check (exists(select 1 from public.events e where e.id=event_id and e.owner_id=(select auth.uid())))',t);
      end if;
    end if;
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
revoke insert,update on public.record_versions,public.request_keys,public.approvals from authenticated;
-- The API creates approval/history through scoped invoker RPCs with explicit column grants.
grant insert on public.record_versions,public.request_keys,public.approvals to authenticated;

create function public.organizer_owner(p_owner uuid) returns void
language plpgsql security invoker set search_path='' as $$ begin
  if p_owner is null or (current_user <> 'service_role' and auth.uid() is distinct from p_owner) then
    raise exception 'forbidden' using errcode='P0001';
  end if;
end $$;

create function public.organizer_current(p_owner uuid,p_event uuid,p_revision integer)
returns public.events language plpgsql security invoker set search_path='' as $$
declare e public.events; begin
  perform public.organizer_owner(p_owner);
  select * into e from public.events where id=p_event and owner_id=p_owner for update;
  if not found then raise exception 'not_found'; end if;
  if p_revision is not null and e.revision<>p_revision then raise exception 'revision_conflict'; end if;
  return e;
end $$;

create function public.organizer_validate_record() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if tg_op='UPDATE' and (new.owner_id<>old.owner_id or new.id<>old.id
    or new.revision<>old.revision+1 or new.created_at<>old.created_at) then
    raise exception 'revision_conflict';
  end if;
  if length(btrim(new.title)) not between 1 and 200 or length(new.description)>30000 then
    raise exception 'invalid_record';
  end if;
  if tg_table_name='events' then
    if not exists(select 1 from pg_catalog.pg_timezone_names where name=new.timezone) then
      raise exception 'invalid_timezone';
    end if;
  elsif new.event_id is not null then
    perform public.organizer_current(new.owner_id,new.event_id,null);
  end if;
  new.updated_at=now();
  return new;
end $$;
create trigger validate_event before insert or update on public.events
for each row execute function public.organizer_validate_record();
create trigger validate_task before insert or update on public.tasks
for each row execute function public.organizer_validate_record();

create function public.organizer_event_json(p_owner uuid,p_id uuid) returns jsonb
language sql stable security invoker set search_path='' as $$
  select to_jsonb(e)||jsonb_build_object('invitees',coalesce((
    select jsonb_agg(jsonb_build_object('id',i.id,'email',i.email,'display_name',i.display_name) order by i.email)
    from public.invitees i where i.event_id=e.id and i.active),'[]'::jsonb))
  from public.events e where e.id=p_id and e.owner_id=p_owner
$$;

create function public.organizer_write_record(
  p_owner uuid,p_kind text,p_id uuid,p_expected integer,p_key text,p_data jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_id uuid:=coalesce(p_id,gen_random_uuid()); result jsonb; prior public.request_keys;
  old_revision integer; i jsonb; begin
  perform public.organizer_owner(p_owner);
  if p_kind not in ('events','tasks') then raise exception 'invalid_kind'; end if;
  if p_id is null then
    if p_key is null or length(p_key) not between 1 and 128 then raise exception 'invalid_key'; end if;
    perform pg_advisory_xact_lock(hashtextextended(p_owner::text||p_kind||p_key,0));
    select * into prior from public.request_keys where owner_id=p_owner and kind=p_kind and key=p_key;
    if found then
      if prior.request_hash<>md5(p_data::text) then raise exception 'idempotency_conflict'; end if;
      return prior.response;
    end if;
  else
    execute format('select revision from public.%I where id=$1 and owner_id=$2 for update',p_kind)
      into old_revision using p_id,p_owner;
    if old_revision is null then raise exception 'not_found'; end if;
    if p_expected is null or old_revision<>p_expected then raise exception 'revision_conflict'; end if;
  end if;
  if p_kind='events' then
    if p_id is null then
      insert into public.events(id,owner_id,title,description,location,starts_at,ends_at,timezone,links,organizer_contact)
      values(v_id,p_owner,p_data->>'title',p_data->>'description',p_data->>'location',
        (p_data->>'starts_at')::timestamptz,(p_data->>'ends_at')::timestamptz,p_data->>'timezone',
        p_data->'links',p_data->>'organizer_contact');
    else
      -- Do not revise while an external write is active/uncertain: reconcile it first.
      if exists(select 1 from public.operations where event_id=p_id and state='running') then
        raise exception 'operation_in_progress';
      end if;
      update public.events set title=p_data->>'title',description=p_data->>'description',
        location=p_data->>'location',starts_at=(p_data->>'starts_at')::timestamptz,
        ends_at=(p_data->>'ends_at')::timestamptz,timezone=p_data->>'timezone',links=p_data->'links',
        organizer_contact=p_data->>'organizer_contact',revision=revision+1,status='changed'
      where id=p_id and owner_id=p_owner;
      update public.invitees set active=false where event_id=p_id;
      update public.go_work set state='superseded',data=jsonb_set(data,'{state}','"superseded"')
        where event_id=p_id and state in ('awaiting_go','running');
      update public.generated_content set state='superseded' where event_id=p_id and state<>'superseded';
      update public.artifacts set is_current=false where event_id=p_id;
    end if;
    for i in select value from jsonb_array_elements(coalesce(p_data->'invitees','[]')) loop
      insert into public.invitees(event_id,email,display_name) values(v_id,lower(i->>'email'),i->>'display_name')
        on conflict(event_id,email) do update set display_name=excluded.display_name,active=true;
    end loop;
    result=public.organizer_event_json(p_owner,v_id);
  else
    if p_id is null then
      insert into public.tasks(id,owner_id,title,description,status,due_at,event_id)
      values(v_id,p_owner,p_data->>'title',p_data->>'description',p_data->>'status',
        (p_data->>'due_at')::timestamptz,(p_data->>'event_id')::uuid) returning to_jsonb(tasks.*) into result;
    else
      update public.tasks set title=p_data->>'title',description=p_data->>'description',status=p_data->>'status',
        due_at=(p_data->>'due_at')::timestamptz,event_id=(p_data->>'event_id')::uuid,revision=revision+1
      where id=p_id and owner_id=p_owner returning to_jsonb(tasks.*) into result;
    end if;
  end if;
  insert into public.record_versions(owner_id,kind,record_id,revision,snapshot)
    values(p_owner,p_kind,v_id,(result->>'revision')::integer,result);
  if p_id is null then
    insert into public.request_keys values(p_owner,p_kind,p_key,md5(p_data::text),result,now());
  end if;
  return result;
end $$;

create function public.organizer_save_content(p_owner uuid,p_expected integer,p_data jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare c public.generated_content; begin
  perform public.organizer_current(p_owner,(p_data->>'event_id')::uuid,p_expected);
  if (p_data->>'event_revision')::integer<>p_expected then raise exception 'revision_conflict'; end if;
  if p_data->>'state' not in ('needs_review','ready') or length(p_data->>'body') not between 1 and 30000 then
    raise exception 'needs_review';
  end if;
  -- Insert-only content: approval binds exact bytes; edits create a new content ID.
  insert into public.generated_content(id,event_id,event_revision,kind,subject,body,producer,state,provenance)
  values((p_data->>'id')::uuid,(p_data->>'event_id')::uuid,p_expected,p_data->>'kind',
    p_data->>'subject',p_data->>'body',p_data->>'producer',p_data->>'state',coalesce(p_data->'provenance','{}'))
  on conflict(id) do nothing returning * into c;
  if not found then
    select * into c from public.generated_content where id=(p_data->>'id')::uuid
      and event_id=(p_data->>'event_id')::uuid and event_revision=p_expected;
    if not found or c.body<>p_data->>'body' or c.kind<>p_data->>'kind'
      or c.subject is distinct from p_data->>'subject' then raise exception 'idempotency_conflict'; end if;
  end if;
  return to_jsonb(c);
end $$;

create function public.organizer_approve(p_owner uuid,p_event uuid,p_expected integer,p_content uuid,
  p_action text,p_acknowledged boolean) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare c public.generated_content; a public.approvals; begin
  perform public.organizer_current(p_owner,p_event,p_expected);
  select * into c from public.generated_content where id=p_content and event_id=p_event
    and event_revision=p_expected and state='ready' and producer in ('superhuman_go','organizer')
    and kind in ('invitation','change_notice');
  if not found or p_acknowledged is not true then raise exception 'needs_review'; end if;
  insert into public.approvals(owner_id,event_id,event_revision,action,invitation_content_id,content_hash,acknowledged_unknowns)
  values(p_owner,p_event,p_expected,p_action,p_content,md5(coalesce(c.subject,'')||c.body),true)
  returning * into a;
  return to_jsonb(a);
end $$;

create function public.organizer_put_work(p_owner uuid,p_data jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare w public.go_work; k text; next_state text:=p_data->>'state'; begin
  perform public.organizer_owner(p_owner);
  if (p_data->>'owner_id')::uuid<>p_owner then raise exception 'forbidden'; end if;
  if next_state<>'superseded' then
    perform public.organizer_current(p_owner,(p_data->>'event_id')::uuid,(p_data->>'event_revision')::integer);
  end if;
  k=coalesce(p_data#>>'{payload,idempotency_key}',(p_data->>'event_id')||':'||
    (p_data->>'event_revision')||':'||(p_data->>'kind')||':'||coalesce(p_data#>>'{payload,batch}','event_prose'));
  perform pg_advisory_xact_lock(hashtextextended(p_owner::text||k,0));
  select * into w from public.go_work where owner_id=p_owner and (id=(p_data->>'id')::uuid or idempotency_key=k) for update;
  if found then
    if next_state='running' and w.state<>'awaiting_go' then raise exception 'operation_in_progress'; end if;
    if next_state='awaiting_go' then return w.data; end if;
    if w.state in ('succeeded','superseded') then return w.data; end if;
    update public.go_work set state=next_state,data=p_data||jsonb_build_object('id',w.id)
      where id=w.id returning * into w;
  else
    if next_state<>'awaiting_go' then raise exception 'not_found'; end if;
    insert into public.go_work values((p_data->>'id')::uuid,p_owner,(p_data->>'event_id')::uuid,
      (p_data->>'event_revision')::integer,k,next_state,p_data) returning * into w;
  end if;
  return w.data;
end $$;

create function public.organizer_put_operation(p_owner uuid,p_data jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare o public.operations; a public.approvals; next_state text:=p_data->>'state'; n integer; begin
  perform public.organizer_current(p_owner,(p_data->>'event_id')::uuid,(p_data->>'event_revision')::integer);
  select * into a from public.approvals where id=(p_data->>'approval_id')::uuid and owner_id=p_owner
    and event_id=(p_data->>'event_id')::uuid and event_revision=(p_data->>'event_revision')::integer;
  if not found then raise exception 'needs_review'; end if;
  if p_data->>'kind'='gmail_send' and a.action='draft_only' then raise exception 'needs_review'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_data->>'idempotency_key',0));
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
    if next_state='running' and o.state='running' then raise exception 'operation_in_progress'; end if;
    -- Ambiguous Gmail create/send must reconcile before another attempt; never blindly re-send.
    if next_state='running' and o.state='failed' and o.kind in ('gmail_draft','gmail_send')
      and o.error_code is distinct from 'integration_not_connected' then
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

create function public.organizer_publish_asset(p_owner uuid,p_expected integer,p_data jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare a public.artifacts; c public.generated_content; begin
  perform public.organizer_current(p_owner,(p_data->>'event_id')::uuid,p_expected);
  if (p_data->>'owner_id')::uuid<>p_owner or (p_data->>'event_revision')::integer<>p_expected then
    raise exception 'revision_conflict';
  end if;
  select * into c from public.generated_content where id=(p_data->>'go_generation_id')::uuid
    and event_id=(p_data->>'event_id')::uuid and event_revision=p_expected and producer='superhuman_go';
  if not found or (p_data->>'review_state'='reviewed' and c.state<>'ready') then raise exception 'needs_review'; end if;
  update public.artifacts set is_current=false where event_id=(p_data->>'event_id')::uuid and kind=p_data->>'kind';
  insert into public.artifacts(event_id,event_revision,kind,storage_path,content_hash,provider_design_id,
    exported_version_id,data,is_current)
  values((p_data->>'event_id')::uuid,p_expected,p_data->>'kind',p_data->>'object_key',p_data->>'sha256',
    p_data->>'canva_design_id',p_data->>'canva_export_id',p_data,true)
  on conflict(storage_path) do update set is_current=true returning * into a;
  if a.content_hash<>p_data->>'sha256' or a.event_id<>(p_data->>'event_id')::uuid then
    raise exception 'idempotency_conflict';
  end if;
  return a.data;
end $$;

create function public.organizer_record_rsvp(p_owner uuid,p_data jsonb) returns void
language plpgsql security invoker set search_path='' as $$
declare e public.events; observation text; begin
  e=public.organizer_current(p_owner,(p_data->>'event_id')::uuid,null);
  if (p_data->>'event_revision')::integer>e.revision then raise exception 'revision_conflict'; end if;
  if p_data->>'status' not in ('attending','maybe','not_attending','no_response','needs_review')
    or p_data->>'source' not in ('calendar','email') then raise exception 'invalid_rsvp'; end if;
  observation=md5(p_owner::text||p_data::text);
  insert into public.rsvps(event_id,invitee_id,status,source,source_message_id,observed_at,event_revision,data,observation_key)
  values(e.id,(p_data->>'invitee_id')::uuid,p_data->>'status',p_data->>'source',
    -- Original schema unique key is retained; observation hash keeps conflicting histories separate.
    (p_data->>'source_id')||':'||observation,(p_data->>'observed_at')::timestamptz,
    (p_data->>'event_revision')::integer,p_data,observation) on conflict(observation_key) do nothing;
end $$;

create function public.organizer_content_immutable() returns trigger
language plpgsql security invoker set search_path='' as $$ begin
  if new.id<>old.id or new.event_id<>old.event_id or new.event_revision<>old.event_revision
    or new.body<>old.body or new.subject is distinct from old.subject or new.producer<>old.producer
    or new.kind<>old.kind or new.provenance<>old.provenance then raise exception 'idempotency_conflict'; end if;
  return new;
end $$;
create trigger immutable_content before update on public.generated_content
for each row execute function public.organizer_content_immutable();

-- Cross-table tenant integrity even when calling the Data API directly.
create function public.organizer_validate_child() returns trigger
language plpgsql security invoker set search_path='' as $$
declare expected integer; begin
  expected=case when tg_table_name='inclusion_facts' then (to_jsonb(new)->>'revision')::integer
    else (to_jsonb(new)->>'event_revision')::integer end;
  if tg_op='INSERT' and expected is not null and tg_table_name<>'rsvps' and not exists(
    select 1 from public.events where id=new.event_id and revision=expected) then raise exception 'revision_conflict'; end if;
  if tg_table_name='rsvps' and not exists(select 1 from public.invitees where id=new.invitee_id and event_id=new.event_id) then
    raise exception 'forbidden';
  end if;
  if tg_table_name in ('go_work','approvals','provider_bindings','inbound_replies') then
    if not exists(select 1 from public.events where id=new.event_id and owner_id=new.owner_id) then raise exception 'forbidden'; end if;
  end if;
  return new;
end $$;
do $$ declare t text; begin
  foreach t in array array['rsvps','go_work','approvals','provider_bindings','inbound_replies',
    'generated_content','artifacts','inclusion_facts'] loop
    execute format('create trigger validate_child before insert or update on public.%I '
      ||'for each row execute function public.organizer_validate_child()',t);
  end loop;
end $$;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('event-assets','event-assets',false,10000000,array['text/html','image/png'])
on conflict(id) do update set public=false,file_size_limit=10000000,allowed_mime_types=excluded.allowed_mime_types;
create policy event_assets_read on storage.objects for select to authenticated using (
  bucket_id='event-assets' and (storage.foldername(name))[1]=(select auth.uid())::text and
  exists(select 1 from public.events where id::text=(storage.foldername(name))[3] and owner_id=(select auth.uid()))
);
create policy event_assets_insert on storage.objects for insert to authenticated with check (
  bucket_id='event-assets' and (storage.foldername(name))[1]=(select auth.uid())::text and
  (storage.foldername(name))[2]='events' and exists(select 1 from public.events
    where id::text=(storage.foldername(name))[3] and owner_id=(select auth.uid())
    and 'r'||revision::text=(storage.foldername(name))[4])
);
-- No UPDATE policy: exports are immutable snapshots. Existing bytes must be read/hash checked.
do $$ declare f record; begin
  for f in select oid::regprocedure as sig from pg_proc where pronamespace='public'::regnamespace
    and proname like 'organizer_%' loop
    execute format('revoke all on function %s from public,anon',f.sig);
    execute format('grant execute on function %s to authenticated,service_role',f.sig);
  end loop;
end $$;
