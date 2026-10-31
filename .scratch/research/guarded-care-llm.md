# Official API evidence — 2026-10-31

Fetched official model page https://developers.openai.com/api/docs/models/gpt-5.4-mini : model supports Responses and structured outputs. Standard input price is USD0.75 per million tokens, cached input USD0.075, output USD4.50. Use standard uncached input for conservative budgeting and no external tools or priority processing. Explicit model alias remains gpt-5.4-mini as requested.

Fetched https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses : Responses uses text.format with json_schema, strict=true, required fields and additionalProperties=false. Validate response locally, including refusals/incomplete output. Prompt instructions do not replace deterministic validators or money authority.

Existing rules.classify always returns IntentSignals; a compatible classify_known entrypoint may return None for uncertain text while retaining legacy callers. Existing harness already owns deadline and durable response paths; integrate there instead of building a second agent. Budget reservations must happen before network calls, and failed/time-limited calls cannot be treated as free or successful.
