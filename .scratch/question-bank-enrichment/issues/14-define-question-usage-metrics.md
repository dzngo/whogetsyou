# Define the Question Usage Metrics Collection Contract

Type: grilling
Status: resolved
Blocked by: 10

## Question

Which appearances, skips, edits, confirmations, and related identifiers must be recorded as Question Usage Metrics so future analysis can relate gameplay behavior to the exact Question Bank entry and version? Define event meanings, identity and version links, privacy and retention boundaries, and explicitly prevent these metrics from influencing the bank or retrieval in the current effort.

## Answer

Record append-only presented, skipped, edit-completed, confirmed, and round-finished events with idempotent identities and exact Question Bank Snapshot, Question ID, Question Revision ID, round, presentation, selected Theme/Level, language, and origin links. Bank-edited confirmations retain the original bank identity but never store or admit the player's edited text. Store no names, answers, guesses, scores, IPs, or cross-game identifiers. Raw session-pseudonymous events expire after 90 days; de-identified counts by revision and snapshot may remain. Metrics are delivered asynchronously and have no read interface into proposal, evaluation, admission, coverage, bank, release, or retrieval modules in this effort.

## Comments

- Decision record: [`../question-usage-metrics.md`](../question-usage-metrics.md)
