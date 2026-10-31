# Guarded LLM execution

1. Read actual Care runtime and official model/Responses documentation. Preserve classifier public compatibility and deadline checks.
2. Client worker in care-llm-client worktree owns llm.py, validator.py and its new tests. Wiring worker in care-llm-wiring owns rules, harness, lifecycle/runtime types and new integration tests. Agree dataclass results before implementation.
3. Root reviews disjoint diffs, integrates only authorized changes, adds factual UI diagnostics/banner and preserves the pending five-tab work. No contract, policy or financial executor changes.
4. Run full acceptance plus Care tests and an independent review. Test actual OpenAI with a tightly bounded request; record whether it succeeded rather than fabricating used_llm.
5. Fetch/merge before push, publish verified huy/main as authorized. Keep the Azure 008addd rollout separate until the requested public smoke test passes.
