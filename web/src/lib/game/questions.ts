import "server-only";
import { callStructured } from "@/lib/game/llm";
import { selectQuestionAngles } from "@/lib/game/angles";
import {
  SYSTEM_PROMPT,
  TRANSLATION_SYSTEM_PROMPT,
  buildCandidateSetPrompt,
  buildTranslationPrompt,
  buildAnswerPrompt,
} from "@/lib/game/prompts";
import type { Level } from "@/lib/types";

export interface Candidate {
  angle_key: string;
  question_en: string;
}

const CANDIDATE_SCHEMA = {
  name: "question_candidate_set",
  schema: {
    type: "object",
    properties: {
      candidates: {
        type: "array",
        items: {
          type: "object",
          properties: {
            rank: { type: "integer" },
            angle_key: { type: "string" },
            question: { type: "string" },
          },
          required: ["rank", "angle_key", "question"],
          additionalProperties: false,
        },
      },
    },
    required: ["candidates"],
    additionalProperties: false,
  },
} as const;

interface RawCandidateSet {
  candidates: { rank: number; angle_key: string; question: string }[];
}

export async function generateCandidatePool(opts: {
  model: string;
  theme: string;
  level: Level;
  previousQuestions: string[];
  recentAngleKeys: string[];
  count?: number;
}): Promise<Candidate[]> {
  const count = opts.count ?? 5;
  const angles = selectQuestionAngles(opts.theme, opts.level, count, opts.recentAngleKeys);
  const allowed = new Set(angles.map((a) => a.key));
  const userPrompt = buildCandidateSetPrompt({
    theme: opts.theme,
    level: opts.level,
    selectedAngles: angles,
    previousQuestions: opts.previousQuestions,
  });
  const messages = [
    { role: "system" as const, content: SYSTEM_PROMPT },
    { role: "user" as const, content: userPrompt },
  ];

  let lastError: unknown = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const raw = await callStructured<RawCandidateSet>(opts.model, messages, CANDIDATE_SCHEMA);
      const seen = new Set<string>();
      const valid: { rank: number; c: Candidate }[] = [];
      for (const item of raw.candidates ?? []) {
        const key = (item.angle_key ?? "").trim();
        const q = (item.question ?? "").trim();
        if (!allowed.has(key) || seen.has(key)) continue;
        if (!q || (q.match(/\?/g) ?? []).length !== 1) continue;
        seen.add(key);
        valid.push({ rank: item.rank, c: { angle_key: key, question_en: q } });
      }
      valid.sort((a, b) => a.rank - b.rank);
      if (valid.length > 0) return valid.map((v) => v.c);
      throw new Error("Không có câu hỏi hợp lệ trong kết quả.");
    } catch (err) {
      lastError = err;
    }
  }
  throw new Error(`Không sinh được câu hỏi: ${lastError instanceof Error ? lastError.message : lastError}`);
}

export async function translateText(opts: {
  model: string;
  text: string;
  source: string;
  target: string;
}): Promise<string> {
  const text = (opts.text ?? "").trim();
  const source = (opts.source ?? "en").toLowerCase();
  const target = (opts.target ?? "en").toLowerCase();
  if (!text || source === target) return text;
  try {
    const res = await callStructured<{ text: string }>(
      opts.model,
      [
        { role: "system", content: TRANSLATION_SYSTEM_PROMPT },
        { role: "user", content: buildTranslationPrompt(text, source, target) },
      ],
      { name: "translation", schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: false } },
    );
    return (res.text ?? "").trim() || text;
  } catch {
    return text; // graceful fallback: show English if translation fails
  }
}

export async function suggestAnswer(opts: {
  model: string;
  question: string;
  storytellerName: string;
  theme?: string;
  level?: string;
  language: string;
}): Promise<string> {
  const answerEn = await callStructured<{ answer: string }>(
    opts.model,
    [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: buildAnswerPrompt({ question: opts.question, storytellerName: opts.storytellerName, theme: opts.theme, level: opts.level }) },
    ],
    { name: "answer_suggestion", schema: { type: "object", properties: { answer: { type: "string" } }, required: ["answer"], additionalProperties: false } },
  ).then((r) => (r.answer ?? "").trim());
  if (!answerEn) return "";
  return translateText({ model: opts.model, text: answerEn, source: "en", target: opts.language });
}
