# P4 voice specification review

Reviewed 2026-10-31 against `realtime-voice-p4.md`, its research note, and the current Care/platform interfaces. Read-only implementation review; no live provider or browser validation.

## Blockers

1. **Voice session creation changes the existing chat selection unless explicitly isolated.** `platform_huy/demo_flow.py::_view` selects the latest Care session for an order without filtering channel and includes every active session in `active_chats`. Its `chat-say` branch also accepts any supplied Care session ID. A newly created customer `web_voice` session can therefore replace the selected A1 chat in the existing UI; subsequent typed benefit requests would enter that voice session and be denied instead of using the original eligible chat. Specify channel-aware chat projection/selection and rejection of voice sessions by the text route, while leaving the dedicated voice adapter able to access its bound session. Verify that starting/ending voice preserves the original chat ID, history, and eligible text-benefit path.

2. **The stated authenticated owner and foreign-session rejection have no defined identity source.** `PresenterAuth.authorized` returns a boolean for a shared presenter secret; `VOICE_CODE` is also a shared secret. Neither identifies a customer or browser. Existing `DemoFlow` derives the customer principal from the selected order, so simply repeating that derivation during a voice lookup would validate the stored order rather than the caller's ownership. Specify the concrete server-established owner/capability used by session/create/connect/turn/end/state, or explicitly define all authenticated presenters as the same authorized operator and narrow the foreign-session guarantee accordingly. Do not add client-supplied principal authority or claim per-customer authorization from the existing boolean presenter check.

Billing start, never-created-call refunds, and uncertain-provider reservations are already awaiting the controller's user question and are not additional blockers in this review. The specification must incorporate that answer before implementing those accounting branches.
