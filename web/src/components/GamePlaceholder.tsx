"use client";

import { endGame } from "@/app/actions";
import type { Player, Room } from "@/lib/types";
import { PageShell, Brand, Card, Button, LiveBadge } from "@/components/ui";

// Temporary in-game screen for Phase 1: confirms the started state syncs in
// realtime to everyone. The full 7-phase game UI arrives in Phase 2.
export default function GamePlaceholder({
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
  const isHost = room.host_id === identity.playerId;
  const storytellerId = room.storyteller_order[room.turn_index];
  const storyteller = players.find((p) => p.id === storytellerId);

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-5">
        <Brand small />
        <LiveBadge live={live} />
      </div>

      <Card className="text-center mb-4">
        <p className="text-xs uppercase tracking-widest text-ink-faint font-mono mb-2">
          Ván đã bắt đầu
        </p>
        <div className="text-3xl mb-2">🎬</div>
        <p className="font-display font-semibold text-ink text-xl mb-1">
          Vòng {room.round}
        </p>
        <p className="text-ink-soft text-sm">
          Người kể chuyện: <strong className="text-ink font-semibold">{storyteller?.name ?? "…"}</strong>
        </p>
        <p className="text-ink-faint text-xs font-mono mt-2">phase: {room.phase}</p>
      </Card>

      <Card className="mb-4">
        <p className="text-sm text-ink-soft leading-relaxed">
          🚧 Màn chơi đầy đủ (chọn chủ đề → câu hỏi AI → trả lời → đoán → tính điểm)
          sẽ được dựng ở <strong className="text-ink font-semibold">Phase 2–4</strong>.
          Màn này để xác nhận trạng thái “đã bắt đầu” đồng bộ realtime tới mọi người.
        </p>
      </Card>

      <Card className="!p-2 mb-4">
        <ul className="flex flex-col">
          {room.storyteller_order.map((pid, i) => {
            const p = players.find((pl) => pl.id === pid);
            if (!p) return null;
            return (
              <li key={pid} className="flex items-center gap-3 px-3 py-2 rounded-xl">
                <span className="text-xs font-mono text-ink-faint w-5 tabular-nums">{i + 1}</span>
                <span className="flex-1 text-ink font-medium truncate">{p.name}</span>
                <span className="text-sm font-mono text-ink-soft tabular-nums">{p.score}</span>
                {pid === storytellerId ? <span className="text-sm">🎙️</span> : null}
              </li>
            );
          })}
        </ul>
      </Card>

      {isHost ? (
        <Button
          variant="danger"
          full
          onClick={() => endGame({ code: room.code, hostId: identity.playerId })}
        >
          Kết thúc & về lobby
        </Button>
      ) : null}
    </PageShell>
  );
}
