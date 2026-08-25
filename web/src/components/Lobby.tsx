"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { startGame, updateSettings, removePlayer, leaveRoom } from "@/app/actions";
import { forgetIdentity } from "@/lib/identity";
import {
  MIN_PLAYERS_TO_START,
  SUPPORTED_LANGUAGES,
  LANGUAGE_FLAGS,
  SUPPORTED_LLM_MODELS,
  type Player,
  type Room,
} from "@/lib/types";
import { PageShell, Brand, Card, Button, Notice, LiveBadge } from "@/components/ui";

export default function Lobby({
  room,
  players,
  identity,
  live,
}: {
  room: Room;
  players: Player[];
  identity: { playerId: string; name: string };
  live: boolean;
}) {
  const code = room.code;
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const isHost = room.host_id === identity.playerId;
  const canStart = players.length >= MIN_PLAYERS_TO_START;

  const shareUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/join?code=${code}`;
  }, [code]);

  async function handleStart() {
    setError(null);
    setBusy(true);
    const res = await startGame({ code, hostId: identity.playerId });
    if (!res.ok) setError(res.error);
    setBusy(false);
  }

  async function handleMaxScore(delta: number) {
    const next = Math.min(1000, Math.max(10, room.settings.max_score + delta));
    await updateSettings({ code, hostId: identity.playerId, settings: { max_score: next } });
  }

  async function handleRemove(playerId: string) {
    await removePlayer({ code, hostId: identity.playerId, playerId });
  }

  async function handleLeave() {
    await leaveRoom({ code, playerId: identity.playerId });
    forgetIdentity(code);
    router.push("/");
  }

  async function copyShare() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-5">
        <Brand small />
        <LiveBadge live={live} />
      </div>

      <Card className="text-center mb-4">
        <p className="text-xs uppercase tracking-widest text-ink-faint font-mono mb-2">{room.name}</p>
        <div className="font-mono font-semibold text-ink text-4xl tracking-[0.4em] pl-[0.4em]">
          {code}
        </div>
        <button
          onClick={copyShare}
          className="mt-3 text-sm text-accent-ink font-semibold cursor-pointer hover:underline"
        >
          {copied ? "Đã sao chép link ✓" : "Sao chép link mời"}
        </button>
      </Card>

      <div className="flex items-center justify-between px-1 mb-2">
        <h2 className="font-display font-semibold text-ink text-lg">
          Người chơi <span className="text-ink-faint font-sans text-sm">({players.length})</span>
        </h2>
        {!canStart ? <span className="text-xs text-ink-faint">cần ≥ {MIN_PLAYERS_TO_START}</span> : null}
      </div>
      <Card className="!p-2 mb-4">
        <ul className="flex flex-col">
          {players.map((p) => {
            const me = p.id === identity.playerId;
            return (
              <li key={p.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl">
                <span
                  className="w-8 h-8 rounded-full grid place-items-center text-sm font-semibold shrink-0"
                  style={{ background: "var(--accent-soft)", color: "var(--accent-ink)" }}
                >
                  {p.name.slice(0, 1).toUpperCase()}
                </span>
                <span className="flex-1 text-ink font-medium truncate">
                  {p.name}
                  {me ? <span className="text-ink-faint font-normal"> (bạn)</span> : null}
                </span>
                {p.role === "host" ? (
                  <span className="text-xs font-mono text-accent-ink bg-accent-soft px-2 py-0.5 rounded-md">
                    chủ phòng
                  </span>
                ) : isHost ? (
                  <button
                    onClick={() => handleRemove(p.id)}
                    className="text-xs text-ink-faint hover:text-accent-ink cursor-pointer"
                    aria-label={`Xoá ${p.name}`}
                  >
                    xoá
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card className="mb-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-ink-soft">Ngôn ngữ</span>
          <span className="text-sm text-ink font-medium">
            {LANGUAGE_FLAGS[room.settings.language]} {SUPPORTED_LANGUAGES[room.settings.language]}
          </span>
        </div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-ink-soft">Model AI</span>
          <span className="text-sm text-ink font-medium">
            {SUPPORTED_LLM_MODELS[room.settings.llm_model] ?? room.settings.llm_model}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-ink-soft">Điểm thắng</span>
          {isHost ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleMaxScore(-10)}
                className="w-7 h-7 rounded-lg bg-surface-2 border border-border-strong text-ink cursor-pointer"
              >
                −
              </button>
              <span className="text-sm text-ink font-semibold font-mono w-10 text-center tabular-nums">
                {room.settings.max_score}
              </span>
              <button
                onClick={() => handleMaxScore(10)}
                className="w-7 h-7 rounded-lg bg-surface-2 border border-border-strong text-ink cursor-pointer"
              >
                +
              </button>
            </div>
          ) : (
            <span className="text-sm text-ink font-medium font-mono">{room.settings.max_score}</span>
          )}
        </div>
      </Card>

      {error ? <div className="mb-4"><Notice>{error}</Notice></div> : null}

      {isHost ? (
        <Button size="lg" full onClick={handleStart} disabled={!canStart || busy}>
          {busy ? "Đang bắt đầu…" : canStart ? "Bắt đầu ván →" : `Chờ đủ ${MIN_PLAYERS_TO_START} người`}
        </Button>
      ) : (
        <div className="text-center text-sm text-ink-soft py-2">Chờ chủ phòng bắt đầu…</div>
      )}

      <button
        onClick={handleLeave}
        className="mt-4 text-center text-xs text-ink-faint hover:text-accent-ink cursor-pointer"
      >
        {isHost ? "Đóng phòng & rời đi" : "Rời phòng"}
      </button>
    </PageShell>
  );
}
