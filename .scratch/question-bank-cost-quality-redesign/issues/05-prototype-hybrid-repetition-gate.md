# Prototype the Hybrid Semantic-Repetition Gate

Type: prototype
Label: wayfinder:prototype
Status: resolved
Parent: [Redesign the Question Bank Pipeline for Cost-Efficient Quality](../map.md)
Blocked by: [Prototype the Lean Creative Batch](03-prototype-lean-creative-batch.md), [Prototype Cascaded Quality Evaluation](04-prototype-cascaded-quality-evaluation.md)

## Question

What local lexical and embedding rules can safely accept obvious distance, reject exact or near-exact repetition, and shortlist only ambiguous candidate-neighbour pairs for GPT high-reasoning review while preserving separate Scenario, Perspective, Answer Space, Aspect, and Wording relations?

## Answer

Use a threshold-complete local scan followed by at most one batched GPT relation call. Local similarity is routing evidence, not a semantic verdict except at two deliberately narrow extremes.

### Local index and normalization

For the initial 200-question bank, compare each quality-passing candidate against every active revision in the immutable input snapshot and every earlier candidate kept in the same run. This full scan avoids approximate-nearest-neighbour omissions. Process new candidates in stable interleaved order: if a later candidate repeats an earlier kept one, retain the earlier candidate and reject the later one.

Normalize Unicode, case, apostrophes, punctuation, and whitespace for identity checks while preserving negation and content words. Record token Jaccard, token containment, character-trigram cosine, and cosine from a pinned local sentence embedding. Use FastEmbed's ONNX-backed `BAAI/bge-small-en-v1.5` adapter, which produces 384-dimensional embeddings, with the FastEmbed version and model artifact checksum pinned in policy. Embed both sides symmetrically from the same normalized question representation. A missing model or checksum mismatch stops the gate with `embedding_unavailable`; it never silently falls back to the existing hashed n-gram vector or to a paid embedding API. [FastEmbed documents the ONNX runtime, default model, and vector size](https://qdrant.github.io/fastembed/Getting%20Started/), and its [supported-model table identifies the English model and dimensions](https://qdrant.github.io/fastembed/examples/Supported_Models/).

### Versioned routing zones

- **Local Reject**: normalized texts are identical; or token Jaccard is at least `0.88` and character-trigram cosine at least `0.94`; or token containment is at least `0.95` and character-trigram cosine at least `0.92`. Record identity or extreme near-copy evidence and reject without GPT.
- **Local Distance**: against every bank and earlier-kept question, embedding cosine is below `0.60`, token Jaccard below `0.25`, and character-trigram cosine below `0.55`. Record the maximum scores and pass the semantic gate without GPT.
- **GPT Review**: every remaining candidate–neighbour pair. Any signal leaving the Local Distance zone is sufficient to shortlist the pair; all Local Reject pairs are removed first.

These numbers are an initial `semantic-routing-v1` policy, not universal properties of the embedding model. Local Distance authority remains disabled until a fresh relation fixture and the costed pilot show zero false-distinct decisions in the reviewed sample. Before that validation, the same zone may prioritize pairs but cannot authorize semantic passage.

### Batched high-reasoning relation judgment

Send at most twelve ambiguous pairs in one `gpt-5.4-mini` high-reasoning call with a 6,000-token input cap and reasoning-inclusive `max_output_tokens=3,500`. At current researched list prices, its worst-case reservation is `$0.020250`. If more than twelve pairs are ambiguous, do not sample or discard the remainder: mark affected candidates `pair_overflow` and unresolved. Combined with the creative and quality maxima, the planned pilot exposure is `$0.185700`, leaving `$0.014300` for later metadata work inside the `$0.20` ceiling.

For each exact candidate–neighbour ID pair, the model returns these relations independently as `same`, `overlapping`, `different`, `opposed`, or `uncertain`:

- Semantic Scenario;
- Question Perspective;
- Answer Space;
- Question Aspect;
- Wording Pattern.

It also proposes `repeat`, `distinct`, or `uncertain` with bounded reason codes and concise evidence. The deterministic resolver accepts `repeat` only when Scenario, Perspective, and Answer Space are each `same` or `overlapping`. Aspect and Wording remain diagnostic: either one alone is insufficient. A proposed verdict inconsistent with the relation fields, any missing pair, unknown or duplicate ID, malformed response, or execution ambiguity becomes uncertain and can never default to distinct.

A repeat against the trusted snapshot rejects the candidate. A repeat against an earlier kept candidate rejects the later candidate. A distinct result passes the semantic gate. Genuine uncertainty becomes eligible for bounded Human Review; systemic pair overflow or malformed batch evidence is an operational failure rather than many question-review cases.

The logic prototype is preserved on branch `codex/prototype-hybrid-repetition-gate` at commit `44fbb10`. Its simulated fixtures cover exact and near copies, low-lexical semantic paraphrases, shared Aspect with distinct Perspective and Answer Space, shared Wording with distinct meaning, opposed framing, obvious distance, and genuine uncertainty. It makes no model-provider calls.
