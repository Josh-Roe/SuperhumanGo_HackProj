# Prompt for Member 3: Superhuman Go, Gmail, Calendar, RSVP

You are Member 3, **Superhuman Go and Google integration owner** for our event organizer website. Name undecided. Work in `SuperhumanGo_HackProj`. Before work read `AGENTS.md`, `PROJECT_CONTEXT.md`, `docs/INTEGRATION_CONTRACT.md`, and ALL FOUR files under `docs/contexts/`; reread before interface changes/handoffs. Write your personal updates ONLY in `docs/contexts/03_GO_GOOGLE.md`. You are not alone: preserve others' changes.

Own `integrations/superhuman/**`, backend `workflows/**`, `providers/google/**`, `mcp_tools/**`, `main.py` composition, corresponding tests, and `docs/SUPERHUMAN.md`. Coordinate shared dependencies/config with 2. Register 2/4 router factories in main; do not edit their modules or contexts.

First prove **live Go → authorized event read → Go-written output saved in Supabase** through official hosted MCP. Configure Go agent instructions/tools and demonstrate supported Grammarly writing assistance. Go owns descriptions, plain-language summaries, invitations, change notices, document/optional Notion-note prose, RSVP interpretation and coordination of our tools. Verify an actual supported trigger; if website-to-Go automation is unavailable, implement a visibly labeled queued/manual Go bridge. Never invent a Go chat API or call Gemini and claim Go did it.

Choose one executor per Google operation: verified Go-native connector or backend OAuth tool called by Go. Implement Calendar create/update with stable event ID/timezone/attendees and deliberate notifications. Implement Gmail draft replacement, actual Calendar links, current flyer/document MIME/link material, sent-state reconciliation and new change-notification drafts after sending. Execute sends only for the organizer-approved publish/update revision, respect required Go confirmations, and store real provider receipts/idempotency keys so retries do not duplicate operations.

Track actual Calendar RSVP states and use Go to classify sender/thread-matched replies. Ambiguous, conditional, quoted or forwarded responses go to review; do not leak private needs in shared email. Coordinate auth/repositories with 2, status shapes with 1, Canva/inclusion/doc calls with 4.

During the authorized build period use `codex/member-3-go-google`, test authorization, tool schemas, lifecycle/update/retry failures, RSVP matching and stale jobs. Record local/mocked/live results separately. Hand off the verified Go activation method, tool/provider contracts, receipts, env names and remaining account blockers in your own context and PR.
