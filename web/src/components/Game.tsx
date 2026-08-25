"use client";

import { useState, useEffect, useRef } from "react";
import {
  selectTheme,
  selectLevel,
  setQuestion,
  backToPhase,
  submitAnswer,
  submitGuess,
  forceGuessing,
  forceReveal,
  nextTurn,
  finishGameEarly,
} from "@/app/game-actions";
import { generateQuestion, regenerateQuestion, suggestMyAnswer } from "@/app/llm-actions";
import { endGame } from "@/app/actions";
import { DEFAULT_THEMES, LEVELS } from "@/lib/game/themes";
import type { Guess, Player, Room, Round, Submission } from "@/lib/types";
import { PageShell, Brand, Card, Button, Notice, LiveBadge } from "@/components/ui";

interface GameProps {
  room: Room;
  players: Player[];
  round: Round | null;
  submissions: Submission[];
  guesses: Guess[];
  identity: { playerId: string; name: string };
  live: boolean;
}

export default function Game(props: GameProps) {
  const { room, players, identity } = props;
  const storytellerId = room.storyteller_order[room.turn_index] ?? null;
  const isStoryteller = identity.playerId === storytellerId;
  const isHost = identity.playerId === room.host_id;
  const nameOf = (id: string | null) => players.find((p) => p.id === id)?.name ?? "…";

  const ctx = { ...props, storytellerId, isStoryteller, isHost, nameOf };

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-4">
        <Brand small />
        <LiveBadge live={props.live} />
      </div>

      {!props.live ? (
        <div className="mb-3 text-xs text-center text-warn bg-warn/10 border border-warn/30 rounded-lg py-1.5">
          Mất kết nối — đang thử lại…
        </div>
      ) : null}

      {room.phase !== "results" ? <Board {...ctx} /> : null}

      <div className="mt-4 wg-phase" key={room.phase ?? "none"}>
        {room.phase === "theme_selection" && <ThemePhase {...ctx} />}
        {room.phase === "level_selection" && <LevelPhase {...ctx} />}
        {room.phase === "question_generation" && <QuestionPhase {...ctx} />}
        {room.phase === "answer_entry" && <AnswerPhase {...ctx} />}
        {room.phase === "guessing" && <GuessPhase {...ctx} />}
        {room.phase === "reveal" && <RevealPhase {...ctx} />}
        {room.phase === "results" && <ResultsView {...ctx} />}
      </div>

      {isHost && room.phase !== "results" ? <HostControls {...ctx} /> : null}
    </PageShell>
  );
}

