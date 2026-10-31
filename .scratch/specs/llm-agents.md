# LLM integration for A1, A2 and A3

The user authorizes integration across care_truc and platform_huy (2026-10-31).
Do not change shared contracts or dependencies. Use the existing httpx transport.

- Explicit `--integrated --llm` loads only OpenAI settings from the local .env.
- A3 uses a bounded structured LLM review of source health. The model may keep
  controls or tighten proactive contact; it cannot grant permission or money.
- A2 uses a bounded, diverse priority batch to produce Vietnamese operator
  hypotheses and next steps with validated evidence references. Assessments,
  dates, fault, forecasts and compensation remain authoritative rule outputs.
- A1 uses semantic topic selection for otherwise unrecognized customer questions,
  then composes validated fact slots. Policy, human requests, cancellation and
  financial requests still run before LLM processing.
- Model output is untrusted. Reject malformed, incomplete, refused, hallucinated
  references and out-of-policy outputs; report fallback explicitly.
- Persist A2/A3 review traces in runtime state and expose through authenticated
  existing APIs. Never send credentials, full databases or customer identifiers.
- Live verification must assert actual model success, not just a safe fallback.
  Source DB hashes must remain unchanged. Synthetic cases are isolated tests only.
