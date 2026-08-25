// Full-round integration test against the real Supabase project.
// Mirrors the exact query shapes used by the server actions.
// Run: node scripts/test-flow.mjs
import fs from "node:fs";
import { createClient } from "@supabase/supabase-js";

for (const l of fs.readFileSync(".env.local", "utf8").split("\n")) {
  const m = l.match(/^\s*([A-Z_]+)\s*=\s*(.*)$/);
  if (m) process.env[m[1]] = m[2].trim();
}
const s = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

let ok = 0, bad = 0;
const check = (label, cond) => (cond ? (ok++, console.log(`  ✅ ${label}`)) : (bad++, console.log(`  ❌ ${label}`)));

let roomId;
try {
  // 1. create room + 3 players -------------------------------------------
  const hostId = crypto.randomUUID();
  const { data: room } = await s
    .from("rooms")
    .insert({ code: "TEST" + Math.floor(Math.random() * 90 + 10), name: "flow-test", host_id: hostId })
    .select("*")
    .single();
  roomId = room.id;
  await s.from("players").insert({ id: hostId, room_id: roomId, name: "Host", role: "host" });
  const { data: p2 } = await s.from("players").insert({ room_id: roomId, name: "Bích" }).select("id").single();
  const { data: p3 } = await s.from("players").insert({ room_id: roomId, name: "Cường" }).select("id").single();
  const listeners = [p2.id, p3.id];
  check("room + 3 players created", !!roomId);

  // 2. start ---------------------------------------------------------------
  const order = [hostId, p2.id, p3.id];
  await s.from("rooms").update({ started: true, phase: "theme_selection", round: 1, turn_index: 0, storyteller_order: order }).eq("id", roomId);
  const storyteller = hostId; // order[0]

  // 3. round + theme/level/question ---------------------------------------
  const { data: round } = await s
    .from("rounds")
    .insert({ room_id: roomId, round_no: 1, storyteller_id: storyteller, theme: "Love 💖", level: "deep" })
    .select("*")
    .single();
  const q = { question: "Điều gì khiến bạn thấy được yêu?", question_en: "", angle_key: "" };
  await s.from("rounds").update({ question: q }).eq("id", round.id);
  await s.from("rooms").update({ selected_theme: "Love 💖", selected_level: "deep", question: q, phase: "answer_entry" }).eq("id", roomId);
  check("round row + jsonb question stored", !!round.id);

  // 4. submissions (upsert onConflict round_id,player_id) ------------------
  await s.from("submissions").upsert(
    [
      { round_id: round.id, player_id: storyteller, text: "Khi được lắng nghe", is_storyteller: true },
      { round_id: round.id, player_id: p2.id, text: "Khi có người nhớ điều nhỏ nhặt", is_storyteller: false },
      { round_id: round.id, player_id: p3.id, text: "Khi được ở cạnh im lặng", is_storyteller: false },
    ],
    { onConflict: "round_id,player_id" },
  );
  // edit-my-answer path re-upserts same key
  await s.from("submissions").upsert(
    { round_id: round.id, player_id: p2.id, text: "Khi có người nhớ điều nhỏ nhặt về mình", is_storyteller: false },
    { onConflict: "round_id,player_id" },
  );
  const { count: subCount } = await s.from("submissions").select("*", { count: "exact", head: true }).eq("round_id", round.id);
  check("3 submissions after upsert+edit (no dup)", subCount === 3);

  // 5. enter guessing: build shuffled options jsonb -----------------------
  const { data: subs } = await s.from("submissions").select("id, player_id, text, is_storyteller").eq("round_id", round.id);
  const options = subs.map((sub, i) => ({
    submission_id: sub.id, owner_id: sub.player_id, is_storyteller: sub.is_storyteller,
    label: String.fromCharCode(65 + i), text: sub.text,
  }));
  await s.from("rounds").update({ options }).eq("id", round.id);
  await s.from("rooms").update({ phase: "guessing" }).eq("id", roomId);
  const { data: rr } = await s.from("rounds").select("options").eq("id", round.id).single();
  check("options jsonb round-trips (array of 3)", Array.isArray(rr.options) && rr.options.length === 3);

  const storySub = subs.find((x) => x.is_storyteller).id;

  // 6. guesses: both listeners guess the storyteller correctly ------------
  await s.from("guesses").upsert(
    [
      { round_id: round.id, player_id: p2.id, submission_id: storySub },
      { round_id: round.id, player_id: p3.id, submission_id: storySub },
    ],
    { onConflict: "round_id,player_id" },
  );
  const { count: guessCount } = await s.from("guesses").select("*", { count: "exact", head: true }).eq("round_id", round.id);
  check("2 guesses recorded", guessCount === 2);

  // 7. reveal: everyone correct → each listener +2 (deep ×2 = +4), story 0
  // (scoring math itself is covered by test-scoring.ts; here we persist it)
  await s.from("players").update({ score: 4 }).in("id", listeners);
  await s.from("rounds").update({ summary: { deltas: { [p2.id]: 4, [p3.id]: 4, [storyteller]: 0 }, correct: listeners, decoy: {}, guesses: { [p2.id]: storySub, [p3.id]: storySub } } }).eq("id", round.id);
  await s.from("rooms").update({ phase: "reveal", winners: [] }).eq("id", roomId);
  const { data: scored } = await s.from("players").select("name, score").eq("room_id", roomId).order("score", { ascending: false });
  check("scores persisted (2 players at 4)", scored.filter((p) => p.score === 4).length === 2);

  // 8. next turn rotates storyteller --------------------------------------
  await s.from("rooms").update({ round: 2, turn_index: 1, phase: "theme_selection", selected_theme: null, question: null }).eq("id", roomId);
  const { data: roomAfter } = await s.from("rooms").select("round, turn_index").eq("id", roomId).single();
  check("next turn: round=2, turn_index=1", roomAfter.round === 2 && roomAfter.turn_index === 1);
} finally {
  // 9. cascade cleanup -----------------------------------------------------
  if (roomId) {
    await s.from("rooms").delete().eq("id", roomId);
    const { count } = await s.from("rounds").select("*", { count: "exact", head: true }).eq("room_id", roomId);
    check("cascade delete removed child rows", count === 0);
  }
}

console.log(`\n${bad === 0 ? "🎉 ALL PASS" : "⚠️ FAILURES"} — ${ok} passed, ${bad} failed`);
process.exit(bad === 0 ? 0 : 1);
