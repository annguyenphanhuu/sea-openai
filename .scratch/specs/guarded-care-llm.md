# Guarded Care LLM

User explicitly authorizes Care changes. Preserve existing policy, durable consent, monetary authority and executor. Extend Vietnamese rule recognition; use model classification only for uncertain text. Model intent alone never establishes a financial request or cancellation consent.

Use OpenAI Responses API with model gpt-5.4-mini, OPENAI_API_KEY from process environment, strict JSON Schema restricting intent to the shared enum. Customer text is untrusted data. Phrase only safe explanatory templates, never money, cancellation, handoff or confirmation. Reject invented numbers/dates/promises, non-Latin/Vietnamese letters and adjacent repeated words; retain original template with validator_ok=false.

Track actual model requests in used_llm, rule/llm intent_source, validator outcome and rule_only budget state. Default LLM_BUDGET_USD=3; reserve conservative request cost before sending and preserve accounting across runtime restarts. Tests use explicitly injected fake LLM under LLM_FAKE=1; never fake executor success. Five user cases plus budget/error/deadline checks must use literal assertions. Root may make a bounded actual API check using existing authorized credentials without logging them.
