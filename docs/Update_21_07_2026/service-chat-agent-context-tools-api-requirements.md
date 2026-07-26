# BE spec: Context-aware agent for the global service chat

## Status

- Priority: P0 for page-aware responses; P1 for generalized tool actions.
- FE already provides a global floating chat on every `/services/*` route.
- Existing chat streaming, emotion analysis, crisis routing, and `exercise_card` remain supported.
- This document extends the current endpoint; it does not require a second chatbot endpoint.

## Product goal

The assistant is no longer presented as a separate sidebar feature. It follows the user across the service area and should understand the current surface without pretending to know data it was not authorized to read.

Examples:

- On Mood, help interpret the latest check-in and choose one next step.
- On Assessment, explain an existing result without diagnosing.
- On Exercises, recommend or launch a short exercise based on the conversation.
- On Journal or Thought Records, only read private content after explicit consent.

## Extend the existing request

### `POST /api/v1/chat/conversations/{conversation_id}/messages`

Current request:

```json
{
  "content": "Tôi không biết nên làm gì tiếp theo"
}
```

Required request:

```json
{
  "content": "Tôi không biết nên làm gì tiếp theo",
  "context": {
    "route": "/services/mood",
    "surface": "mood",
    "resource_id": null,
    "consent_token": null
  }
}
```

### Context fields

| Field           | Type           | Required | Rules                                                                         |
| --------------- | -------------- | -------- | ----------------------------------------------------------------------------- |
| `route`         | string         | No       | Relative `/services/*` route, maximum 200 characters.                         |
| `surface`       | enum           | No       | Allowlisted value described below. Do not trust arbitrary tool names from FE. |
| `resource_id`   | string or null | No       | Identifier of the item currently open, when applicable.                       |
| `consent_token` | string or null | No       | Short-lived server-issued token for sensitive reads.                          |

Allowed `surface` values:

```text
dashboard
mood
assessment
exercises
exercise_detail
sounds
journal
thought_record
safety_plan
library
community
profile
settings
```

Unknown or invalid context must be ignored rather than inserted into the model prompt.

## Context handling

The backend builds trusted context from `current_user`, `surface`, and `resource_id`. The frontend must never send raw mood history, assessment answers, journal content, safety-plan content, or chat-derived risk scores as context.

Minimum trusted context by surface:

| Surface          | Server-side context allowed by default                                            |
| ---------------- | --------------------------------------------------------------------------------- |
| `mood`           | Latest mood entry and deterministic mood summary.                                 |
| `assessment`     | Latest completed result, score band, and approved interpretation.                 |
| `exercises`      | Available exercises and recent completion metadata.                               |
| `sounds`         | Available sounds and non-sensitive listening metadata.                            |
| `journal`        | No entry content without explicit consent.                                        |
| `thought_record` | No record content without explicit consent.                                       |
| `safety_plan`    | Safety resource availability only; do not expose private plan content by default. |

Page context is supporting information. The latest user message remains the primary instruction.

## Agent tools

Phase one tool allowlist:

```text
get_latest_mood_entry(user_id)
get_mood_summary(user_id, days)
get_latest_assessment_result(user_id)
find_suitable_exercises(emotion, energy, max_minutes)
get_exercise(exercise_slug)
get_available_sounds(intent)
create_mood_checkin(user_id, payload, confirmation_token)
log_exercise_completion(user_id, payload, confirmation_token)
```

Rules:

- Read tools derive `user_id` from JWT, never from model arguments.
- Mutation tools require explicit user confirmation and a short-lived confirmation token.
- The model cannot construct URLs. The server maps validated resources to frontend routes.
- Limit each assistant turn to one primary recommended action.
- Tool errors degrade to a text response and must not terminate the SSE stream with an HTTP 500.

## Generalized SSE action contract

Keep existing `chunk`, `done`, and `error` events. Extend the final `done` event with an `actions` array while retaining `exercise_card` for backward compatibility.

```json
{
  "type": "done",
  "message_id": 482,
  "emotion": "anxious",
  "emotion_confidence": 0.82,
  "crisis_level": 0,
  "suggest_checkin": false,
  "exercise_card": null,
  "actions": [
    {
      "id": "exercise:coherent-breathing",
      "type": "exercise",
      "title": "Thở đều trong vài phút",
      "description": "Một nhịp chậm để cơ thể dịu lại.",
      "url": "/services/exercises/coherent-breathing",
      "requires_confirmation": false,
      "payload": null
    }
  ],
  "context_used": {
    "surface": "mood",
    "resource_id": null
  }
}
```

### Action fields

| Field                   | Type                                                                           | Rules                                                        |
| ----------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `id`                    | string                                                                         | Stable within the response.                                  |
| `type`                  | `exercise \| mood_checkin \| journal \| sound \| assessment \| safety \| link` | Closed enum.                                                 |
| `title`                 | string                                                                         | Maximum 80 characters.                                       |
| `description`           | string or null                                                                 | Maximum 140 characters.                                      |
| `url`                   | string or null                                                                 | Same-origin relative route from a server allowlist.          |
| `requires_confirmation` | boolean                                                                        | Must be true for any mutation.                               |
| `payload`               | object or null                                                                 | Structured UI data; never executable code or arbitrary HTML. |

Return at most two actions and highlight only the first as primary.

## Emotion analysis

Keep the current fields in the final SSE event:

- `sentiment`
- `emotion`
- `emotion_confidence`
- `depression_risk`
- `crisis_level`
- `suggest_checkin`

Emotion is an uncertain signal, not a diagnosis. Do not persist or show low-confidence labels below the existing threshold unless needed for aggregate safety processing.

## Consent for sensitive records

Journal and Thought Record content require an explicit UI confirmation before reading.

Suggested flow:

1. Agent returns a `request_consent` action naming the exact record and purpose.
2. User confirms in UI.
3. FE requests a short-lived, one-use consent token.
4. The next message includes that token and `resource_id`.
5. BE validates ownership, scope, expiry, and records an audit event.

Do not treat opening the Journal page as consent to read journal entries.

## Safety

- Run deterministic crisis detection before any model or tool call.
- Crisis routing overrides page context and normal recommendations.
- Never return a normal exercise as the primary action for a crisis-level message.
- Do not include raw private notes in application logs or model observability by default.
- Preserve the current behavior where level-three crisis messages skip the model response.

## Compatibility and rollout

1. Add optional `context` to `SendMessageRequest` and ignore it behind a feature flag initially.
2. Build trusted context loaders for Mood, Assessment, and Exercises first.
3. Add `actions` to the final SSE event while continuing to populate `exercise_card`.
4. Roll out consent-based Journal and Thought Record tools separately.
5. After FE adoption is measured, deprecate `exercise_card` in a later API version.

## Acceptance criteria

- A message sent from Mood can use the authenticated user's latest mood without the FE sending raw mood data.
- The same user message from different surfaces may produce different supporting context, with the current route recorded in `context_used`.
- Invalid surface, resource ID, or cross-user resource access is rejected or ignored safely.
- Existing clients sending only `{ "content": string }` continue to work.
- Existing SSE chunk rendering remains unchanged.
- An exercise recommendation returns a validated internal route and a structured action.
- A mutation cannot run without explicit confirmation.
- Journal and Thought Record content cannot be read merely because the user is on those pages.
- Crisis behavior remains deterministic and takes precedence over agent tools.
