"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useGame } from "@/lib/useGame";
import { getIdentity, rememberIdentity } from "@/lib/identity";
import { PageShell, Brand, Card } from "@/components/ui";
import Lobby from "@/components/Lobby";
import Game from "@/components/Game";

export default function RoomView({ code }: { code: string }) {
  const { room, players, round, submissions, guesses, live, loading } = useGame(code);
  const [identity, setIdentity] = useState<{ playerId: string; name: string } | null>(null);
  const [identityReady, setIdentityReady] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIdentity(getIdentity(code));
    setIdentityReady(true);
  }, [code]);

  if (loading || !identityReady) {
    return (
      <PageShell>
        <div className="flex-1 grid place-items-center text-ink-faint text-sm">Đang tải phòng…</div>
      </PageShell>
    );
  }

  if (!room) {
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

  const inRoom = !!identity && players.some((p) => p.id === identity.playerId);
  if (!inRoom) {
    // Mid-game: let a returning player reclaim their existing slot (keeps score).
    if (room.started && players.length > 0) {
      return (
        <PageShell>
          <div className="mb-6"><Brand small /></div>
          <Card>
            <p className="text-ink font-semibold mb-1">Vào lại phòng “{room.name}”</p>
            <p className="text-ink-soft text-sm mb-4">Ván đang diễn ra. Bạn là ai?</p>
            <div className="flex flex-col gap-2">
              {players.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    rememberIdentity(code, p.id, p.name);
                    setIdentity({ playerId: p.id, name: p.name });
                  }}
                  className="text-left bg-surface-2 border border-border-strong rounded-xl px-4 py-3 text-ink font-medium hover:border-accent cursor-pointer"
                >
                  {p.name}
                </button>
              ))}
            </div>
          </Card>
        </PageShell>
      );
    }
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

  if (room.started) {
    return (
      <Game
        room={room}
        players={players}
        round={round}
        submissions={submissions}
        guesses={guesses}
        identity={identity!}
        live={live}
      />
    );
  }

  return <Lobby room={room} players={players} identity={identity!} live={live} />;
}
