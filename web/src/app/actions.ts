"use server";

import { getSupabaseAdmin } from "@/lib/supabase/server";
import {
  MIN_PLAYERS_TO_START,
  SUPPORTED_LANGUAGES,
  SUPPORTED_LLM_MODELS,
  type Language,
  type RoomSettings,
} from "@/lib/types";

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no ambiguous I/O/0/1

function generateCode(length = 4): string {
  let out = "";
  for (let i = 0; i < length; i++) {
    out += CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)];
  }
  return out;
}

function cleanName(raw: string): string {
  return raw.trim().replace(/\s+/g, " ").slice(0, 40);
}

function normalizeSettings(input: Partial<RoomSettings> | undefined): RoomSettings {
  const language = (input?.language && SUPPORTED_LANGUAGES[input.language as Language]
    ? input.language
    : "en") as Language;
  const llm_model =
    input?.llm_model && SUPPORTED_LLM_MODELS[input.llm_model]
      ? input.llm_model
      : "gemini-2.5-flash";
  let max_score = Number(input?.max_score ?? 100);
  if (!Number.isFinite(max_score)) max_score = 100;
  max_score = Math.min(1000, Math.max(10, Math.round(max_score)));
  return { max_score, language, llm_model };
}

// ---------------------------------------------------------------------------
// Create room
// ---------------------------------------------------------------------------
export async function createRoom(input: {
  hostName: string;
  roomName: string;
  settings?: Partial<RoomSettings>;
}): Promise<ActionResult<{ code: string; playerId: string }>> {
  const hostName = cleanName(input.hostName ?? "");
  const roomName = cleanName(input.roomName ?? "");
  if (!hostName) return { ok: false, error: "Cần nhập tên của bạn." };
  if (!roomName) return { ok: false, error: "Cần nhập tên phòng." };

  const supabase = getSupabaseAdmin();
  const settings = normalizeSettings(input.settings);
  const hostId = crypto.randomUUID();

  // Try a few codes in case of a rare collision.
  for (let attempt = 0; attempt < 6; attempt++) {
    const code = generateCode(attempt < 4 ? 4 : 5);
    const { error: roomError } = await supabase.from("rooms").insert({
      code,
      name: roomName,
      host_id: hostId,
      settings,
    });
    if (roomError) {
      if (roomError.code === "23505") continue; // unique violation → new code
      return { ok: false, error: roomError.message };
    }
    // Fetch the new room's id, then insert the host player (id == host_id).
    const { data: room } = await supabase
      .from("rooms")
      .select("id")
      .eq("code", code)
      .single();
    if (!room) return { ok: false, error: "Không tạo được phòng." };
    const { error: hostInsertError } = await supabase.from("players").insert({
      id: hostId,
      room_id: room.id,
      name: hostName,
      role: "host",
    });
    if (hostInsertError) return { ok: false, error: hostInsertError.message };
    return { ok: true, data: { code, playerId: hostId } };
  }
  return { ok: false, error: "Không tạo được mã phòng, thử lại nhé." };
}

// ---------------------------------------------------------------------------
// Join room
// ---------------------------------------------------------------------------
export async function joinRoom(input: {
  code: string;
  name: string;
}): Promise<ActionResult<{ code: string; playerId: string }>> {
  const code = (input.code ?? "").trim().toUpperCase();
  const name = cleanName(input.name ?? "");
  if (!code) return { ok: false, error: "Cần nhập mã phòng." };
  if (!name) return { ok: false, error: "Cần nhập tên của bạn." };

  const supabase = getSupabaseAdmin();
  const { data: room } = await supabase
    .from("rooms")
    .select("id, started")
    .eq("code", code)
    .single();
  if (!room) return { ok: false, error: "Không tìm thấy phòng với mã này." };
  if (room.started) {
    return { ok: false, error: "Ván đã bắt đầu rồi (tính năng vào lại sẽ có sau)." };
  }

  const { data: player, error } = await supabase
    .from("players")
    .insert({ room_id: room.id, name, role: "joiner" })
    .select("id")
    .single();
  if (error || !player) return { ok: false, error: error?.message ?? "Không vào được phòng." };
  return { ok: true, data: { code, playerId: player.id } };
}

// ---------------------------------------------------------------------------
// Lobby management (host only — enforced by passing hostId)
// ---------------------------------------------------------------------------
type HostRoom = { id: string; host_id: string; started: boolean };
type HostGuard = { ok: true; room: HostRoom } | { ok: false; error: string };

