"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRoom } from "@/lib/useRoom";
import { getIdentity, forgetIdentity } from "@/lib/identity";
import { startGame, updateSettings, removePlayer, leaveRoom } from "@/app/actions";
import {
  MIN_PLAYERS_TO_START,
  SUPPORTED_LANGUAGES,
  LANGUAGE_FLAGS,
  SUPPORTED_LLM_MODELS,
} from "@/lib/types";
import {
  PageShell,
  Brand,
  Card,
  Button,
  Notice,
  LiveBadge,
} from "@/components/ui";
import GamePlaceholder from "@/components/GamePlaceholder";

export default function Lobby({ code }: { code: string }) {
  const { room, players, status, live } = useRoom(code);
  const [identity, setIdentity] = useState<{ playerId: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setIdentity(getIdentity(code));
  }, [code]);

  const isHost = !!room && !!identity && room.host_id === identity.playerId;
  const inRoom = !!identity && players.some((p) => p.id === identity.playerId);
  const canStart = players.length >= MIN_PLAYERS_TO_START;

  const shareUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/join?code=${code}`;
  }, [code]);

  async function handleStart() {
    if (!identity) return;
    setError(null);
    setBusy(true);
    const res = await startGame({ code, hostId: identity.playerId });
    if (!res.ok) setError(res.error);
    setBusy(false);
  }

  async function handleMaxScore(delta: number) {
    if (!identity || !room) return;
    const next = Math.min(1000, Math.max(10, room.settings.max_score + delta));
    await updateSettings({ code, hostId: identity.playerId, settings: { max_score: next } });
  }

  async function handleRemove(playerId: string) {
    if (!identity) return;
    await removePlayer({ code, hostId: identity.playerId, playerId });
  }

  async function handleLeave() {
    if (!identity) return;
    await leaveRoom({ code, playerId: identity.playerId });
    forgetIdentity(code);
    window.location.href = "/";
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

  // ---- Loading / not found / not a member states -------------------
  if (status === "loading") {
    return (
      <PageShell>
        <div className="flex-1 grid place-items-center text-ink-faint text-sm">Đang tải phòng…</div>
      </PageShell>
    );
  }
  if (status === "not_found" || !room) {
    return (
      <PageShell>
        <div className="mb-6"><Brand small /></div>
        <Card>
          <p className="text-ink font-semibold mb-1">Không tìm thấy phòng “{code}”.</p>
          <p className="text-ink-soft text-sm mb-4">Có thể phòng đã đóng hoặc mã sai.</p>
          <Link href="/" className="text-accent-ink font-semibold text-sm">← Về trang chủ</Link>
        </Card>
      </PageShell>
    );
  }
  if (!inRoom) {
    return (
      <PageShell>
        <div className="mb-6"><Brand small /></div>
        <Card>
          <p className="text-ink font-semibold mb-1">Bạn chưa ở trong phòng này.</p>
          <p className="text-ink-soft text-sm mb-4">Vào phòng “{room.name}” bằng mã {code}.</p>
          <Link
            href={`/join?code=${code}`}
            className="inline-block bg-accent text-white font-semibold rounded-xl px-4 py-2.5 text-sm no-underline"
          >
            Vào phòng →
          </Link>
        </Card>
      </PageShell>
    );
  }

  // ---- Game started → hand off to the game screen (Phase 2) ---------
  if (room.started) {
    return <GamePlaceholder room={room} players={players} identity={identity!} live={live} />;
  }

  // ---- Lobby -------------------------------------------------------
  return (
    <PageShell>
      <div className="flex items-center justify-between mb-5">
        <Brand small />
        <LiveBadge live={live} />
      </div>

      {/* Room code card */}
      <Card className="text-center mb-4">
        <p className="text-xs uppercase tracking-widest text-ink-faint font-mono mb-2">
          {room.name}
        </p>
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

      {/* Players */}
      <div className="flex items-center justify-between px-1 mb-2">
        <h2 className="font-display font-semibold text-ink text-lg">
          Người chơi <span className="text-ink-faint font-sans text-sm">({players.length})</span>
        </h2>
        {!canStart ? (
          <span className="text-xs text-ink-faint">cần ≥ {MIN_PLAYERS_TO_START}</span>
        ) : null}
      </div>
      <Card className="!p-2 mb-4">
        <ul className="flex flex-col">
          {players.map((p) => {
            const me = p.id === identity!.playerId;
            return (
              <li
                key={p.id}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
              >
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

      {/* Settings */}
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

      {/* Actions */}
      {isHost ? (
        <Button size="lg" full onClick={handleStart} disabled={!canStart || busy}>
          {busy ? "Đang bắt đầu…" : canStart ? "Bắt đầu ván →" : `Chờ đủ ${MIN_PLAYERS_TO_START} người`}
        </Button>
      ) : (
        <div className="text-center text-sm text-ink-soft py-2">
          Chờ chủ phòng bắt đầu…
        </div>
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
