-- Gemini and Notion are out of scope: Superhuman Go (with its built-in Grammarly) writes all prose.
-- Fails loudly if any existing row still uses a removed kind or producer.
alter table public.generated_content drop constraint content_kind_check;
alter table public.generated_content add constraint content_kind_check check (kind in
 ('description','summary','invitation','change_notice','document','flyer_brief',
  'flyer_copy','event_document','plain_language_summary','flyer_alt_text'));
alter table public.generated_content drop constraint content_producer_check;
alter table public.generated_content add constraint content_producer_check
 check (producer in ('superhuman_go','organizer'));
