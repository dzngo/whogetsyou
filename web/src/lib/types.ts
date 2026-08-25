// Shared domain types — mirror the Supabase tables.

export type Language = "en" | "vn" | "fr" | "es" | "de";
export type Level = "shallow" | "deep";
export type PlayerRole = "host" | "joiner";

export type Phase =
  | "theme_selection"
  | "level_selection"
  | "question_generation"
  | "answer_entry"
  | "guessing"
  | "reveal"
  | "results";

export interface RoomSettings {
  max_score: number;
  language: Language;
  llm_model: string;
}

export interface QuestionState {
  question: string;
  question_en: string;
  angle_key: string;
}

export interface Room {
  id: string;
  code: string;
  name: string;
  host_id: string;
  is_private: boolean;
  started: boolean;
  settings: RoomSettings;
  phase: Phase | null;
  round: number;
  turn_index: number;
  storyteller_order: string[];
  selected_theme: string | null;
  selected_level: Level | null;
  question: QuestionState | null;
  winners: string[];
  end_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Player {
  id: string;
  room_id: string;
  name: string;
  role: PlayerRole;
  connected: boolean;
  score: number;
  joined_at: string;
}

export const SUPPORTED_LANGUAGES: Record<Language, string> = {
  en: "English",
  vn: "Tiếng Việt",
  fr: "Français",
  es: "Español",
  de: "Deutsch",
};

export const LANGUAGE_FLAGS: Record<Language, string> = {
  en: "🇬🇧",
  vn: "🇻🇳",
  fr: "🇫🇷",
  es: "🇪🇸",
  de: "🇩🇪",
};

// A trimmed model list — expand later to match the old Python catalog.
export const SUPPORTED_LLM_MODELS: Record<string, string> = {
  "gemini-3.6-flash": "Gemini 3.6 Flash",
  "gemini-3.7-flash": "Gemini 3.7 Flash",
  "gemini-3.5-flash": "Gemini 3.5 Flash",
  "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite (nhanh)",
};

export const DEFAULT_LLM_MODEL = "gemini-3.6-flash";

export interface AnswerOption {
  submission_id: string;
  owner_id: string;
  is_storyteller: boolean;
  label: string;
  text: string;
}

export interface RoundSummary {
  deltas: Record<string, number>;
  correct: string[];
  decoy: Record<string, number>;
  guesses: Record<string, string>;
}

export interface Round {
  id: string;
  room_id: string;
  round_no: number;
  storyteller_id: string | null;
  theme: string | null;
  level: Level | null;
  question: QuestionState | null;
  options: AnswerOption[] | null;
  summary: RoundSummary | null;
}

export interface Submission {
  id: string;
  round_id: string;
  player_id: string;
  text: string;
  is_storyteller: boolean;
}

export interface Guess {
  id: string;
  round_id: string;
  player_id: string;
  submission_id: string;
}

export const MIN_PLAYERS_TO_START = 3;
