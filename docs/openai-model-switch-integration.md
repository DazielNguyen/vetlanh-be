# BE Integration Doc — LLM Provider Switch to OpenAI

**Date:** 2026-07-27
**Requested by:** FE Team (Phase 8 of `plans/gaming-companion-redesign/plan.md`)
**Status:** 📋 Docs-only — no frontend code change, no API key included in this document or any commit.
**Context:** The chat/agentic features currently run on whatever LLM backend already powers them today. This doc specifies the contract the frontend depends on, so the backend team can switch the underlying model to an OpenAI model without breaking any FE surface. It does not request or assume any particular current provider.

---

## Purpose

This is a **contract-preservation** document, not a redesign. Its only job is: after the backend switches to an OpenAI model, everything below must still behave exactly as described, unless a section explicitly says a difference is acceptable.

The frontend does not care which model or provider generates a response. It only cares that:
1. The request/response shapes below are unchanged.
2. The specific fields the UI reads (see each surface) keep the same meaning.
3. Any new latency/streaming/moderation behavior is called out so FE can adapt if needed (see [Behavior Differences](#behavior-differences-to-expect-after-a-model-switch)).

---

## Surface Inventory

Every place in the current product where AI-generated output is consumed by the frontend:

| # | Surface | Consumes live LLM output today? | Contract source |
|---|---|---|---|
| 1 | Global service chat (streaming conversation) | ✅ Yes | This doc, [§1](#1-global-service-chat-streaming) |
| 2 | Guided conversational flows (Thought Record / Safety Plan, Phase 4) | ❌ No — scripted wizard, not a live model call (see note below) | This doc, [§2](#2-guided-conversational-flows-phase-4--not-yet-a-real-llm-consumer) |
| 3 | Proactive AI check-ins (Phase 5) | ✅ Yes (message text is BE/LLM-generated; delivery is a plain SignalR event) | `docs/be-specs/checkins-api-requirements.md`, this doc [§3](#3-proactive-ai-check-ins-phase-5) |
| 4 | Personalized dashboard recommendation (Phase 6) | ✅ Yes (title/rationale are BE/LLM-derived) | `docs/be-specs/recommendations-api-requirements.md`, this doc [§4](#4-personalized-dashboard-recommendation-phase-6) |
| 5 | Community 1-1 matching (Phase 7) | ❌ No — pairing/moderation logic, not generative text | `docs/be-specs/community-matching-api-requirements.md` (not affected by this switch) |

Row 5 is listed for completeness per the plan's phase coverage; it is not a generative-AI surface and needs no changes for a model switch.

---

## 1. Global service chat (streaming conversation)

**Endpoint:** `POST api/v1/chat/conversations/{conversation_id}/messages` — Server-Sent Events response.

This is the one surface where the frontend directly renders live, token-by-token model output, so it is the most sensitive to a provider switch.

### Request the frontend sends today
```json
{ "content": "Tôi không biết nên làm gì tiếp theo" }
```
(An optional `context` object — `route`, `surface`, `resource_id`, `consent_token` — is also sent per `docs/be-specs/service-chat-agent-context-tools-api-requirements.md`; unrelated to the model switch, listed here only so the backend doesn't drop it during the swap.)

### SSE events the frontend parses (`lib/api/services/fetchChat.ts`, `types/chat.ts:StreamChunk`)

| Event `type` | Fields the FE reads | Used for |
|---|---|---|
| `chunk` | `content` (string, incremental text) | Appended to `streamingText` as it arrives — this is the visible "typing" effect. Must keep arriving as an incremental stream, not a single final blob, or the UI reads as frozen until the end. |
| `done` | `message_id`, `exercise_card`, `sentiment`, `suggest_checkin`, `crisis_level`, `emotion`, `emotion_confidence`, `depression_risk`, `phq_estimate` | Terminates the stream; each field below has a specific UI consequence. |
| `error` | `detail` (string) | Surfaced to the user as "Gửi tin nhắn thất bại, vui lòng thử lại." and terminates the stream without crashing it (per the existing chat-agent contract's "tool errors must not terminate the SSE stream with an HTTP 500" rule). |

### `done` fields the model switch must keep producing correctly

| Field | FE behavior if this regresses |
|---|---|
| `exercise_card` | Rendered as a structured card in the conversation. If this stops being populated when appropriate, users lose the in-chat exercise recommendation entirely (silent regression, not an error). |
| `suggest_checkin` (`boolean`) | Triggers a "would you like to check in?" prompt. |
| `emotion` / `emotion_confidence` | FE only surfaces emotion when `emotion !== "neutral"` **and** `emotion_confidence >= 0.55` (`hooks/useStreamChat.ts`). If the new model's confidence scores are calibrated differently (e.g. systematically lower), this threshold may need re-tuning — flag if so rather than silently under-reporting. |
| `depression_risk` | Only surfaced when not `"none"`. Same calibration caution as above. |
| `crisis_level` | **Safety-critical.** `crisis_level >= 3` makes the FE append a crisis/hotline card to the conversation (`hooks/useStreamChat.ts`). **Important nuance for the backend team:** the FE does *not* suppress or discard any streamed assistant text when this fires — it is additive, not a replacement. The current behavior only reads cleanly as "crisis card instead of AI text" because the *existing* backend is assumed to withhold assistant text on a level-3 turn in the first place; the FE has no client-side logic enforcing that. **If the OpenAI-backed integration ever emits both `crisis_level >= 3` and non-empty streamed text on the same turn, the user will see both the assistant's text bubble and the crisis card together** — the backend must continue to withhold text on level-3 turns to preserve today's UX. Separately, `crisis_level` itself must remain a **deterministic, non-model-generated** signal per the existing chat-agent contract ("Run deterministic crisis detection before any model or tool call... Preserve the current behavior where level-three crisis messages skip the model response.") — i.e. the OpenAI switch must not make crisis detection itself a function of the new model's judgment. Call out explicitly if crisis detection does not live outside the LLM call in the current implementation, since that would change this document's risk assessment. |
| `phq_estimate` | Present in the type but not currently asserted on by any FE consumer found in this repo — preserve the field regardless in case a future FE build reads it. |

### What the FE does **not** care about
Model name, token count, temperature, system prompt content, or any other model-internal detail — none of this crosses the wire to the FE today and none of it should start to.

---

## 2. Guided conversational flows (Phase 4) — not yet a real LLM consumer

Per `plans/gaming-companion-redesign/phase-04-guided-conversational-flows.md`, this surface is implemented as a **pre-written, scripted question sequence** — no live LLM call happens during the flow. The companion animates and a running summary displays, but the "conversation" is fixed copy, not model output.

**Nothing about this surface changes as part of an OpenAI switch.** It is listed here only because Phase 4 explicitly deferred real crisis-language detection on guided-flow free text until "a real LLM turn is in the loop" and pointed back to this doc. If/when this flow is upgraded to use live model calls (a separate, not-yet-scoped effort), it would consume the same `POST .../messages` SSE contract as [§1](#1-global-service-chat-streaming) — there is no second chat endpoint. No action needed from the backend for this switch; noted for completeness so a backend engineer doesn't go looking for a second guided-flow-specific contract.

---

## 3. Proactive AI check-ins (Phase 5)

Full contract: `docs/be-specs/checkins-api-requirements.md`. Relevant to a model switch: the `message` field in both the SignalR event (`ReceiveProactiveCheckIn`) and the REST catch-up endpoint (`GET api/v1/checkins/pending`) is a short, personalized Vietnamese sentence presumed to be LLM-generated server-side from trigger data (e.g. "3 days without a mood entry"). The frontend renders this string as-is with no parsing or expected structure beyond "a short displayable sentence" — a model switch only needs to keep producing a string of comparable length and tone (empathetic, Vietnamese, non-clinical-alarming). No field shape changes needed.

---

## 4. Personalized dashboard recommendation (Phase 6)

Full contract: `docs/be-specs/recommendations-api-requirements.md`. Relevant to a model switch: `GET api/v1/dashboard/personalized-recommendation` returns `{ title, rationale, url }` or `null`. `title` and `rationale` are presumed LLM/derivation-logic output; `url` must remain a validated same-origin relative path resolved server-side (the frontend rejects anything else as a defense-in-depth measure — this is unrelated to the model itself but is called out so the new model's output pipeline doesn't accidentally start emitting a raw/unvalidated URL). No field shape changes needed for the switch itself.

---

## API Key Handling

- **No API key, secret, or credential — real, placeholder, or example-formatted — appears anywhere in this document, in this repository, or in any commit related to this plan.**
- The OpenAI API key must be supplied to the backend **out-of-band** (i.e., not through this repo, not through a pull request, not pasted into any chat/ticket that becomes part of source history) and stored using the backend's existing secret-management mechanism (environment variable injected at deploy time, or a secret-manager reference such as AWS Secrets Manager / GCP Secret Manager / Vault — whichever the backend already uses for its other credentials).
- This frontend repository has no `OPENAI_*` or model-provider environment variable today (confirmed: no such reference exists anywhere in `lib/env.ts` or elsewhere in the codebase as of this doc's writing) and does not need one — the frontend never talks to OpenAI directly; it only talks to this app's own backend, which is the sole owner of the provider credential.

---

## Behavior Differences to Expect After a Model Switch

The frontend cannot detect *which* model produced a response, but it can be affected if the following change:

| Dimension | What could change | FE impact if it does |
|---|---|---|
| **Streaming granularity** | A new model/provider may emit larger or smaller text chunks per SSE `chunk` event than today. | None if chunks keep arriving incrementally — the FE just appends `content` as it comes (`hooks/useStreamChat.ts`). Only a problem if the backend switches to buffering the *entire* response into a single final `chunk`/`done`, which would make the UI feel frozen for the full generation time instead of streaming. Call this out explicitly if the new integration does this. |
| **Response latency** | OpenAI models may respond faster or slower than the current provider for a given prompt. | The FE has a **hard 30-second client-side timeout** (`hooks/useStreamChat.ts`: "Hard 30s timeout — prevents permanently frozen input if BE hangs") that aborts the stream and shows "AI đang xử lý quá lâu, vui lòng thử lại." If the new model is meaningfully slower on average, real users will hit this timeout more often — worth confirming expected p95 latency before rollout so FE can decide whether 30s needs to become configurable. |
| **Content moderation behavior** | OpenAI's built-in moderation/refusal behavior differs from whatever the current provider does — it may refuse or soften responses to prompts the current model does not. | No FE-side handling exists today for a "the model refused to answer" case distinct from a normal response or the existing `error` SSE event. If the new integration can produce a refusal, it should be surfaced through the existing `error` event (with an appropriate `detail` message) rather than as a normal assistant text turn, so the FE's existing error-handling path (not a new one) covers it. |
| **Emotion/risk-score calibration** | `emotion_confidence`, `depression_risk`, and any other confidence-style output may be numerically calibrated differently by a new model. | See the `emotion`/`depression_risk` row in [§1](#1-global-service-chat-streaming) — FE thresholds (`>= 0.55`) may need re-tuning after rollout if the new model is systematically over- or under-confident relative to today's calibration. |

---

## Cross-References

- `docs/be-specs/service-chat-agent-context-tools-api-requirements.md` — the base chat/SSE contract this doc extends for the model-switch angle specifically; read that doc first for the full request/response shape, agent tools, and consent flow.
- `docs/be-specs/checkins-api-requirements.md` — Phase 5, full check-in contract; this doc only adds the "the message text is presumably LLM output" note.
- `docs/be-specs/recommendations-api-requirements.md` — Phase 6, full recommendation contract; same relationship.
- `docs/be-specs/community-matching-api-requirements.md` — Phase 7; not a generative-AI surface, listed in the inventory above for completeness only, no action needed here.
- `plans/gaming-companion-redesign/phase-04-guided-conversational-flows.md` — explains why guided flows are *not* a live-LLM surface today and why this doc is the forward-reference for when/if they become one.
- `plans/gaming-companion-redesign/plan.md` — overall plan; this document closes out Phase 8, the plan's final phase.

---

## Acceptance Criteria (for the backend team completing the switch)

- [ ] The `chunk` / `done` / `error` SSE event contract in [§1](#1-global-service-chat-streaming) is unchanged after the switch — existing FE code requires no changes to keep working.
- [ ] `crisis_level` continues to be produced by deterministic logic that runs regardless of which generative model is behind the conversational response (per the existing chat-agent contract's crisis-detection requirement) — confirm this explicitly, since it is the one field where "the model changed" must never mean "crisis detection changed."
- [ ] The backend continues to withhold assistant text on any turn where `crisis_level >= 3` — the FE does not enforce this itself (see [§1](#1-global-service-chat-streaming) crisis_level row), so this must remain a backend guarantee after the switch, not become an assumption nobody owns.
- [ ] Streaming remains incremental (`chunk` events arrive progressively), not buffered into one final blob.
- [ ] If the new model can refuse/decline a response, that case is surfaced via the existing `error` SSE event, not a silent empty response or a new event type the FE doesn't parse.
- [ ] No API key or secret is present anywhere in this repository's history as a result of this integration.
- [ ] `docs/be-specs/checkins-api-requirements.md` and `docs/be-specs/recommendations-api-requirements.md` need no contract changes as a direct result of the model switch (their field shapes are provider-agnostic) — confirm rather than assume, in case the new model changes output length/format enough to need a rationale/message length cap adjustment.

Once the checklist above is confirmed by the backend team, this closes the last open phase of `plans/gaming-companion-redesign/plan.md`.
