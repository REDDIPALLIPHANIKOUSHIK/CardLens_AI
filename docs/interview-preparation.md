# CardLens AI — interview notes

- **What is CardLens AI?** A decision-support demo that ranks synthetic card offers against user-entered spending and preferences, then explains estimated value and alternatives.
- **Why hybrid ranking?** Eligibility is a transparent rule gate; weighted scoring then combines spending fit, estimated rewards, preference match, known criteria, fees, and benefits. Each factor can be inspected.
- **Why not use only an LLM?** Generative models can vary or invent numeric outputs. Deterministic backend functions own rank, eligibility, estimates, comparison, and simulation. The optional LLM only explains outputs after calling tools.
- **How is CardLens Score calculated?** A weighted 0–100 suitability score from six factors. It is not an approval probability. The API returns the breakdown.
- **How are rewards estimated?** Monthly entered spend × illustrative demo rate × 12, less the catalog annual fee. Caps, exclusions, redemption rules, and issuer offer terms are deliberately not guessed.
- **What is What-If?** The API reruns the same validation, eligibility, reward, and ranking logic with changed spending or fee preference and returns movement and a deterministic explanation.
- **What does confidence mean?** A profile completeness signal blended with top-score separation, with reasons for missing spend/eligibility fields. It is not an LLM's self-reported probability and has not been calibrated against outcomes.
- **Why RAG?** Issuer terms change. Retrieval is source- and version-linked; if evidence is absent, the service returns an insufficient-information answer.
- **How are AI failures handled?** Optional calls are bounded by timeouts and fail to deterministic explanations; voice returns a text fallback; recommendations do not depend on external AI.
- **What is the model evaluation?** No labeled user-choice dataset is available. The current project makes no predictive-accuracy or recommendation-quality claim; deterministic ranking is the baseline.
- **How is user data protected?** No payment credentials are collected. Logs contain request metadata but not profile bodies. The demo has no authentication or consent/purpose workflow, so it is not ready for real personal financial data.
- **What remains?** Durable profile and conversation workflows with authentication/consent, calibrated recommender evaluation, issuer-verified card catalog, service-level controls for multi-instance rate limiting, and broader language/UI validation.
