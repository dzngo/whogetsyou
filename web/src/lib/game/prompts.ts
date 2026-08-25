// Prompt templates — ported from the old Python llm_prompts.py.
import { SUPPORTED_LANGUAGES, type Language } from "@/lib/types";
import { THEME_DESCRIPTIONS, type QuestionAngle } from "@/lib/game/angles";

const GAME_RULES_SUMMARY = `
"Who Gets You?" is a multiplayer party game about how well friends understand one another.

- The Guess Target is the Storyteller Answer.
- In Shallow rounds, the Storyteller Answer is what the Storyteller would plausibly prefer, choose, notice, or do in everyday life.
- In Deep rounds, the Storyteller Answer is something personally true about the Storyteller.
- Themes are life areas (e.g., childhood, travel, work), plus Random for surprise.


Tone rules for you (the AI):
- Shallow questions should be realistic, light, quick, and low-stakes. Prefer everyday preferences, habits, routines, tastes, communication styles, small joys, simple choices, and plausible "what if / what would you do" situations.
- Deep questions should be reflective, personal, emotionally safe, and specific.
- Keep generated content inclusive and non-triggering. Shallow can be playful, but avoid cruelty, forced embarrassment, private exposure, discriminatory framing, or sexual pressure.
- Suggested answers must fit the selected level: short and casual for Shallow; first-person, personal, and emotionally safe for Deep.
`.trim();

const LEVEL_DESCRIPTIONS: Record<string, string> = {
  shallow: "Realistic, low-pressure, and quick. Uses everyday preferences, habits, routines, tastes, simple choices, or plausible situations that do not require serious thinking.",
  deep: "Introspective and emotionally aware. Invites vulnerability, formative memories, or personal growth moments while staying respectful.",
};

export const SYSTEM_PROMPT = `You are the narrative director for the party game "Who Gets You?". Use the rules below to keep questions and answers safe, inclusive, and emotionally intelligent.
${GAME_RULES_SUMMARY}
Always return JSON that matches the provided schema for the current task.`;

export const TRANSLATION_SYSTEM_PROMPT =
  "You are a concise translator. Translate only according to the user's instructions. " +
  "Preserve meaning, intent, and format. Do not add new ideas, examples, explanations, labels, markdown, or extra questions. " +
  "Always return JSON that matches the provided schema for the current task.";

function languageName(code: string): string {
  return SUPPORTED_LANGUAGES[(code || "").toLowerCase() as Language] ?? code ?? "English";
}

function renderPreviousQuestions(previous: string[]): string {
  const cleaned = previous.map((q) => q.trim()).filter(Boolean);
  if (cleaned.length === 0) return "None provided. Feel free to explore any original angle.";
  return `Previously used questions:\n${cleaned.map((q) => `- ${q}`).join("\n")}\n`;
}

