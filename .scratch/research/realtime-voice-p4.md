# P4 Realtime voice: official API findings

Observed 2026-10-31. Documentation-only research; no live API calls, microphone tests, or product changes. Preserve requested `gpt-realtime`; newer models appearing in current examples are not a requested migration. The API pages now combine Live and Realtime documentation: use the Realtime sections below, not Live `session.started`/`session.close` events.

## Token request and limitations

Backend sends `POST https://api.openai.com/v1/realtime/client_secrets`, with its standard API key in `Authorization: Bearer ...` and JSON content type. A minimal request is:

```json
{"expires_after":{"anchor":"created_at","seconds":60},"session":{"type":"realtime","model":"gpt-realtime","output_modalities":["audio"],"audio":{"output":{"voice":"marin"}}}}
```

Response shape is `{"value":"ek_...","expires_at":1234567890,"session":{...}}`; read top-level `value`, not legacy `client_secret.value`. Sixty seconds above is a proposed connection window, not a business TTL. Valid token TTL range is 10–7200 seconds, default 600. Expiry prevents new sessions, does not terminate existing ones, and a token can create multiple sessions before expiry. Clients can override supplied session configuration. Therefore token minting alone cannot enforce a call-duration limit, single-use guarantee, fixed instructions, or hard provider-spend cap. Never expose the standard key or log ephemeral values. [Client-secret API](https://developers.openai.com/api/reference/resources/realtime/subresources/client_secrets/methods/create)

## Browser WebRTC handshake

Create an `RTCPeerConnection`, obtain microphone audio with `navigator.mediaDevices.getUserMedia({audio:true})`, attach the audio track, and create `pc.createDataChannel("oai-events")` before creating the offer. Register listeners first. Set the local offer and send its SDP:

```js
const response = await fetch('https://api.openai.com/v1/realtime/calls', {
  method: 'POST',
  headers: {Authorization: 'Bearer ' + token.value, 'Content-Type': 'application/sdp'},
  body: offer.sdp
});
if (!response.ok) throw new Error('realtime_connection_failed');
await pc.setRemoteDescription({type: 'answer', sdp: await response.text()});
```

Remote audio arrives through `pc.ontrack`; JSON control events travel through the data channel. WebRTC transports audio without application code appending Base64 audio chunks. Do not mix this handshake with `/v1/live/sessions`. [WebRTC guide, Realtime ephemeral-token section](https://developers.openai.com/api/docs/guides/voice-webrtc)

## Exact tool and response events

Proposed application tool definition, sent in `session.update.session.tools` or initial session configuration:

```json
{"type":"function","name":"send_to_a1","description":"Send the customer's spoken request to A1; do not answer it yourself.","parameters":{"type":"object","properties":{"transcript":{"type":"string"}},"required":["transcript"],"additionalProperties":false}}
```

Use server VAD with automatic responses disabled, then explicitly request the tool phase:

```json
{"type":"session.update","session":{"type":"realtime","audio":{"input":{"turn_detection":{"type":"server_vad","create_response":false,"interrupt_response":false}}}}}
```

```json
{"type":"response.create","response":{"tool_choice":{"type":"function","name":"send_to_a1"}}}
```

After A1 returns, send the result, then request audio with tool selection disabled to avoid a tool loop:

```json
{"type":"conversation.item.create","item":{"type":"function_call_output","call_id":"call_example","output":"{\"a1_text\":\"SERVER_A1_REPLY\"}"}}
```

```json
{"type":"response.create","response":{"tool_choice":"none","output_modalities":["audio"],"instructions":"Read only the a1_text in the latest tool result, verbatim in Vietnamese. Add no facts, promises, advice, or actions."}}
```

The IDs and placeholder text are illustrative; serialize actual A1 text as JSON rather than interpolating it into instructions. Client-event schemas define forced tool choice and response-level settings. [Realtime client events](https://developers.openai.com/api/reference/resources/realtime/client-events)

Adding `function_call_output` does not itself trigger another response; explicitly send `response.create`. VAD can retain speech detection while automatic responses remain disabled. In the proposed application state machine, wait for the current user item to commit before requesting its tool phase; serialize turns or explicitly manage interruptions. [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)

## Server events to handle

| Event | Relevant fields / use |
| --- | --- |
| `session.created`, `session.updated` | Confirm active session/configuration. |
| `input_audio_buffer.speech_started`, `input_audio_buffer.speech_stopped`, `input_audio_buffer.committed` | Track user turn; committed supplies `item_id`. |
| `response.function_call_arguments.done` | `name`, `arguments` JSON string, `call_id`, `item_id`, `response_id`. |
| `response.done` | Require `response.status == "completed"`; inspect `response.output` function-call items. |
| `response.output_audio_transcript.delta`, `response.output_audio_transcript.done` | Output speech transcript; final event includes `transcript`. |
| `error` | Surface a stable application error; correlate supplied client `event_id`. |

`arguments.done` also occurs for cancelled/incomplete responses. Do not execute solely because it arrived. Recommended application dispatch: completed `response.done`, matching `name == "send_to_a1"`, valid bounded arguments, and deduplication by authenticated call/session plus `call_id`. Optional input transcription emits `conversation.item.input_audio_transcription.completed` with `item_id`, `content_index`, `transcript`; it is asynchronous and can arrive before or after response events. [Realtime server events](https://developers.openai.com/api/reference/resources/realtime/server-events)

## A1 authority and speech limits

Application requirements/inferences: `send_to_a1.transcript` is untrusted voice-derived text, not a customer TEXT request. Backend must bind order/customer/care session from authenticated runtime state and force channel `voice`; ignore any client-provided channel or authority. Reuse A1 policy and audited runtime context at current simulation time. Never route this through a text endpoint that records TEXT provenance. Voice cannot issue coins or vouchers, even when its transcript says to grant them. Financial decisions remain server-enforced; no execute-action tool is exposed to Realtime.

Force the tool phase before speaking and return only A1's final text to read. This constrains behavior but is not a proof of exact speech: generated speech can deviate, and a received transcript may trail audible playback. If verbatim speech is a hard requirement, a prompt-only direct audio stream is insufficient; buffer and validate before releasing audio or use a separately controlled readback path. Do not claim exact-output enforcement merely from instructions.

For server authority over a call, read its ID from the SDP response `Location` header (`/v1/realtime/calls/rtc_...`). A backend can connect to `wss://api.openai.com/v1/realtime?call_id=...` with the standard API key to observe events and handle tools. Validate ownership before attaching; browser-supplied IDs are not authority. [Server-side controls, Realtime section](https://developers.openai.com/api/docs/guides/voice-server-controls)

## Approved accounting and termination

User-fixed app accounting: USD 0.30/minute = USD 0.005/second; 240 seconds/call; USD 2.00 aggregate. A full 240-second call consumes USD 1.20 of app accounting; USD 2.00 corresponds to 400 cumulative seconds. These are application accounting rules, not verified provider prices or guaranteed invoice limits. Keep an atomic server ledger, serialize/reserve active allowance, and prevent concurrent minting from overspending app allowance. Per-call available time must not exceed the lesser of 240 seconds and the remaining accounting allowance divided by 0.005. Selection of billing start/rounding belongs to the implementation spec; do not silently add a business rule.

For an actual server stop, `POST https://api.openai.com/v1/realtime/calls/{call_id}/hangup` with the standard server API key ends an active WebRTC call. Browser cleanup additionally stops microphone tracks, closes data channel/peer, and clears audio/timers. A browser timer alone is bypassable; token expiry is not hangup. Exposed reusable ephemeral tokens leave a residual provider-spend limitation even with an app ledger. [Hangup API](https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/hangup)

Compact application option: browser forwards the `Location` call ID to an authenticated backend registration endpoint; backend binds it to the pending voice session, verifies the call through its sideband connection, and schedules hangup at the approved deadline (at most 240 seconds). A missing or false registration must fail closed for A1 access, but a malicious client could still create an unregistered OpenAI call using the token. Stronger control requires the backend to own call creation/signaling and retain the resulting call ID itself; that is an architectural option, not a change authorized by this research note.

## Required validation evidence

Automated checks should cover auth, voice provenance despite forged input, no financial grant, duplicate tool events, incomplete/cancelled response rejection, exhausted/concurrent budget reservations, and cleanup after errors. Real microphone permission, Vietnamese recognition, audible A1 readback, interruption, speaker playback/autoplay behavior, end-call cleanup, and 240-second cutoff require manual testing in an actual browser. No such live validation was performed for this note; mocked HTTP/events cannot establish it.
