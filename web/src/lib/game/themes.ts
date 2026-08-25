// Ported from the old Python models.py (DEFAULT_THEMES).
export const DEFAULT_THEMES: string[] = [
  "Yourself 🌱",
  "Childhood 👶",
  "Family 🏡",
  "Goals ✨",
  "Work 💼",
  "Love 💖",
  "Friends 🤝",
  "Hobbies 🎨",
  "Travel ✈️",
  "Random 🎲",
];

export const LEVELS = [
  { key: "shallow", label: "Nhẹ nhàng", emoji: "🫧", hint: "Vui, nhanh, dễ đoán · điểm ×1" },
  { key: "deep", label: "Sâu sắc", emoji: "🌊", hint: "Suy ngẫm, cá nhân hơn · điểm ×2" },
] as const;
