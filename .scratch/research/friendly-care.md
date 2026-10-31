# Friendly care validation

- A1 regression: 692 tests passed (`runs/friendly-care-final.xml`).
- Cross-agent acceptance and integration, plus updated conversation validation:
  98 tests passed (`runs/friendly-care-integration.xml`).
- Real OpenAI pipeline and safety cases: 10 passed in the isolated
  `runs/friendly-care-live-20261031/report.json` run.
- Final conversational check: five real model turns passed, covering English ETA,
  urgency, delay explanation, policy information and thanks. Report:
  `runs/friendly-conversation-47fc73dc/report.json`.
- HTTP preview on port 8791 returned `used_llm: true`, the unchanged forecast,
  its uncertainty statement and no financial effects. Existing port 8790 remains
  untouched; this preview has a separate runtime under `runs/friendly-demo-20261031`.
- Team main now enables A2/A3 model reviews only with `SEA_LLM_REVIEWS=1`.
  This conversation preview uses A1 LLM and the standard A3/A2 replay phases.

Observed urgent-customer lead-in: “Mình hiểu bạn cần biết thời gian nhận hàng
để sắp xếp.” The neutral ETA reply goes straight to the forecast; thanks closes
without another question. Unverified facts and financial/cancellation policy
continue to use the existing validation gates.
