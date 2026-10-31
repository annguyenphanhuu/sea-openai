# P4 implementation spec: bounded browser voice through A1

Date: 2026-10-31. Status: prepared for independent review; no implementation authorization is implied by this file. Sources and verified provider schemas: [research](../research/realtime-voice-p4.md).

## Intended behavior and design inference

The customer clicks **Gọi**, permits microphone access, speaks Vietnamese, and receives spoken A1 replies. This is an inbound customer request, not an additional proactive contact. Existing proactive contact limits remain unchanged. Realtime transcribes/relays the request through the sole tool `send_to_a1`; A1 remains the business decision maker. Model remains `gpt-realtime`.

**Design inference:** keep both the standard API key and temporary Realtime key on the backend. Browser WebRTC media still travels directly to OpenAI; the backend relays only SDP signaling and A1 tool HTTP requests. This preserves browser WebRTC and temporary-key authentication while avoiding client-visible reusable credentials. It differs from the official browser example only in where the authenticated SDP POST occurs. No sideband WebSocket is required for this compact design.

The app uses the explicitly supplied accounting rate USD 0.30/minute, a 240-second maximum per call, and USD 2.00 aggregate allowance. These are app accounting rules, not a guarantee about the OpenAI invoice. Charge time starts when the temporary key is created and ends on confirmed provider termination. Server deadline includes setup time.

## Ownership and integration boundary

- Backend implementation: new `platform_huy/voice.py` (provider/session/budget manager), optional task-owned runtime migration module, platform adapters in `demo_flow.py`, HTTP routes in `serve_ui.py`, and dedicated `acceptance_huy/test_voice_p4.py`. All SQLite/runtime writes remain on their owning event loop; provider I/O does not hold SQLite transactions.
- UI implementation: `platform_huy/ui_prototype/live.html` only, plus its assigned browser evidence/tests. No backend file edits from UI worker.
- Controller integrates and owns Git. Neither worker edits `care_truc`, `contracts`, source data, or another task's tests. Preserve all NEXT/progress/auth and intro statistics.
- Runtime tables live outside source databases under the current runtime path. No MongoDB or external persistence.

## Security and public HTTP interface

All voice routes require the existing presenter authentication plus `X-Voice-Code` matching configured `VOICE_CODE`, checked before session lookup/provider access. Compare secrets safely; missing configuration disables voice with a stable error. The browser asks for the code and retains it in memory only. No secret, provider credential, raw provider error, or SDP enters logs.

`voice_session_id` is opaque. Backend owns its binding to authenticated principal, selected order, Care session, allowance, provider call, and deadline. Neither tool arguments nor a client channel/principal/order override that binding. Require same-origin application requests according to existing auth conventions; do not add permissive CORS.

| Route | Request | Successful response |
| --- | --- | --- |
| `POST /api/voice/session` | JSON `{order_id, request_id}` | JSON `{voice_session_id, status, model, expires_at, deadline_at, allowance_seconds, rate_usd_per_minute:0.3, budget_remaining_usd}` |
| `POST /api/voice/connect` | JSON `{voice_session_id, sdp}` | JSON `{voice_session_id, sdp, status:"active", deadline_at, allowance_seconds}` |
| `POST /api/voice/turn` | JSON `{voice_session_id, response_id, call_id, transcript}` | JSON `{voice_session_id, call_id, a1_text, turn_result}` |
| `POST /api/voice/end` | JSON `{voice_session_id}` | JSON `{voice_session_id, status, charged_usd, reserved_usd, budget_remaining_usd}` |
| `GET /api/voice/state?voice_session_id=...` | Bound session ID | Public status, deadline, charged/reserved/remaining accounting; no keys or provider call ID required by UI |

Stable errors: 401 auth/code, 400 malformed/bounded-input failure, 403 identity binding failure, 409 session state conflict/already connecting/expired, 429 allowance unavailable, 503 provider unavailable/termination uncertain. HTTP 202 is suitable when an accepted termination is still being retried; never represent that as confirmed ended. Bound SDP and transcript sizes explicitly in implementation constants. Use `request_id` to replay session creation without minting/reserving twice; changed payload with the same ID is a conflict.

## Backend lifecycle and signaling

