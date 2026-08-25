"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createRoom } from "@/app/actions";
import { rememberIdentity } from "@/lib/identity";
import {
  SUPPORTED_LANGUAGES,
  SUPPORTED_LLM_MODELS,
  LANGUAGE_FLAGS,
  type Language,
} from "@/lib/types";
import {
  PageShell,
  Brand,
  Card,
  Button,
  Field,
  TextInput,
  Select,
  Notice,
} from "@/components/ui";

export default function HostPage() {
  const router = useRouter();
  const [hostName, setHostName] = useState("");
  const [roomName, setRoomName] = useState("");
  const [language, setLanguage] = useState<Language>("vn");
  const [model, setModel] = useState("gemini-2.5-flash");
  const [maxScore, setMaxScore] = useState(100);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCreate() {
    setError(null);
    setBusy(true);
    const res = await createRoom({
      hostName,
      roomName,
      settings: { language, llm_model: model, max_score: maxScore },
    });
    if (!res.ok) {
      setError(res.error);
      setBusy(false);
      return;
    }
    rememberIdentity(res.data.code, res.data.playerId, hostName.trim());
    router.push(`/room/${res.data.code}`);
  }

  return (
    <PageShell>
      <div className="mb-6">
        <Brand small />
      </div>
      <h1 className="font-display font-semibold text-ink text-2xl mb-1">Tạo phòng</h1>
      <p className="text-ink-soft text-sm mb-6">
        Bạn sẽ là chủ phòng — chọn ngôn ngữ, model và điểm mục tiêu.
      </p>

      <Card>
        <div className="flex flex-col gap-4">
          <Field label="Tên của bạn">
            <TextInput
              value={hostName}
              onChange={(e) => setHostName(e.target.value)}
              placeholder="VD: Thảo"
              maxLength={40}
              autoFocus
            />
          </Field>
          <Field label="Tên phòng">
            <TextInput
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
              placeholder="VD: Tối thứ 6"
              maxLength={40}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Ngôn ngữ">
              <Select value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
                {(Object.keys(SUPPORTED_LANGUAGES) as Language[]).map((code) => (
                  <option key={code} value={code}>
                    {LANGUAGE_FLAGS[code]} {SUPPORTED_LANGUAGES[code]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Điểm thắng">
              <TextInput
                type="number"
                inputMode="numeric"
                min={10}
                max={1000}
                value={maxScore}
                onChange={(e) => setMaxScore(Number(e.target.value))}
              />
            </Field>
          </div>

          <Field label="Model AI" hint="Sinh câu hỏi. Có thể đổi sau.">
            <Select value={model} onChange={(e) => setModel(e.target.value)}>
              {Object.entries(SUPPORTED_LLM_MODELS).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>

          {error ? <Notice>{error}</Notice> : null}

          <Button size="lg" full onClick={handleCreate} disabled={busy}>
            {busy ? "Đang tạo…" : "Tạo phòng →"}
          </Button>
        </div>
      </Card>
    </PageShell>
  );
}
