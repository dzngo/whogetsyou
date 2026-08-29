# Research Reliable Automatic LLM Evaluation

Type: research
Status: resolved

## Question

What do primary research and first-party technical sources establish about reliable automatic evaluation of creative text with LLMs, including independent judging, evaluator calibration, correlated errors, position and style bias, multi-agent critique or debate, ensemble agreement, confidence, and abstention? Translate the evidence into constraints that a Question Enrichment Pipeline must respect without selecting this project's final architecture.

## Answer

Research is captured on branch `research/automatic-llm-evaluation` at commit `3f6e509` in `docs/research/reliable-automatic-llm-evaluation.md`.

Downstream decisions must treat automatic judging as a calibrated selective evaluator, not a self-validating agent consensus: establish a versioned target-domain human benchmark; keep substantive criteria separate; blind proposal provenance and probe order/style counterfactuals; preserve independent judgments before critique or debate; measure correlated errors rather than interpreting panel agreement as confidence; calibrate accept/abstain thresholds on held-out human labels; route uncertain, unstable, conflicted, or out-of-distribution proposals to the Human Review Queue; and version/regression-test every judge, rubric, prompt, and aggregation change. The evidence does not select the number of agents, models, or deliberation/aggregation architecture—each must outperform simpler baselines on that benchmark.