1. Validate auth/code and order access, then atomically reserve available allowance in SQLite. Prepare a customer-origin Care voice session using the adapter below. Persist creation intent before provider I/O.
2. Request `POST /v1/realtime/client_secrets` with standard server key, session type `realtime`, model `gpt-realtime`, audio output, VAD automatic responses disabled, and only `send_to_a1`. Retain returned `value` server-side in memory. Record token creation timing and expiry; do not persist credential plaintext. Return public session metadata only. Connection TTL is an operational setting distinct from the approved duration cap; do not silently restart the accounting timer on connect.
3. Connect atomically claims `ready -> connecting` once. Forward the browser SDP to `POST /v1/realtime/calls`, using the retained temporary key and `Content-Type: application/sdp`. Never accept a caller-supplied provider URL, model, key, or call ID. On success read the provider `Location`, validate/extract the call ID, persist it before returning SDP, erase the temporary key, and activate the server timer.
4. Single-use connect means no second provider call. A repeat with identical session/SDP after successful completion may replay the saved answer; a pending or conflicting repeat returns 409. Never automatically repost an uncertain timed-out provider create request. Timeout/missing Location after possible call creation is an uncertain state with reservation held, not permission for another call.
5. Timer runs independently of browser activity. At the stored deadline it closes A1 admission and calls `POST /v1/realtime/calls/{call_id}/hangup` with the standard key. Manual end uses the same idempotent path. Timer and manual end cannot double-settle.
6. Only confirmed successful provider hangup permits unused allowance release. Hangup failure leaves a durable stopping/uncertain record and full remaining reservation held; retry termination with bounded timeouts, not call creation. Browser teardown does not prove provider hangup.
7. Startup recovery disables new use of orphaned sessions. Persisted call IDs are candidates for immediate hangup; never recreate provider calls. Lost temporary keys mean setup cannot resume. Missing/uncertain call IDs remain visibly unresolved. A server crash/network outage can delay hangup; do not claim a physically guaranteed provider cutoff during an outage.

Because the browser never receives a key and server connect is single-use, it cannot create additional unregistered calls using this app's temporary credential. An ambiguous provider-creation outcome still needs explicit unresolved-state handling.

## Atomic accounting

Use integer microdollars: aggregate limit `2_000_000`, rate `5_000` per second. Reserve at most `1_200_000` for a 240-second call and at most the uncommitted remainder. Reserved plus finalized charges must never exceed `2_000_000`. Use an immediate transaction/CAS for reservation and settlement; a status-only response never changes balance. A reservation shortens the current session allowance if less than 240 seconds remains.

Track elapsed operational time from provider token creation, never simulation ticks. Within a process use monotonic elapsed time; persist UTC audit timestamps/deadlines for restart recovery. Operational time affects voice connection/accounting only, not order eligibility, feed freshness, or NEXT. Settle the metered duration after successful hangup, up to the reserved allowance, without hiding failed/late termination in the provider audit. Integer arithmetic must not add arbitrary whole-minute billing. Precision/rounding is a technical accounting representation to document in tests, not a new minute-minimum business rule.

Maximum normal call: 240 seconds = USD 1.20. Aggregate allowance: 400 seconds at the approved rate. Browser displays estimated elapsed accounting and server-confirmed remaining/reserved amounts distinctly. No browser-supplied elapsed/cost value is authoritative.

**Unresolved failure settlement:** a key may be created but never connected, or provider creation may definitively fail before a call exists. Such a session has no provider call to hang up. The stated rule permits unused release only after successful hangup; this spec therefore does not invent a refund exception. Hold that reservation in an unresolved state until the controller obtains an explicit decision on verifiably never-created calls. A failed token-mint request before token creation is also recorded distinctly; do not pretend it had an active call.

## Existing A1 integration without policy edits

Current contracts use `web_voice`, not literal `voice`. `CareHarness.open_chat` has no channel parameter and defaults to chat; do not use it and relabel the transcript afterward. `CareStore.create_session` already accepts a `SessionState` with explicit `channel="web_voice"` and `opened_by="customer"`.

Add a platform-owned inbound adapter on the Care owner loop. Mirror existing inbound admission: validate request identity, check harness accepting, call existing `harness.authorize`, then use existing `care.storage.create_session` with customer origin, web_voice channel, bound order/principal, and an idempotent open key scoped to the voice session. This creates no `ContactTask` and no `contact_send`; it neither consumes nor bypasses proactive contact quota. Never reuse/mutate an existing chat session. No synthetic user message is necessary merely to open the session.

