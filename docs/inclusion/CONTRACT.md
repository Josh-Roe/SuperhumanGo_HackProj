# Inclusion review contract

Member 4, 2026-10-16. Callable: `services.inclusion.check_inclusion(event, facts, owner_id=validated_owner, summary=go_summary)` → `InclusionReport`. Pure local rules; no hidden LLM, holiday database or external venue lookup. Member 2 persists owner-scoped inputs/reports by revision. Member 3 obtains the summary through Superhuman Go; Member 1 supplies the organizer review UI.

`Fact` is `{value: "yes" | "no" | "unknown", source?: Source}`. Source has `label`, timezone-aware `observed_at`, `confirmed_by`, optional HTTPS/HTTP `url`. Unsourced yes/no remains operationally unknown. Store the original fact as entered; the checker never fills unknowns with invented guarantees. A dated source is a traceable assertion, not independent proof. Ask again when facts become stale or the venue changes.

`InclusionInput` fields: `step_free_entrance`, `above_ground_floor`, `elevator`, `food_served`, `diet_options`, `diet_source`, private `required_diets`, `captions`, `loud_sound`, `strobes`, `observances_selected`, `observances`.

| Category | Finding behavior |
| --- | --- |
| Plain language | Needs Go summary and explicit organizer review; records generation ID. Review clarity/actionability manually; no readability score or universal comprehension claim. |
| Step-free entrance | Sourced yes recorded, no attention, unknown/unsourced unknown. Organizer must confirm the actual route. |
| Elevator | Sourced ground-floor answer records that fact; unknown floor remains unknown. For upper floors, sourced elevator yes/no yields recorded/attention and preserves both sources. Ground floor does not prove step-free access. |
| Diet | Unknown if food/options are unconfirmed. Sourced no-food recorded. Missing required option yields attention. Matching option labels still needs attendee confirmation; no allergy/cross-contamination guarantee. Individual restrictions never appear in findings/public assets. |
| Religious observances | Ask which observances to check. Accept explicitly supplied, sourced start/end instants covering the applicable local interval, including any sunset boundaries. Check actual interval overlap in aware timestamps. Empty/unselected coverage remains visible; no overlap means only no overlap in the supplied intervals. Never infer religion or claim a comprehensive holiday scan. |
| Captions | Sourced yes recorded, no attention, unknown preserved. Organizer checks whether captions cover the actual program. |
| Loud sound / strobes | Sourced yes attention, no recorded, unknown preserved. A warning is for organizer action/disclosure, not automatic event rejection. |

Report: `event_id`, `event_revision`, `audience="organizer_private"`, `findings[]`, `requires_review`, `certification=false`. Each finding has `category`, `status` (`recorded`, `attention`, `unknown`, `needs_review`), machine-readable `reason`, `sources[]`, optional conflict names and Go generation ID. `recorded` means a sourced fact was recorded; never label it “certified accessible.”

Member 1 should translate reason codes into static interface explanations/questions, show sources/date and unknowns in text, avoid color-only indicators, and provide organizer acknowledgment plus editable facts. Static UI labels are not generated event prose. Requests for new summary/disclosure/event wording go to Member 3's Go queue; do not invent it in the client. Acknowledgments belong to Member 2's review records for the exact revision. This checker reports findings; it does not grant publication approval.

No route is registered here. Require authenticated event ownership before loading sensitive inputs. `repr=False` on dietary requirements is only accidental-log protection: serialized inputs still contain sensitive values. Do not log, publish or attach raw inputs/reports to invitations. Public event material includes only organizer-approved general accommodation statements from Go, without attendee data. Parking, restrooms, Forms and participant-specific assessment remain outside this implementation.
