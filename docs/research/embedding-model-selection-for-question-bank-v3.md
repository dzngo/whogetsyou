# Embedding model selection for Question Bank v3

Research date: 2026-09-13.

## Decision

The launch model is **`text-embedding-3-small` at 1536 dimensions**, selected
after reviewing the cost, n8n integration, and operational tradeoffs below. It
is used only to retrieve the ten nearest accepted questions; an LLM makes the
duplicate decision. The relevant future quality measure is therefore
**duplicate-pair recall at 10**, not a similarity threshold or a general RAG
score.

The following alternatives remain candidates for a later domain evaluation:

1. `text-embedding-3-small` through n8n's native OpenAI Embeddings node;
2. `voyage-4-lite` through an authenticated HTTP Request node; and
3. `embeddinggemma:300m-qat-q8_0` through n8n's native Ollama Embeddings node.

Any future replacement must reach at least 98% Recall@10 on a fixture of
semantic duplicates and hard negatives. `text-embedding-3-small` is the launch
baseline because it is natively supported by the connected n8n instance, uses
an existing credential, and its token cost is negligible for short questions.

## Why embedding price is unlikely to drive campaign cost

OpenAI currently lists `text-embedding-3-small` at $0.02 per million input
tokens. At an intentionally conservative average of 25 tokens per proposed
question, embedding:

- 100,000 candidates costs about $0.05;
- 1,000,000 candidates costs about $0.50.

Each candidate needs one embedding. If accepted, that same vector is inserted
into pgvector; it does not need to be embedded again. Generative and judging
LLM calls will dominate campaign spend by orders of magnitude.

Source: [OpenAI `text-embedding-3-small` model page](https://developers.openai.com/api/docs/models/text-embedding-3-small).

## Finalists

| Model | Provider cost | n8n integration on the connected instance | Published evidence | Main tradeoff |
|---|---:|---|---|---|
| `text-embedding-3-small` | $0.02 / 1M tokens | Native `Embeddings OpenAI` sub-node; 256–1536 dimensions | OpenAI reports 62.3 average MTEB and 44.0 MIRACL for the model | Simplest production path; not the strongest public benchmark candidate |
| `voyage-4-lite` | First 200M tokens free, then $0.02 / 1M | No native Voyage embedding node found; use HTTP Request plus direct pgvector SQL | Voyage describes it as its lowest-cost/latency general model and reports strong top-10 retrieval in its own evaluation | Cheapest hosted option, but adds a credential and custom wiring; vendor-run benchmark |
| `embeddinggemma:300m-qat-q8_0` | No API charge | Native `Embeddings Ollama` sub-node | Google reports 69.49 English MTEB v2 for the Q8 checkpoint; Ollama distributes a 338 MB Q8 package | Requires installing and operating Ollama; no Ollama binary is currently installed on this host |

The benchmark numbers above are not directly comparable across rows because
they were produced by different organizations, benchmark versions, and test
protocols. They establish that each finalist is credible; they do not select a
winner for short conversational-question duplicate retrieval.

Sources:

- [OpenAI embedding model announcement](https://openai.com/index/new-embedding-models-and-api-updates/)
- [Voyage 4 pricing](https://docs.voyageai.com/docs/pricing)
- [Voyage 4 model family and top-10 evaluation](https://blog.voyageai.com/2026/01/15/voyage-4/)
- [Voyage embedding documentation](https://docs.voyageai.com/docs/embeddings)
- [Google EmbeddingGemma model card](https://huggingface.co/google/embeddinggemma-300m)
- [Ollama EmbeddingGemma package](https://ollama.com/library/embeddinggemma)

## Other credible options not selected for the first bake-off

### Gemini Embedding 2

Google lists `gemini-embedding-2` at $0.20 per million text tokens, or $0.10
through its Batch API. It supports flexible dimensions and automatic
normalization at reduced dimensions. It is capable but ten times the standard
token price of OpenAI Small, and the connected n8n instance does not expose a
native Gemini Embeddings node. Its multimodal strengths are irrelevant to a
text-only question bank.

Sources:

- [Gemini embeddings documentation](https://ai.google.dev/gemini-api/docs/embeddings)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

### Qwen3-Embedding-0.6B

This is a strong local challenger. Qwen reports 70.70 mean-task MTEB English
v2 and says task-specific instructions improve most retrieval scenarios by
roughly 1–5%. Ollama distributes a 639 MB quantized package, and n8n can call it
through the native Ollama Embeddings node. It is excluded from the first
bake-off only to keep the experiment small; add it if EmbeddingGemma fails the
Recall@10 gate.

Sources:

- [Qwen3-Embedding-0.6B model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Ollama Qwen3 Embedding package](https://ollama.com/library/qwen3-embedding)

## n8n compatibility findings

The live official n8n node catalog connected on 2026-09-13 exposes native
embedding sub-nodes for OpenAI, Cohere, Ollama, Lemonade, and AWS Bedrock. It
does not expose native Voyage or Gemini embedding sub-nodes.

The OpenAI node defaults to `text-embedding-3-small`, supports configurable
dimensions and batches up to 512 documents. The Ollama node accepts an
arbitrary installed embedding model name. Both can attach directly to n8n's
PGVector node.

Voyage remains feasible, but its HTTP response vectors must be inserted and
queried with Postgres/pgvector nodes or a small sub-workflow. This is visible
and testable in n8n, but is more work than a native embedding sub-node.

## Domain evaluation

Create a new evaluation fixture specifically for Question Bank v3; do not use
the old bank's evaluation corpus. It should contain approximately 300 query
questions:

- clear paraphrases and near-duplicates;
- the same aspect with different scenario, perspective, or answer space;
- repeated shallow forms across different subjects, such as favorite food vs
  favorite city;
- situational questions with small but meaningful changes;
- Deep questions that share vocabulary but reveal different characteristics;
- adversarial hard negatives whose wording is similar but meaning differs.

For every query, identify the existing questions that would make it redundant.
Measure:

- Recall@10 for known duplicates — release gate: at least 98%;
- Recall@5 as a diagnostic;
- median and p95 embedding latency;
- failed-request rate;
- provider token cost; and
- operational requirements.

The Semantic Judge continues to decide `duplicate`, `distinct`, or `uncertain`.
Embeddings never reject a question and therefore need no admission threshold.

## Recommended implementation decision

1. Build the pgvector workflow with a replaceable embedding sub-workflow.
2. Launch the bake-off with `text-embedding-3-small` as the baseline.
3. Add Voyage only if the user is willing to create another API credential.
4. Add local EmbeddingGemma only if running Ollama continuously is acceptable.
5. Pin the selected model, dimensions, input formatting, and model version in
   the bank manifest. Changing any of them creates a new embedding index and
   requires re-embedding the accepted questions.
