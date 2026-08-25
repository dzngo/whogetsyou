// Verify the real LLM path: Gemini structured output + Vietnamese translation.
// Run: node scripts/test-llm.mjs
import fs from "node:fs";
import OpenAI from "openai";

for (const l of fs.readFileSync(".env.local", "utf8").split("\n")) {
  const m = l.match(/^\s*([A-Z_]+)\s*=\s*(.*)$/);
  if (m) process.env[m[1]] = m[2].trim();
}

const model = "gemini-2.5-flash";
const client = new OpenAI({
  apiKey: process.env.GOOGLE_API_KEY,
  baseURL: "https://generativelanguage.googleapis.com/v1beta/openai/",
});

let bad = 0;

// 1. Structured candidate set --------------------------------------------
console.log("→ Sinh câu hỏi (Love / deep)…");
const candSchema = {
  type: "object",
  properties: {
    candidates: {
      type: "array",
      items: {
        type: "object",
        properties: { rank: { type: "integer" }, angle_key: { type: "string" }, question: { type: "string" } },
        required: ["rank", "angle_key", "question"],
        additionalProperties: false,
      },
    },
  },
  required: ["candidates"],
  additionalProperties: false,
};
try {
  const r = await client.chat.completions.create({
    model,
    messages: [
      { role: "system", content: "You write warm, safe party-game questions. Return JSON matching the schema." },
      { role: "user", content: "Generate a ranked Candidate Set for theme 'Love 💖', depth Deep. Angles:\n- trust: Ask about how trust is built or broken in small moments.\n- boundaries: Ask about a boundary that helps the player feel safe.\nOne English question per angle, exactly one question mark each. JSON field 'candidates' with rank, angle_key, question." },
    ],
    response_format: { type: "json_schema", json_schema: { name: "cand", schema: candSchema, strict: true } },
  });
  const parsed = JSON.parse(r.choices[0].message.content);
  const ok = Array.isArray(parsed.candidates) && parsed.candidates.length >= 1 && parsed.candidates.every((c) => c.question.includes("?"));
  console.log(ok ? "  ✅ structured candidates ok" : "  ❌ bad shape");
  if (!ok) bad++;
  parsed.candidates.forEach((c) => console.log(`     [${c.rank}] ${c.angle_key}: ${c.question}`));

  // 2. Translate the top candidate to Vietnamese -------------------------
  console.log("→ Dịch sang tiếng Việt…");
  const top = parsed.candidates[0].question;
  const t = await client.chat.completions.create({
    model,
    messages: [
      { role: "system", content: "You are a concise translator. Return JSON with field 'text'." },
      { role: "user", content: `Translate from English to Tiếng Việt, preserve it as a question:\n${top}\nReturn JSON with field 'text'.` },
    ],
    response_format: { type: "json_schema", json_schema: { name: "tr", schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: false }, strict: true } },
  });
  const vi = JSON.parse(t.choices[0].message.content).text;
  const okVi = typeof vi === "string" && vi.length > 0;
  console.log(okVi ? "  ✅ translation ok" : "  ❌ translation failed");
  if (!okVi) bad++;
  console.log(`     EN: ${top}\n     VI: ${vi}`);
} catch (e) {
  bad++;
  console.log("  ❌ LLM error:", e?.message ?? e);
}

console.log(`\n${bad === 0 ? "🎉 LLM PATH OK" : "⚠️ FAILURES: " + bad}`);
process.exit(bad === 0 ? 0 : 1);
