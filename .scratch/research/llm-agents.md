# Integration findings

- Current main already provides guarded A1 phrase/segment selection via OpenAI.
  A2 and A3 are deterministic; --llm currently enables only A1.
- Official schema documentation inspected:
  https://developers.openai.com/api/docs/guides/structured-outputs
  Responses uses text.format with type=json_schema, strict=true and a closed
  schema. Application validation still checks references and business authority.
- Existing installed/runtime code uses httpx; no new dependency is needed.
- API keys stay in .env / process environment. Do not log request headers or
  provider error bodies. store=false is set for model requests.
- sysguard guard_alive currently uses a 90-minute liveness indicator, whereas
  contracts.params and A1 enforce a 60-minute contact heartbeat. Preserve the
  liveness indicator and enforce the shared 60-minute threshold for contact.
