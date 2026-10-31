# Minimal voice hooks for the server owner

Voice branch: `huy-voice`. Voice code does not edit `serve_ui.py` or `demo_flow.py`.
The one new Chat button imports `/voice.js`; existing static serving can serve it.

## HTTP adapter

Create one `VoiceRoutes` from `platform_huy.voice_routes` per server:

```python
voice = VoiceRoutes(
    state_path.parent / 'voice-budget.sqlite',
    os.environ.get('OPENAI_API_KEY', ''),
    os.environ.get('VOICE_CODE', ''),
    budget_usd=float(os.environ.get('VOICE_BUDGET_USD', '2')),
    validate_session=validate_existing_chat_with_voice_guard,
)
```

Preserve presenter authentication, same-origin checks and JSON size limits before
all new routes. `X-Voice-Code` is an additional secret header, never a query string.
Map `VoiceError.status` and `.code` to sanitized JSON; never log bodies, headers or
client-secret values. All responses, especially client secrets, need `Cache-Control: no-store`.

| Route | Call |
| --- | --- |
| POST `/api/voice/session` | `voice.create(payload, code)` |
| POST `/api/voice/end` | `voice.end(payload, code)` |
| POST `/api/voice/state` | `voice.state(code)` |

`create` takes the existing `session_id`, creates no A1 session and returns an
ephemeral `client_secret`, `voice_session_id`, `expires_at`,
`max_duration_seconds`, `issued_at`, `deadline_at`, and remaining app budget.
The browser sends its SDP directly to OpenAI `/v1/realtime/calls` with that key.
Standard `OPENAI_API_KEY` never leaves the server. Do not auto-retry token creation.

## Existing POST `/api/chat/say`

For a voice payload, first call `voice.authorize_turn(payload, code)`. It checks
the issued voice binding, existing chat ID, deadline and code, and returns exact
customer text plus trusted `channel='voice'`. Use the existing `handle_message`
and gateway path, with the existing chat session. Do not create another A1 session.

**Required before enabling token creation:** the platform adapter must carry this
trusted voice marker through the current turn and effect gateway. A voice transcript
must never be recorded as customer TEXT compensation evidence or authorize coins/
voucher. Reject a voice-marked request if this hook is unavailable. Merely placing
`channel` in JSON or `inside` is insufficient because the stored session is `chat`.
Keep normal text requests unchanged. The validator callback must dispatch to the
Care owner loop and verify an active existing chat; do not read its SQLite from
the HTTP thread. It must fail closed until the voice provenance guard is wired.

After normal A1 processing and receipt handling, return `reply` and `inside` with
the actual intent/gate/used_llm plus `channel='voice'` and the exact input transcript.
The browser refuses to read a response without that confirmed channel. Tool
`request_id` is `voice:{voice_session_id}:{call_id}`; preserve existing idempotency.
Revalidate any submitted voice capability even if the caller omits `channel`.

## Budget and validation

The backend reserves up to $1.20, tracks a $2 total at $0.30/minute, and conservatively
counts time from issuance; the browser closes tracks/peer/data channel by 240 seconds
or a shorter remaining allowance. `/end` releases unused app allowance. This is
application accounting, not a guaranteed provider invoice cap: ephemeral tokens
are reusable and expiry does not terminate a provider call. No SDP relay is used.

Before manual Chrome testing, run actual HTTP checks for bad VOICE_CODE 401,
ordinary/injection transcripts reaching A1, voice money denial, existing text chat
still granting only under original eligibility, and expiry/cleanup. Existing
offline tests cover the adapter and browser event protocol, not end-to-end A1 or
microphone operation. Huy agreed to perform the real microphone test once wired.
