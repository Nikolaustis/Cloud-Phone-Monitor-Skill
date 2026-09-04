# AI Evaluation

The repository treats evaluation as part of the AI contract rather than a final presentation step.

`benchmark_questions.json` contains a synthetic golden set that exercises deterministic routing, numeric retrieval, evidence coverage, trend lookup, explanation and correct abstention. Run:

```bash
python -B evals/run_eval.py
```

The generated `demo_report.json` is **not a production LLM score**. Before using AI metrics on a resume, create a production-safe benchmark and report at least:

- tool-routing accuracy;
- numeric exact match;
- evidence coverage / unsupported-claim rate;
- abstention accuracy;
- P50/P95 latency;
- model/provider + data revision;
- token/cost metrics when an LLM is enabled.

Production evaluations should keep deterministic tool correctness separate from LLM answer-quality judgments.