function renderSelectedAngles(angles: QuestionAngle[]): string {
  return angles.map((a) => `- ${a.key}: ${a.guidance}`).join("\n");
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function buildCandidateSetPrompt(opts: {
  theme: string;
  level: string;
  selectedAngles: QuestionAngle[];
  previousQuestions: string[];
}): string {
  const level = (opts.level || "").toLowerCase();
  const levelRequirements =
    level === "shallow"
      ? "- Make each question realistic, light, quick, and low-pressure.\n" +
        "- Ask for one preference, habit, routine, taste, style, choice, small joy, or plausible reaction only.\n" +
        "- Direct everyday 'what do you like', 'which do you prefer', and realistic 'what would you do if' shapes are welcome.\n" +
        "- Keep situational questions plausible: missed plans, free time, places, errands, meals, weather, messages, breaks, or travel delays.\n" +
        "- Do not make premises magical, surreal, childish, object-personified, cartoon-like, cruel, embarrassing, or sexually pressured.\n" +
        "- Avoid idioms and compressed phrasing that translate badly, such as 'go-to', 'pick-me-up', 'on a whim', and invented compounds like 'snack-free distraction'.\n" +
        "- Prefer plain English that will translate naturally into another language.\n" +
        "- Do not ask for a confession, personal growth story, emotional lesson, or deep memory.\n"
      : "- Invite a personally true answer: a value, memory, relationship pattern, belief, regret, hope, or self-understanding.\n" +
        "- Keep each question emotionally safe and reflective without becoming heavy, clinical, or therapy-like.\n" +
        "- Ask for one specific angle, not a broad life audit.\n" +
        "- Prefer concrete, natural wording that will translate well.\n";

  return (
    `Generate a ranked Candidate Set for the theme '${opts.theme}'.\n` +
    `Depth: ${titleCase(opts.level)} — ${LEVEL_DESCRIPTIONS[level] ?? "Keep it warm and sincere"}\n` +
    "Use the exact Question Angles below. Generate exactly one question for each angle key.\n" +
    "Do not invent, rename, merge, skip, or repeat angle keys.\n" +
    `Question Angles:\n${renderSelectedAngles(opts.selectedAngles)}\n\n` +
    `${renderPreviousQuestions(opts.previousQuestions)}\n` +
    "Treat previous questions as off-limits source material. Avoid their structure, opening patterns, key phrases, and broad situations.\n" +
    "Rank the candidates from best to weakest for a party game: realistic, natural, easy to answer, theme-connected, diverse, and translation-friendly.\n" +
    "Requirements for every candidate:\n" +
    "- Write the question entirely in English.\n" +
    "- Exactly one sentence and exactly one question mark.\n" +
    "- Prefer fewer than 18 words for Shallow; prefer fewer than 24 words for Deep.\n" +
    "- Make it easy to answer with a short phrase or sentence.\n" +
    "- Do not ask why, ask for examples, or add a reflective tail unless the level is Deep and it is essential.\n" +
    "- Do not combine multiple tasks with 'and'.\n" +
    "- Avoid yes/no questions, harmful framing, stale wording, and long option lists.\n" +
    levelRequirements +
    "Output JSON with a single field 'candidates'. Each item must contain 'rank', 'angle_key', and 'question'."
  );
}

export function buildTranslationPrompt(text: string, source: string, target: string): string {
  return (
    `Translate the following text from ${languageName(source)} to ${languageName(target)}.\n` +
    "Rules:\n" +
    "- Preserve the original meaning, intent, tone, and format.\n" +
    "- Make it natural and playable in the target language.\n" +
    "- Preserve whether the text is a question or an answer.\n" +
    "- Do not add examples, explanations, labels, markdown, or extra questions.\n" +
    "- Return only the translated text in JSON.\n" +
    `Text:\n${text}\n` +
    "Return JSON with a single field 'text'."
  );
}

export function buildAnswerPrompt(opts: {
  question: string;
  storytellerName: string;
  theme?: string;
  level?: string;
}): string {
  const themeOptions = THEME_DESCRIPTIONS[opts.theme ?? ""] ?? [];
  const themeNote = themeOptions.length ? themeOptions[Math.floor(Math.random() * themeOptions.length)] : "";
  const themeLine = themeNote ? `Theme guidance: ${themeNote}\n` : "";
  const level = (opts.level || "").toLowerCase();
  const styleRules =
    level === "shallow"
      ? "Make the answer short, casual, realistic, and immediately playable.\n" +
        "It should sound like a natural everyday preference, habit, or choice.\n" +
        "It does not need to reveal a serious truth or personal story.\n"
      : "Keep it concise, first-person, specific, natural, and emotionally safe.\n" +
        "It should sound personally true without becoming too heavy.\n";
  return (
    `The player is ${opts.storytellerName}. Help them respond to:\n` +
    `Question: ${opts.question}\n` +
    themeLine +
    "Return the answer entirely in English.\n" +
    styleRules +
    "Do not include labels, explanations, or markdown.\n" +
    "Return JSON with only 'answer'."
  );
}
