"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { joinRoom } from "@/app/actions";
import { rememberIdentity } from "@/lib/identity";
import { PageShell, Brand, Card, Button, Field, TextInput, Notice } from "@/components/ui";

export default function JoinPage() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Prefill code from a shared link like /join?code=ABCD
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const c = params.get("code");
    if (c) setCode(c.toUpperCase());
  }, []);

  async function handleJoin() {
    setError(null);
    setBusy(true);
    const res = await joinRoom({ code, name });
    if (!res.ok) {
      setError(res.error);
      setBusy(false);
      return;
    }
    rememberIdentity(res.data.code, res.data.playerId, name.trim());
    router.push(`/room/${res.data.code}`);
  }

  return (
    <PageShell>
      <div className="mb-6">
        <Brand small />
      </div>
      <h1 className="font-display font-semibold text-ink text-2xl mb-1">Vào phòng</h1>
      <p className="text-ink-soft text-sm mb-6">Nhập mã phòng mà chủ phòng chia sẻ.</p>

      <Card>
        <div className="flex flex-col gap-4">
          <Field label="Mã phòng">
            <TextInput
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="VD: K7QP"
              maxLength={6}
              autoCapitalize="characters"
              className="font-mono tracking-[0.3em] text-lg"
            />
          </Field>
          <Field label="Tên của bạn">
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Minh"
              maxLength={40}
            />
          </Field>

          {error ? <Notice>{error}</Notice> : null}

          <Button size="lg" full onClick={handleJoin} disabled={busy}>
            {busy ? "Đang vào…" : "Vào phòng →"}
          </Button>
        </div>
      </Card>
    </PageShell>
  );
}