For each voice turn, revalidate runtime binding and call existing `harness.handle_message` on that dedicated Care session at current simulation time, then drain normal effects as currently required. The request ID is derived from voice session plus tool `call_id`; replay returns the original A1 result and changed transcript conflicts. Preserve existing handoff/cancellation behavior and audit. Do not add voice confirmation semantics or force a pending cancellation to succeed.

Existing Care coin eligibility rejects non-chat/customer-origin requests, and platform financial gate also requires chat. Maintain those gates, reject all coins/voucher execution from voice at the platform integration boundary, and prove no financial ledger/outbox effect under spoken benefit requests. Tool output returns A1's actual rendered reply; it does not fabricate success. No policy, formula, amount, provenance, or financial-key changes.

## Browser turn state machine

UI states: idle, preparing, connecting, listening, awaiting-tool, awaiting-A1, speaking, ending, ended/error. Separate generation IDs invalidate late fetch/events after disconnect or a new session.

On a user gesture request microphone, create peer and `oai-events` channel/listeners, create offer, call the two app endpoints, then apply returned SDP. Remote audio attaches to the player. No key is delivered to browser. At `input_audio_buffer.committed`, request a response forcing `send_to_a1`. Serialize turns; never let an unsolicited free answer precede A1.

Wait for `response.done` with status completed and a completed output item of type `function_call`, name `send_to_a1`, valid JSON `{transcript}`, and a previously unseen `call_id`. `response.function_call_arguments.done` alone is insufficient because it also fires on cancellation. Send the transcript through `/api/voice/turn`, then emit `conversation.item.create` with `function_call_output`, matching `call_id`, and JSON-encoded `{a1_text}`. Follow with `response.create` using `tool_choice:"none"`, audio output, and instructions to read only that text verbatim. Keep tool inputs untrusted; reject unexpected tools and malformed arguments.

Without sideband, the backend cannot cryptographically authenticate browser-forwarded Realtime events. Completed-response validation is an honest-client protocol check, not provenance authority; all backend effects remain safe even for forged tool HTTP calls because the server binds channel/customer/order and preserves policy gates.

Display canonical A1 text and incoming transcript separately. Output speech transcript events are observability, not the authoritative reply. Direct streamed audio plus a read-verbatim instruction cannot guarantee exact spoken output; if exact pre-playback validation becomes mandatory, that requires additional audio buffering/readback scope. Do not claim that guarantee in UI or test results.

Hangup invokes app `/end` and immediately stops microphone tracks, peer, data channel, and playback. Client deadline also cleans up locally, while the independent server timer handles provider termination. Poll public state until confirmed ended or display termination uncertainty. On refresh/close request cleanup best effort; do not depend on unload delivery. UI shows AI voice and the approved accounting rate/limit, not implementation credentials.

## Verification and completion evidence

Backend RED/GREEN: auth before provider I/O; token never returned/logged; concurrent reserve <= USD 2; creation/connect idempotency; setup time consumes allowance; provider-call ID stored before answer; timed/manual hangup settle once; failure holds funds; recovered call hangup; foreign session rejection; exact `web_voice`/customer binding; fabricated channel/order ignored or rejected; benefit requests produce no financial effect; transcript replay stable.

UI tests: completed tool response only; canceled/malformed/duplicate events cannot double-submit; A1 text returned as function output; readback disables tools; late responses discarded after end; all media tracks stop; network/permission failures leave clear state. Existing full repository suite must still pass, including NEXT/auth/coin tests. Evidence belongs in `.scratch/runs/task-voice-p4/` with actual commands/output, not invented success.

User agreed to a real manual Chrome test. Validate actual microphone permission, Vietnamese input, audible A1 readback, denied coins/voucher, manual hangup, browser refresh cleanup, setup timeout, and deadline termination. Record observed behavior and any unavailable account/network/microphone condition. Mocked events and HTTP alone do not establish working voice.

## Decisions before affected failure behavior

Inbound call origin and use of existing web_voice storage are resolved above; no new proactive exemption is needed. The never-connected/no-provider-call reservation release case remains a concrete accounting ambiguity. Exact audio enforcement remains a declared implementation limitation, not a silently satisfied guarantee. Controller should obtain a decision if the requested acceptance criteria require either a refund exception or guaranteed verbatim speech before implementing those affected behaviors.
