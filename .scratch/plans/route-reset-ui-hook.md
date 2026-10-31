# V4 Reset UI hook

Owner: live.html / voice UI controller (outside this worker's scope).

Add the confirmed Reset button beside NEXT. On click, use the existing authenticated
JSON request helper to POST `/api/reset` with `{}` and `X-Presenter-Key`. A configured
`LIVE_PRESENTER_KEY` is mandatory even on loopback; absent or wrong keys return 401.
Disable Reset while NEXT is busy. The server independently returns 409
`next_in_progress` if NEXT is reserved, or `reset_in_progress` while a reset starts.

On HTTP 200 replace the displayed state with the returned fresh snapshot; clear the
selected chat, pending cancellation UI, old conversation messages and request IDs.
The reset retains the phrase selector and release input paths, returns simulation
time to the configured initial time, and starts separate platform/Care databases.
Previous runtime databases remain on disk. Reset does not run NEXT automatically.
Show API failures through the existing error UI and retain the current state.
