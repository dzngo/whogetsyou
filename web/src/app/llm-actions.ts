"use server";

import { getSupabaseAdmin } from "@/lib/supabase/server";
import { generateCandidatePool, translateText, suggestAnswer, type Candidate } from "@/lib/game/questions";
import { SUPPORTED_LLM_MODELS, DEFAULT_LLM_MODEL, type Level, type Room } from "@/lib/types";

// Fall back to a current model if a room was created with a since-retired one.
function modelOf(room: Room): string {
  const m = room.settings.llm_model;
  return SUPPORTED_LLM_MODELS[m] ? m : DEFAULT_LLM_MODEL;
}

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

interface QuestionDraft {
  question: string;
  question_en: string;
  angle_key: string;
  pool?: Candidate[];
  index?: number;
}

async function loadRoom(code: string): Promise<Room | null> {
  const supabase = getSupabaseAdmin();
  const { data } = await supabase.from("rooms").select("*").eq("code", code.trim().toUpperCase()).maybeSingle<Room>();
  return data ?? null;
}

function storytellerId(room: Room): string | null {
  return room.storyteller_order[room.turn_index] ?? null;
}

async function priorContext(roomId: string, roundNo: number) {
  const supabase = getSupabaseAdmin();
  const { data } = await supabase
    .from("rounds")
    .select("question")
    .eq("room_id", roomId)
    .lt("round_no", roundNo);
  const previousQuestions: string[] = [];
  const recentAngleKeys: string[] = [];
  for (const r of data ?? []) {
    const q = r.question as QuestionDraft | null;
    if (q?.question_en) previousQuestions.push(q.question_en);
    if (q?.angle_key) recentAngleKeys.push(q.angle_key);
  }
  return { previousQuestions, recentAngleKeys };
}

async function produceFromPool(room: Room, pool: Candidate[], index: number): Promise<ActionResult<{ question: string }>> {
  const supabase = getSupabaseAdmin();
  const current = pool[index];
  const translated = await translateText({
    model: modelOf(room),
    text: current.question_en,
    source: "en",
    target: room.settings.language,
  });
  const draft: QuestionDraft = {
    question: translated,
    question_en: current.question_en,
    angle_key: current.angle_key,
    pool,
    index,
  };
  await supabase.from("rooms").update({ question: draft, updated_at: new Date().toISOString() }).eq("id", room.id);
  return { ok: true, data: { question: translated } };
}

async function freshPool(room: Room): Promise<ActionResult<{ question: string }>> {
  const { previousQuestions, recentAngleKeys } = await priorContext(room.id, room.round);
  const pool = await generateCandidatePool({
    model: modelOf(room),
    theme: room.selected_theme ?? "Random 🎲",
    level: (room.selected_level ?? "shallow") as Level,
    previousQuestions,
    recentAngleKeys,
  });
  return produceFromPool(room, pool, 0);
}

// ---------------------------------------------------------------------------
// Generate the first AI question for the round.
// ---------------------------------------------------------------------------
export async function generateQuestion(input: {
  code: string;
  playerId: string;
}): Promise<ActionResult<{ question: string }>> {
  const room = await loadRoom(input.code);
  if (!room) return { ok: false, error: "Không tìm thấy phòng." };
  if (storytellerId(room) !== input.playerId)
    return { ok: false, error: "Chỉ người kể chuyện mới sinh câu hỏi." };
  if (!room.selected_theme || !room.selected_level)
    return { ok: false, error: "Chưa chọn chủ đề/mức độ." };
  try {
    return await freshPool(room);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Lỗi sinh câu hỏi." };
  }
}

// ---------------------------------------------------------------------------
// Regenerate: next candidate in the pool, or a brand-new set when exhausted.
// ---------------------------------------------------------------------------
export async function regenerateQuestion(input: {
  code: string;
  playerId: string;
}): Promise<ActionResult<{ question: string }>> {
  const room = await loadRoom(input.code);
  if (!room) return { ok: false, error: "Không tìm thấy phòng." };
  if (storytellerId(room) !== input.playerId)
    return { ok: false, error: "Chỉ người kể chuyện mới đổi câu hỏi." };
  const draft = room.question as QuestionDraft | null;
  try {
    if (draft?.pool && typeof draft.index === "number" && draft.index + 1 < draft.pool.length) {
      return await produceFromPool(room, draft.pool, draft.index + 1);
    }
    return await freshPool(room);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Lỗi đổi câu hỏi." };
  }
}

// ---------------------------------------------------------------------------
// Answer helper: suggest an answer for the current player (does not submit).
// ---------------------------------------------------------------------------
export async function suggestMyAnswer(input: {
  code: string;
  playerId: string;
}): Promise<ActionResult<{ answer: string }>> {
  const room = await loadRoom(input.code);
  if (!room) return { ok: false, error: "Không tìm thấy phòng." };
  if (room.phase !== "answer_entry") return { ok: false, error: "Chưa tới lúc trả lời." };
  const draft = room.question as QuestionDraft | null;
  if (!draft) return { ok: false, error: "Chưa có câu hỏi." };
  const supabase = getSupabaseAdmin();
  const { data: player } = await supabase.from("players").select("name").eq("id", input.playerId).maybeSingle<{ name: string }>();
  try {
    const answer = await suggestAnswer({
      model: modelOf(room),
      question: draft.question_en || draft.question,
      storytellerName: player?.name ?? "the player",
      theme: room.selected_theme ?? "",
      level: room.selected_level ?? "",
      language: room.settings.language,
    });
    return { ok: true, data: { answer } };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Lỗi gợi ý." };
  }
}
