# Research Semantic Repetition and Corpus-Diversity Detection

Type: research
Status: resolved

## Question

What do primary research and first-party technical sources establish about detecting semantic repetition and measuring diversity in a large short-text corpus? Compare the demonstrated strengths and failure modes of lexical similarity, embeddings, clustering, learned or LLM classification, structured metadata, and hybrid approaches for distinguishing duplicate wording, semantic scenarios, Question Aspects, Question Perspectives, and answer spaces.

## Answer

Research artifact: `docs/research/semantic-repetition-and-corpus-diversity.md` on branch `research/semantic-repetition-detection`, commit `a1e295ca91148aed5966d6c8793b7d5a81075355`.

Downstream decisions must preserve duplicate wording, semantic scenario, Question Aspect, Question Perspective, and answer space as separate relations. Use lexical and embedding similarity for high-recall neighbor discovery, then relation-specific structured metadata and calibrated pair adjudication; never make one similarity score or unsupervised cluster authoritative. Validate every model, prompt, threshold, and answer-space hypothesis on project-specific hard contrasts, retain disagreement, abstain to the Human Review Queue, version all evidence and taxonomy assignments, and measure local repetition plus facet-specific coverage within each Theme × Level slice.
