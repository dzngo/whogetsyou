// Run: node scripts/test-scoring.ts   (Node ≥ 22 strips TS types natively)
import { computeScoring, type ScoringOption } from "../src/lib/game/scoring.ts";

let passed = 0;
let failed = 0;

function eq(label: string, got: Record<string, number>, want: Record<string, number>) {
  const keys = new Set([...Object.keys(got), ...Object.keys(want)]);
  let ok = true;
  for (const k of keys) if ((got[k] ?? 0) !== (want[k] ?? 0)) ok = false;
  if (ok) {
    passed++;
    console.log(`  ✅ ${label}`);
  } else {
    failed++;
    console.log(`  ❌ ${label}\n     got  ${JSON.stringify(got)}\n     want ${JSON.stringify(want)}`);
  }
}

// Players: S=storyteller, A/B/C=listeners. One submission each.
const S = "S", A = "A", B = "B", C = "C";
const playerIds = [S, A, B, C];
const sub = (owner: string) => `${owner}_sub`;
const options: ScoringOption[] = [
  { submission_id: sub(S), owner_id: S, is_storyteller: true },
  { submission_id: sub(A), owner_id: A, is_storyteller: false },
  { submission_id: sub(B), owner_id: B, is_storyteller: false },
  { submission_id: sub(C), owner_id: C, is_storyteller: false },
];
const base = { level: "shallow" as const, storytellerId: S, playerIds, options, currentScores: {}, maxScore: 1000 };

// Case 1 — exactly one correct (A). B,C both decoy onto A. (shallow ×1)
eq(
  "1 correct: A+3,S+3, +decoy A picked by B&C (+2)",
  computeScoring({ ...base, guesses: { [A]: sub(S), [B]: sub(A), [C]: sub(A) } }).deltas,
  { A: 5, S: 3, B: 0, C: 0 },
);

// Case 2 — some but not all correct (A,B correct of 3). C decoys onto A.
eq(
  "some correct: A+1,B+1,S+1, +decoy A(+1)",
  computeScoring({ ...base, guesses: { [A]: sub(S), [B]: sub(S), [C]: sub(A) } }).deltas,
  { A: 2, B: 1, S: 1, C: 0 },
);

// Case 3 — everyone correct → each listener +2, storyteller 0.
eq(
  "all correct: A/B/C +2, S 0",
  computeScoring({ ...base, guesses: { [A]: sub(S), [B]: sub(S), [C]: sub(S) } }).deltas,
  { A: 2, B: 2, C: 2, S: 0 },
);

// Case 4 — nobody correct → each listener +2, plus decoys. A→B, C→B, B→C.
eq(
  "none correct: base +2 each, decoy B(+2) C(+1)",
  computeScoring({ ...base, guesses: { [A]: sub(B), [C]: sub(B), [B]: sub(C) } }).deltas,
  { A: 2, B: 4, C: 3, S: 0 },
);

// Case 5 — deep multiplier doubles Case 1.
eq(
  "deep ×2 of case 1: A+10,S+6",
  computeScoring({ ...base, level: "deep", guesses: { [A]: sub(S), [B]: sub(A), [C]: sub(A) } }).deltas,
  { A: 10, S: 6, B: 0, C: 0 },
);

// Winners + newScores carry existing scores forward.
const r = computeScoring({
  ...base,
  maxScore: 10,
  currentScores: { S: 8, A: 6, B: 3, C: 0 },
  guesses: { [A]: sub(S), [B]: sub(A), [C]: sub(A) },
});
eq("newScores add onto current", r.newScores, { S: 11, A: 11, B: 3, C: 0 });
console.log(`  ${r.winners.sort().join(",") === "A,S" ? "✅" : "❌"} winners = [A,S] (got [${r.winners.sort()}])`);
if (r.winners.sort().join(",") === "A,S") passed++; else failed++;

console.log(`\n${failed === 0 ? "🎉 ALL PASS" : "⚠️ FAILURES"} — ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
