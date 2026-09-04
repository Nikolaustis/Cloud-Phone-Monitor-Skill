# AI Architecture

The AI layer is a consumer of the existing deterministic pricing semantic layer, not a replacement for it.

```text
Dashboard safe data
  → AI Context Builder
  → normalized config/change/pairing/trend/metric facts
  → deterministic tool registry
  → Evidence Mode OR optional LLM orchestration
  → answer + evidence + revision
```

`fact_id` is stable for identical normalized facts. `evidence_id` is response-local (`E1`, `E2`, ...). The former supports data lineage; the latter supports readable citations in one answer.

Structured numerical data uses tools. Text retrieval/RAG, if added later, should be limited to unstructured promotion text, methodology and documentation.
