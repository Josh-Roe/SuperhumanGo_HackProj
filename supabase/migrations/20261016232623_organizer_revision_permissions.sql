-- An organizer may invalidate an old artifact pointer on an event revision.
-- Setting a current pointer or modifying trusted provider metadata remains server-only.
grant update(is_current) on public.artifacts to authenticated;
create policy organizer_can_invalidate on public.artifacts as restrictive
for update to authenticated using (true) with check (is_current=false);