async function assertHost(code: string, hostId: string): Promise<HostGuard> {
  const supabase = getSupabaseAdmin();
  const { data: room } = await supabase
    .from("rooms")
    .select("id, host_id, started")
    .eq("code", code.trim().toUpperCase())
    .single<HostRoom>();
  if (!room) return { ok: false, error: "Không tìm thấy phòng." };
  if (room.host_id !== hostId) return { ok: false, error: "Chỉ chủ phòng mới làm được việc này." };
  return { ok: true, room };
}

export async function updateSettings(input: {
  code: string;
  hostId: string;
  settings: Partial<RoomSettings>;
}): Promise<ActionResult<null>> {
  const guard = await assertHost(input.code, input.hostId);
  if (!guard.ok) return { ok: false, error: guard.error };
  const supabase = getSupabaseAdmin();
  const { data: current } = await supabase
    .from("rooms")
    .select("settings")
    .eq("id", guard.room.id)
    .single();
  const merged = normalizeSettings({ ...(current?.settings ?? {}), ...input.settings });
  const { error } = await supabase
    .from("rooms")
    .update({ settings: merged, updated_at: new Date().toISOString() })
    .eq("id", guard.room.id);
  if (error) return { ok: false, error: error.message };
  return { ok: true, data: null };
}

export async function removePlayer(input: {
  code: string;
  hostId: string;
  playerId: string;
}): Promise<ActionResult<null>> {
  const guard = await assertHost(input.code, input.hostId);
  if (!guard.ok) return { ok: false, error: guard.error };
  if (input.playerId === input.hostId) {
    return { ok: false, error: "Không thể tự xoá chủ phòng." };
  }
  const supabase = getSupabaseAdmin();
  const { error } = await supabase
    .from("players")
    .delete()
    .eq("id", input.playerId)
    .eq("room_id", guard.room.id);
  if (error) return { ok: false, error: error.message };
  return { ok: true, data: null };
}

export async function leaveRoom(input: {
  code: string;
  playerId: string;
}): Promise<ActionResult<null>> {
  const supabase = getSupabaseAdmin();
  const { data: room } = await supabase
    .from("rooms")
    .select("id, host_id, started")
    .eq("code", input.code.trim().toUpperCase())
    .single();
  if (!room) return { ok: true, data: null };
  // Host leaving a not-yet-started room deletes the whole room.
  if (room.host_id === input.playerId && !room.started) {
    await supabase.from("rooms").delete().eq("id", room.id);
    return { ok: true, data: null };
  }
  await supabase.from("players").delete().eq("id", input.playerId).eq("room_id", room.id);
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------
// Start game (Phase 1 sets up the initial round state; the in-game screen
// comes in Phase 2).
// ---------------------------------------------------------------------------
export async function startGame(input: {
  code: string;
  hostId: string;
}): Promise<ActionResult<null>> {
  const guard = await assertHost(input.code, input.hostId);
  if (!guard.ok) return { ok: false, error: guard.error };
  const supabase = getSupabaseAdmin();

  const { data: players } = await supabase
    .from("players")
    .select("id")
    .eq("room_id", guard.room.id)
    .order("joined_at", { ascending: true });
  if (!players || players.length < MIN_PLAYERS_TO_START) {
    return { ok: false, error: `Cần ít nhất ${MIN_PLAYERS_TO_START} người để bắt đầu.` };
  }

  const order = players.map((p) => p.id);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }

  const { error } = await supabase
    .from("rooms")
    .update({
      started: true,
      phase: "theme_selection",
      round: 1,
      turn_index: 0,
      storyteller_order: order,
      selected_theme: null,
      selected_level: null,
      question: null,
      winners: [],
      end_reason: null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", guard.room.id);
  if (error) return { ok: false, error: error.message };

  // Reset scores at game start.
  await supabase.from("players").update({ score: 0 }).eq("room_id", guard.room.id);
  return { ok: true, data: null };
}

// ---------------------------------------------------------------------------
// End game → back to lobby (host only)
// ---------------------------------------------------------------------------
export async function endGame(input: {
  code: string;
  hostId: string;
}): Promise<ActionResult<null>> {
  const guard = await assertHost(input.code, input.hostId);
  if (!guard.ok) return { ok: false, error: guard.error };
  const supabase = getSupabaseAdmin();
  const { error } = await supabase
    .from("rooms")
    .update({
      started: false,
      phase: null,
      round: 0,
      selected_theme: null,
      selected_level: null,
      question: null,
      winners: [],
      end_reason: null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", guard.room.id);
  if (error) return { ok: false, error: error.message };
  return { ok: true, data: null };
}
