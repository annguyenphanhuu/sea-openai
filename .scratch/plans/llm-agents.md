# LLM agents implementation plan

1. Fetch team main, branch nguyen/llm-agents; inspect existing runtime and A1 LLM.
2. Add bounded Responses API client, A2 reviewer, A3 reviewer and runtime wiring.
3. Add A1 semantic topic routing while preserving immutable rendered facts.
4. Verify malformed outputs, timeouts, stale feeds, injection, safe controls,
   restart persistence, HTTP visibility and unchanged financial authority.
5. Run live OpenAI checks on release data and adversarial isolated cases; save
   report under runs/ and document repeatable commands and limitations.
6. Run repository and care regression tests, diff checks, fetch/merge, commit/push.