// --------------------------------------------------------------------------
// Host controls: skip a stuck storyteller, or end the game early.
// --------------------------------------------------------------------------
function HostControls({ room, identity }: Ctx) {
  const [open, setOpen] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [busy, setBusy] = useState(false);

  return (
    <div className="mt-8 pt-4 border-t border-border">
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="text-xs text-ink-faint hover:text-ink cursor-pointer mx-auto block"
        >
          ⚙️ Điều khiển chủ phòng
        </button>
      ) : (
        <div className="flex flex-col gap-2">
          {confirmEnd ? (
            <div className="rounded-xl border border-border bg-surface-2 p-3">
              <p className="text-sm text-ink mb-2">Kết thúc ván ngay bây giờ? Người điểm cao nhất sẽ thắng.</p>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setConfirmEnd(false)}>Không</Button>
                <Button
                  variant="danger"
                  full
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    await finishGameEarly({ code: room.code, hostId: identity.playerId });
                  }}
                >
                  {busy ? "…" : "Kết thúc & xem kết quả"}
                </Button>
              </div>
            </div>
          ) : (
            <>
              <button
                onClick={() => nextTurn({ code: room.code, playerId: identity.playerId })}
                className="text-sm text-ink-soft hover:text-ink cursor-pointer text-left px-1"
              >
                ⏭️ Bỏ qua lượt này (nếu người kể chuyện rời đi / bị kẹt)
              </button>
              <button
                onClick={() => setConfirmEnd(true)}
                className="text-sm text-[color:var(--accent-ink)] hover:underline cursor-pointer text-left px-1"
              >
                🏁 Kết thúc sớm ván này
              </button>
              <button
                onClick={() => setOpen(false)}
                className="text-xs text-ink-faint hover:text-ink cursor-pointer mx-auto mt-1"
              >
                đóng
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

type Ctx = GameProps & {
  storytellerId: string | null;
  isStoryteller: boolean;
  isHost: boolean;
  nameOf: (id: string | null) => string;
};

// --------------------------------------------------------------------------
// Board: scoreboard + round context
// --------------------------------------------------------------------------
function Board({ room, players, storytellerId, identity, nameOf }: Ctx) {
  const ranked = [...players].sort((a, b) => b.score - a.score);
  const meIsStory = identity.playerId === storytellerId;
  return (
    <Card className="!p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-mono uppercase tracking-wider text-ink-faint">
          Vòng {room.round} · điểm thắng {room.settings.max_score}
        </span>
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-md"
          style={{ background: "var(--accent-soft)", color: "var(--accent-ink)" }}
        >
          {meIsStory ? "Bạn kể chuyện 🎙️" : `Kể chuyện: ${nameOf(storytellerId)}`}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {ranked.map((p) => {
          const isStory = p.id === storytellerId;
          const me = p.id === identity.playerId;
          return (
            <span
              key={p.id}
              className="inline-flex items-center gap-1.5 text-sm px-2.5 py-1 rounded-lg border"
              style={{
                borderColor: me ? "var(--accent)" : "var(--border)",
                background: "var(--surface-2)",
              }}
            >
              {isStory ? "🎙️" : ""}
              <span className="text-ink font-medium">{p.name}</span>
              <span className="font-mono font-semibold text-ink-soft tabular-nums">{p.score}</span>
            </span>
          );
        })}
      </div>
    </Card>
  );
}

function WaitingCard({ text }: { text: string }) {
  return (
    <Card className="text-center py-8">
      <div className="text-2xl mb-2 animate-pulse">⏳</div>
      <p className="text-ink-soft text-sm">{text}</p>
    </Card>
  );
}

function QuestionBanner({ text }: { text: string }) {
  return (
    <div
      className="rounded-2xl p-4 mb-4 border"
      style={{ background: "var(--accent-soft)", borderColor: "var(--accent)" }}
    >
      <p className="text-xs font-mono uppercase tracking-wider text-accent-ink mb-1">Câu hỏi</p>
      <p className="text-ink font-display font-semibold text-lg leading-snug">{text}</p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 1: theme selection
// --------------------------------------------------------------------------
function ThemePhase({ room, identity, isStoryteller, nameOf, storytellerId }: Ctx) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!isStoryteller) return <WaitingCard text={`${nameOf(storytellerId)} đang chọn chủ đề…`} />;
  return (
    <div>
      <h2 className="font-display font-semibold text-ink text-xl mb-1">Chọn chủ đề</h2>
      <p className="text-ink-soft text-sm mb-4">Bạn là người kể chuyện vòng này.</p>
      <div className="grid grid-cols-2 gap-2.5">
        {DEFAULT_THEMES.map((theme) => (
          <button
            key={theme}
            disabled={!!busy}
            onClick={async () => {
              setBusy(theme);
              await selectTheme({ code: room.code, playerId: identity.playerId, theme });
            }}
            className="text-left bg-surface border border-border rounded-2xl px-4 py-3.5 text-ink font-medium hover:border-accent transition disabled:opacity-50 cursor-pointer"
          >
            {theme}
          </button>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 2: level selection
// --------------------------------------------------------------------------
function LevelPhase({ room, identity, isStoryteller, nameOf, storytellerId }: Ctx) {
  const [busy, setBusy] = useState(false);
  if (!isStoryteller) return <WaitingCard text={`${nameOf(storytellerId)} đang chọn mức độ…`} />;
  return (
    <div>
      <p className="text-sm text-ink-soft mb-1">Chủ đề: <strong className="text-ink">{room.selected_theme}</strong></p>
      <h2 className="font-display font-semibold text-ink text-xl mb-4">Chọn mức độ</h2>
      <div className="flex flex-col gap-3">
        {LEVELS.map((lvl) => (
          <button
            key={lvl.key}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await selectLevel({ code: room.code, playerId: identity.playerId, level: lvl.key });
            }}
            className="text-left bg-surface border border-border rounded-2xl px-4 py-4 hover:border-accent transition disabled:opacity-50 cursor-pointer"
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-xl">{lvl.emoji}</span>
              <span className="text-ink font-semibold">{lvl.label}</span>
            </div>
            <p className="text-xs text-ink-faint">{lvl.hint}</p>
          </button>
        ))}
      </div>
      <BackRow code={room.code} playerId={identity.playerId} to="theme_selection" label="← Đổi chủ đề" />
    </div>
  );
}

function BackRow({ code, playerId, to, label }: { code: string; playerId: string; to: "theme_selection" | "level_selection"; label: string }) {
  return (
    <button
      onClick={() => backToPhase({ code, playerId, phase: to })}
      className="mt-4 text-sm text-ink-faint hover:text-accent-ink cursor-pointer"
    >
      {label}
    </button>
  );
}

// --------------------------------------------------------------------------
// Phase 3: question (Phase 2 = typed manually; AI comes in Phase 3)
// --------------------------------------------------------------------------
function QuestionPhase({ room, identity, isStoryteller, nameOf, storytellerId }: Ctx) {
  const question = room.question?.question ?? "";
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "gen" | "regen" | "confirm">(null);
  const requested = useRef(false);

  // Auto-generate the first question once, when the storyteller lands here.
  useEffect(() => {
    if (!isStoryteller || question || requested.current) return;
    requested.current = true;
    setBusy("gen");
    generateQuestion({ code: room.code, playerId: identity.playerId }).then((res) => {
      if (!res.ok) setError(res.error);
      setBusy(null);
    });
  }, [isStoryteller, question, room.code, identity.playerId]);

  if (!isStoryteller) return <WaitingCard text={`${nameOf(storytellerId)} đang soạn câu hỏi…`} />;

  async function regen() {
    setError(null);
    setBusy("regen");
    const res = await regenerateQuestion({ code: room.code, playerId: identity.playerId });
    if (!res.ok) setError(res.error);
    setBusy(null);
  }

  async function confirm(text: string) {
    setError(null);
    setBusy("confirm");
    const res = await setQuestion({ code: room.code, playerId: identity.playerId, question: text });
    if (!res.ok) {
      setError(res.error);
      setBusy(null);
    }
  }

  const header = (
    <>
      <p className="text-sm text-ink-soft mb-1">
        {room.selected_theme} · {room.selected_level === "deep" ? "Sâu sắc 🌊" : "Nhẹ nhàng 🫧"}
      </p>
      <h2 className="font-display font-semibold text-ink text-xl mb-3">Câu hỏi cho vòng này</h2>
    </>
  );

  if (busy === "gen" && !question) {
    return (
      <div>
        {header}
        <Card className="text-center py-8">
          <div className="text-2xl mb-2 animate-pulse">🤖</div>
          <p className="text-ink-soft text-sm">AI đang nghĩ câu hỏi…</p>
        </Card>
      </div>
    );
  }

  if (editing) {
    return (
      <div>
        {header}
        <textarea
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          rows={3}
          maxLength={200}
          autoFocus
          className="w-full bg-surface border border-border-strong rounded-xl px-3.5 py-3 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-none"
        />
        {error ? <div className="mt-3"><Notice>{error}</Notice></div> : null}
        <div className="flex gap-2 mt-3">
          <Button variant="secondary" onClick={() => setEditing(false)}>Huỷ</Button>
          <Button full onClick={() => confirm(editText)} disabled={busy === "confirm" || editText.trim().length < 4}>
            {busy === "confirm" ? "…" : "Dùng câu này →"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {header}
      <QuestionBanner text={question || "…"} />
      {error ? <div className="mb-3"><Notice>{error}</Notice></div> : null}

      <div className="grid grid-cols-2 gap-2 mb-2">
        <Button variant="secondary" onClick={regen} disabled={!!busy || !question}>
          {busy === "regen" ? "Đang đổi…" : "🔄 Câu khác"}
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            setEditText(question);
            setEditing(true);
          }}
          disabled={!!busy || !question}
        >
          ✏️ Sửa
        </Button>
      </div>
      <Button size="lg" full onClick={() => confirm(question)} disabled={!!busy || !question}>
        {busy === "confirm" ? "…" : "Dùng câu này →"}
      </Button>
      <BackRow code={room.code} playerId={identity.playerId} to="level_selection" label="← Đổi mức độ" />
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 4: answer entry
// --------------------------------------------------------------------------
function AnswerPhase({ room, players, submissions, identity, isHost }: Ctx) {
  const mine = submissions.find((s) => s.player_id === identity.playerId);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(!mine);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const question = room.question?.question ?? "";

  async function suggest() {
    setSuggesting(true);
    const res = await suggestMyAnswer({ code: room.code, playerId: identity.playerId });
    if (res.ok) setText(res.data.answer);
    else setError(res.error);
    setSuggesting(false);
  }

  async function send() {
    setError(null);
    setBusy(true);
    const res = await submitAnswer({ code: room.code, playerId: identity.playerId, text });
    if (!res.ok) {
      setError(res.error);
      setBusy(false);
      return;
    }
    setEditing(false);
    setBusy(false);
  }

  return (
    <div>
      <QuestionBanner text={question} />
      <p className="text-sm text-ink-soft mb-3">
        Mọi người viết một câu trả lời (kể cả người kể chuyện). Đừng để lộ ai viết gì nhé.
      </p>

      {mine && !editing ? (
        <Card className="mb-3">
          <p className="text-xs text-ink-faint mb-1">Câu trả lời của bạn</p>
          <p className="text-ink font-medium">{mine.text}</p>
          <button
            onClick={() => {
              setText(mine.text);
              setEditing(true);
            }}
            className="mt-2 text-sm text-accent-ink cursor-pointer"
          >
            Sửa
          </button>
        </Card>
      ) : (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Câu trả lời của bạn…"
            rows={2}
            maxLength={200}
            className="w-full bg-surface border border-border-strong rounded-xl px-3.5 py-3 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-none"
          />
          {error ? <div className="mt-3"><Notice>{error}</Notice></div> : null}
          <div className="flex justify-end mt-2">
            <button
              onClick={suggest}
              disabled={suggesting}
              className="text-sm text-accent-ink hover:underline cursor-pointer disabled:opacity-50"
            >
              {suggesting ? "Đang nghĩ…" : "✨ Gợi ý từ AI"}
            </button>
          </div>
          <Button size="lg" full className="mt-1" onClick={send} disabled={busy || !text.trim()}>
            {busy ? "…" : mine ? "Cập nhật" : "Nộp câu trả lời →"}
          </Button>
        </>
      )}

      <ProgressRow done={submissions.length} total={players.length} label="đã trả lời" />

      {isHost && submissions.length >= 2 ? (
        <button
          onClick={() => forceGuessing({ code: room.code, hostId: identity.playerId })}
          className="mt-3 w-full text-center text-sm text-ink-faint hover:text-accent-ink cursor-pointer"
        >
          (Chủ phòng) Bắt đầu đoán ngay
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 5: guessing
// --------------------------------------------------------------------------
function GuessPhase({ room, round, guesses, identity, isStoryteller, isHost }: Ctx) {
  const options = round?.options ?? [];
  const myGuess = guesses.find((g) => g.player_id === identity.playerId);
  const listenerTotal = room.storyteller_order.length - 1;
  const [busy, setBusy] = useState(false);

  async function pick(submissionId: string) {
    setBusy(true);
    await submitGuess({ code: room.code, playerId: identity.playerId, submissionId });
    setBusy(false);
  }

  return (
    <div>
      <QuestionBanner text={room.question?.question ?? ""} />
      {isStoryteller ? (
        <Card className="mb-3 text-center py-6">
          <div className="text-2xl mb-1">🕵️</div>
          <p className="text-ink-soft text-sm">Mọi người đang đoán đâu là câu của bạn…</p>
        </Card>
      ) : (
        <p className="text-sm text-ink-soft mb-3">Đâu là câu trả lời của người kể chuyện?</p>
      )}

      <div className="flex flex-col gap-2.5">
        {options.map((opt) => {
          const mineOwn = opt.owner_id === identity.playerId;
          const picked = myGuess?.submission_id === opt.submission_id;
          const disabled = isStoryteller || mineOwn || busy;
          return (
            <button
              key={opt.submission_id}
              disabled={disabled}
              onClick={() => pick(opt.submission_id)}
              className="text-left rounded-2xl px-4 py-3.5 border transition disabled:cursor-not-allowed cursor-pointer flex items-center gap-3"
              style={{
                borderColor: picked ? "var(--accent)" : "var(--border)",
                background: picked ? "var(--accent-soft)" : "var(--surface)",
                opacity: mineOwn && !isStoryteller ? 0.55 : 1,
              }}
            >
              <span className="font-mono font-semibold text-ink-faint">{opt.label}</span>
              <span className="text-ink flex-1">{opt.text}</span>
              {mineOwn ? <span className="text-xs text-ink-faint">của bạn</span> : null}
              {picked ? <span className="text-accent-ink">✓</span> : null}
            </button>
          );
        })}
      </div>

      <ProgressRow done={guesses.length} total={listenerTotal} label="đã đoán" />

      {isHost && guesses.length >= 1 ? (
        <button
          onClick={() => forceReveal({ code: room.code, hostId: identity.playerId })}
          className="mt-3 w-full text-center text-sm text-ink-faint hover:text-accent-ink cursor-pointer"
        >
          (Chủ phòng) Lật bài ngay
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 6: reveal & scoring
// --------------------------------------------------------------------------
function RevealPhase({ room, round, players, identity, isStoryteller, isHost, nameOf, storytellerId }: Ctx) {
  const options = round?.options ?? [];
  const summary = round?.summary;
  const deltas = summary?.deltas ?? {};
  const guessesMap = summary?.guesses ?? {};

  // group guessers by chosen submission
  const guessersBy: Record<string, string[]> = {};
  for (const [pid, sid] of Object.entries(guessesMap)) {
    (guessersBy[sid] ??= []).push(nameOf(pid));
  }

  const canAdvance = isStoryteller || isHost;

  return (
    <div>
      <QuestionBanner text={room.question?.question ?? ""} />
      <h2 className="font-display font-semibold text-ink text-xl mb-3">Lật bài</h2>

      <div className="flex flex-col gap-2.5 mb-4">
        {options.map((opt) => {
          const guessers = guessersBy[opt.submission_id] ?? [];
          return (
            <div
              key={opt.submission_id}
              className="rounded-2xl px-4 py-3 border"
              style={{
                borderColor: opt.is_storyteller ? "var(--good)" : "var(--border)",
                background: opt.is_storyteller ? "color-mix(in srgb, var(--good) 12%, var(--surface))" : "var(--surface)",
              }}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono font-semibold text-ink-faint">{opt.label}</span>
                <span className="text-ink flex-1">{opt.text}</span>
                {opt.is_storyteller ? (
                  <span className="text-xs font-semibold" style={{ color: "var(--good)" }}>
                    ✓ câu thật
                  </span>
                ) : (
                  <span className="text-xs text-ink-faint">{nameOf(opt.owner_id)}</span>
                )}
              </div>
              {guessers.length > 0 ? (
                <p className="text-xs text-ink-faint mt-1.5">đoán bởi: {guessers.join(", ")}</p>
              ) : null}
            </div>
          );
        })}
      </div>

      <Card className="mb-4">
        <p className="text-xs font-mono uppercase tracking-wider text-ink-faint mb-2">Điểm vòng này</p>
        <ul className="flex flex-col gap-1">
          {players.map((p) => {
            const d = deltas[p.id] ?? 0;
            return (
              <li key={p.id} className="flex items-center justify-between text-sm">
                <span className="text-ink">
                  {p.name}
                  {p.id === storytellerId ? " 🎙️" : ""}
                </span>
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ color: d > 0 ? "var(--good)" : "var(--ink-faint)" }}
                >
                  {d > 0 ? `+${d}` : "0"}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>

      {room.winners.length > 0 ? (
        <Notice tone="info">🏆 Có người đạt điểm thắng! Bấm tiếp để xem kết quả.</Notice>
      ) : null}

      {canAdvance ? (
        <Button
          size="lg"
          full
          className="mt-3"
          onClick={() => nextTurn({ code: room.code, playerId: identity.playerId })}
        >
          {room.winners.length > 0 ? "Xem kết quả →" : "Vòng tiếp theo →"}
        </Button>
      ) : (
        <p className="text-center text-sm text-ink-soft mt-3">Chờ {nameOf(storytellerId)} sang vòng mới…</p>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Phase 7: results
// --------------------------------------------------------------------------
function ResultsView({ room, players, identity, isHost }: Ctx) {
  const ranked = [...players].sort((a, b) => b.score - a.score);
  const top = ranked[0]?.score ?? 0;
  const winners = ranked.filter((p) => p.score === top && top > 0);

  return (
    <PageShellInner>
      <div className="text-center py-4">
        <div className="text-5xl mb-2">🏆</div>
        <p className="text-xs font-mono uppercase tracking-widest text-ink-faint">Kết thúc</p>
        <h2 className="font-display font-semibold text-ink text-2xl mt-1">
          {winners.map((w) => w.name).join(" + ") || "Không có người thắng"}
        </h2>
        <p className="text-ink-soft text-sm mt-1">{room.end_reason ?? "Ván đã kết thúc."}</p>
      </div>

      <Card className="!p-2 mb-4">
        <ul className="flex flex-col">
          {ranked.map((p, i) => (
            <li
              key={p.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
              style={{ background: i === 0 ? "var(--accent-soft)" : "transparent" }}
            >
              <span className="font-mono text-ink-faint w-6 tabular-nums">{i + 1}</span>
              <span className="flex-1 text-ink font-medium">{p.name}</span>
              <span className="font-mono font-semibold text-ink tabular-nums">{p.score}</span>
            </li>
          ))}
        </ul>
      </Card>

      {isHost ? (
        <Button
          size="lg"
          full
          onClick={() => endGame({ code: room.code, hostId: identity.playerId })}
        >
          Về lobby (chơi lại)
        </Button>
      ) : (
        <p className="text-center text-sm text-ink-soft">Chờ chủ phòng bắt đầu ván mới…</p>
      )}
    </PageShellInner>
  );
}

function PageShellInner({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>;
}

// --------------------------------------------------------------------------
function ProgressRow({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between text-xs text-ink-faint mb-1.5">
        <span>{label}</span>
        <span className="font-mono tabular-nums">{done}/{total}</span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: "var(--accent)" }}
        />
      </div>
    </div>
  );
}
