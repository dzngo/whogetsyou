// Scoring — ported 1:1 from the old Python `_compute_scoring` (ui/game_flow.py).
//
//  Depth multiplier: shallow ×1, deep ×2.
//  - exactly one listener correct   → that listener +3×m, storyteller +3×m
//  - some (not all) listeners correct → each correct +1×m, storyteller +1×m
//  - all or nobody correct          → each listener +2×m, storyteller 0
//  Decoy bonus (stacks): if a listener's answer is picked by N other listeners → +N×m.

import type { Level } from "@/lib/types";

export interface ScoringOption {
  submission_id: string;
  owner_id: string;
  is_storyteller: boolean;
}

export interface ScoringInput {
  level: Level;
  storytellerId: string;
  /** all player ids in the room */
  playerIds: string[];
  /** answer options for the round (one per player) */
  options: ScoringOption[];
  /** guesserId -> chosen submission_id */
  guesses: Record<string, string>;
  currentScores: Record<string, number>;
  maxScore: number;
}

export interface ScoringResult {
  deltas: Record<string, number>;
  correct: string[];
  decoyPicks: Record<string, number>;
  newScores: Record<string, number>;
  winners: string[];
}

export function computeScoring(input: ScoringInput): ScoringResult {
  const { level, storytellerId, playerIds, options, guesses, currentScores, maxScore } = input;
  const multiplier = level === "deep" ? 2 : 1;

  const bySubmission = new Map<string, ScoringOption>();
  for (const opt of options) bySubmission.set(opt.submission_id, opt);

  const storytellerSubmission = options.find((o) => o.is_storyteller);
  const listenerIds = playerIds.filter((pid) => pid !== storytellerId);

  const deltas: Record<string, number> = {};
  for (const pid of playerIds) deltas[pid] = 0;

  // Correct listeners: guessed the storyteller's own submission.
  const correct: string[] = [];
  for (const [guesserId, submissionId] of Object.entries(guesses)) {
    if (guesserId === storytellerId) continue;
    if (storytellerSubmission && submissionId === storytellerSubmission.submission_id) {
      correct.push(guesserId);
    }
  }

  const decoyPicks: Record<string, number> = {};
  if (listenerIds.length > 0) {
    for (const pid of listenerIds) decoyPicks[pid] = 0;

    if (correct.length === 1) {
      deltas[correct[0]] += 3 * multiplier;
      deltas[storytellerId] += 3 * multiplier;
    } else if (correct.length > 0 && correct.length < listenerIds.length) {
      for (const pid of correct) deltas[pid] += 1 * multiplier;
      deltas[storytellerId] += 1 * multiplier;
    } else {
      // everyone correct OR nobody correct
      for (const pid of listenerIds) deltas[pid] += 2 * multiplier;
    }

    // Decoy bonus: a listener whose answer other listeners picked.
    for (const [guesserId, submissionId] of Object.entries(guesses)) {
      const opt = bySubmission.get(submissionId);
      if (!opt) continue;
      const ownerId = opt.owner_id;
      if (ownerId in decoyPicks && ownerId !== guesserId) {
        decoyPicks[ownerId] += 1;
      }
    }
    for (const [pid, count] of Object.entries(decoyPicks)) {
      deltas[pid] += count * multiplier;
    }
  }

  const newScores: Record<string, number> = { ...currentScores };
  for (const pid of playerIds) {
    newScores[pid] = (newScores[pid] ?? 0) + (deltas[pid] ?? 0);
  }

  const winners = playerIds.filter((pid) => (newScores[pid] ?? 0) >= maxScore);

  return { deltas, correct, decoyPicks, newScores, winners };
}
