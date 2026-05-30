# Customer Value

The baseline customer pain is onboarding delay. Customers connect a database,
see hundreds of columns, and then depend on professional services to manually
find PII and write masking rules. That slows time-to-value, increases delivery
cost, and creates inconsistent outcomes across customer projects. This tool
addresses that pain by turning schema review into a guided workflow: detect
likely PII, recommend the masking function, explain the recommendation, and
route ambiguous fields to human review instead of silently guessing.

In a 30-day pilot with three customers, I would measure success with concrete
operational metrics: time from schema connection to draft masking plan, number
of columns reviewed per analyst hour, PII recall on a customer-approved sample
set, percentage of high-confidence rules accepted without edits, and review
queue size per schema. I would also track user-facing outcomes such as time to
first masking job and the percentage reduction in manual services effort.

The main risks are false negatives, category confusion, and overconfident
automation on weak evidence. A missed PII column is the most serious failure
mode because it can create a compliance gap. Guardrails in this submission are
therefore recall-first: deterministic detection, explicit confidence scores,
review routing below the auto-configure threshold, grounded documentation
retrieval, and tests that measure regression on a labeled golden set.

I would not fully automate final approval of low-confidence columns, policy
exceptions, or production promotion of masking jobs. Those steps should stay
human because they require customer-specific policy judgment, business context,
and accountability. The right product outcome is not “remove the human”; it is
“remove the repetitive triage and leave humans with the cases that actually need
judgment.”
