// Question angle catalog — ported 1:1 from the old Python models.py.
// These drive question variety and quality; keep them faithful to the original.

export interface QuestionAngle {
  key: string;
  guidance: string;
  weight?: number;
}

type ByLevel = { shallow: QuestionAngle[]; deep: QuestionAngle[] };

export const THEME_DESCRIPTIONS: Record<string, string[]> = {
  "Yourself 🌱": [
    "Self-awareness and identity shifts",
    "Snapshots from your personal daily life",
    "Facts about you and your interests",
    "How you understand yourself",
    "Self-talk and inner dialogue",
    "Micro-habits that reveal who you are",
    "How your thoughts, emotions, and behaviors align with your values",
    "How other people perceive you versus how you see yourself",
    "Emotional triggers and how you regulate them",
    "Strengths, blind spots, and patterns you keep noticing",
    "Decisions that changed your sense of purpose or direction",
  ],
  "Childhood 👶": [
    "Memories and stories from your early years",
    "Lessons from your upbringing",
    "Family dynamics when you were growing up",
    "Formative childhood friendships",
    "Caretakers and their impact on you",
    "Big feelings from kid years",
    "Moments when you felt especially safe, protected, or understood",
    "Positive childhood experiences that still shape your relationships",
    "Community traditions and places that made you feel you belonged",
    "Play, imagination, and the worlds you created as a child",
    "Early experiences that changed how you handle fear, trust, or confidence",
  ],
  "Family 🏡": [
    "Experiences with family members",
    "Warm and messy family moments",
    "Traditions and rituals at home",
    "Conflict and repair in family life",
    "Generational expectations and boundaries",
    "Quirks that define your home life",
    "Everyday routines that made home feel stable or chaotic",
    "Roles you naturally take on in your family",
    "Ways your family shows care, loyalty, or protection",
    "Conversations, tensions, or values that repeat across generations",
    "How you balance closeness with independence in family relationships",
  ],
  "Goals ✨": [
    "Dreams you are actively pursuing",
    "Milestones you want to reach",
    "Career leaps you are aiming for",
    "Health goals and personal growth quests",
    "Creative ambitions",
    "Bucket-list experiments",
    "Goals that feel deeply connected to your values",
    "How you stay motivated when progress is slow",
    "Habits and systems that move you forward",
    "Setbacks, pivots, and how you redefine success",
    "How you measure progress and hold yourself accountable",
  ],
  "Work 💼": [
    "How you show up professionally",
    "Coworker and manager relationships",
    "Team dynamics and collaboration",
    "Challenges and pressure at work",
    "Leadership style and growth",
    "Promotion or burnout recovery stories",
    "Psychological safety and what helps you speak up",
    "How you handle competing priorities and role conflict",
    "What energizes you versus what drains you at work",
    "How you build trust, clarity, and momentum on a team",
    "How leadership pressure changes your day-to-day emotions",
  ],
  "Love 💖": [
    "Romantic relationships and intimacy",
    "How you show love to a partner",
    "Dating history and patterns",
    "Love languages and communication styles",
    "Conflict repair in relationships",
    "What you want next in love",
    "How trust is built or broken in small everyday moments",
    "Boundaries that help you feel safe and close",
    "Emotional, intellectual, physical, or experiential intimacy",
    "How you reconnect after hurt, distance, or misunderstanding",
    "Needs or desires that are hard for you to say out loud",
  ],
  "Friends 🤝": [
    "Friendship stories old and new",
    "Chosen-family moments",
    "How you support and are supported",
    "Inside jokes and shared rituals",
    "Boundaries and loyalty in friendships",
    "Long-distance friendship dynamics",
    "The friendships that make you feel most like yourself",
    "Quality versus quantity in your social life",
    "Meaningful conversations that made you feel more connected",
    "How you maintain friendship during busy or changing life stages",
    "When reaching out, being reached for, or being remembered mattered",
  ],
  "Hobbies 🎨": [
    "Passions and creative outlets",
    "How you unwind and recharge",
    "Learning curves in your craft",
    "Communities around your hobbies",
    "Resources you lean on to improve",
    "Dream collaborations",
    "How hobbies shape your identity outside work or responsibility",
    "Play, curiosity, and experimentation for their own sake",
    "The discipline, patience, or confidence a hobby builds in you",
    "How leisure affects your mood, resilience, or mental clarity",
    "Social connection, belonging, or mentorship through a hobby community",
  ],
  "Travel ✈️": [
    "Journeys and discoveries",
    "Culture shocks and perspective shifts",
    "Planning quirks and travel style",
    "Travel buddies and group dynamics",
    "Memorable moments from trips",
    "Lessons that stayed with you",
    "Travel experiences that challenged your assumptions",
    "Curiosity, openness, and how you engage with difference",
    "Conversations with locals that changed how you saw a place",
    "Moments when travel made you more aware of inequality or privilege",
    "The difference between just visiting and truly paying attention",
  ],
  "Random 🎲": ["Randomness"],
};

export const GENERIC_QUESTION_ANGLES: ByLevel = {
  shallow: [
    { key: "everyday_preference", guidance: "Ask about one realistic everyday preference connected to the selected theme." },
    { key: "small_routine", guidance: "Ask about one small routine or habit connected to the selected theme." },
    { key: "simple_choice", guidance: "Ask about one light choice the player would plausibly make in real life." },
    { key: "communication_style", guidance: "Ask about one simple communication or social style connected to the selected theme." },
    { key: "plausible_situation", guidance: "Ask what the player would do in one plausible everyday situation connected to the selected theme." },
    { key: "small_joy", guidance: "Ask about one small thing the player enjoys, notices, or looks forward to." },
  ],
  deep: [
    { key: "values", guidance: "Ask about one value or principle connected to the selected theme." },
    { key: "memory", guidance: "Ask about one specific memory connected to the selected theme." },
    { key: "relationship_pattern", guidance: "Ask about one relationship pattern or way of showing up connected to the selected theme." },
    { key: "growth", guidance: "Ask about one personal growth moment connected to the selected theme." },
    { key: "belief", guidance: "Ask about one belief, assumption, or perspective connected to the selected theme." },
    { key: "hope", guidance: "Ask about one hope, fear, or future-facing reflection connected to the selected theme." },
  ],
};

export const QUESTION_ANGLES: Record<string, ByLevel> = {
  "Yourself 🌱": {
    shallow: [
      { key: "free_time", guidance: "Ask what the player likes doing during free time or a relaxed day." },
      { key: "music_media", guidance: "Ask about music, movies, shows, books, or online content the player usually enjoys." },
      { key: "food_drink", guidance: "Ask about one everyday food or drink preference.", weight: 0.6 },
      { key: "small_joy", guidance: "Ask about one small thing that makes the player's day better." },
      { key: "season_weather", guidance: "Ask about the player's favorite season, weather, or outdoor feeling." },
      { key: "planning_style", guidance: "Ask whether the player prefers planning ahead or being spontaneous." },
      { key: "communication_style", guidance: "Ask about texting, calling, replying, or talking in person." },
      { key: "tidiness_style", guidance: "Ask about being tidy, flexible, organized, or naturally casual." },
      { key: "hobbies", guidance: "Ask about a hobby the player has or wants to try." },
      { key: "small_strength", guidance: "Ask about one simple thing the player thinks they are good at." },
      { key: "favorite_place", guidance: "Ask about a place where the player likes spending time." },
      { key: "first_impression", guidance: "Ask what others may notice first about the player." },
    ],
    deep: [
      { key: "identity", guidance: "Ask about how the player understands who they are becoming." },
      { key: "self_perception", guidance: "Ask about the gap between how the player sees themself and how others see them." },
      { key: "values", guidance: "Ask about a value that quietly guides the player's choices." },
      { key: "emotional_pattern", guidance: "Ask about a recurring emotional pattern the player has noticed." },
      { key: "growth", guidance: "Ask about a personal change that shaped how the player sees themself." },
      { key: "inner_dialogue", guidance: "Ask about the player's self-talk or private inner standards." },
      { key: "blind_spot", guidance: "Ask about a blind spot or recurring pattern the player is learning from." },
      { key: "purpose", guidance: "Ask about a decision that changed the player's sense of direction." },
    ],
  },
  "Childhood 👶": {
    shallow: [
      { key: "favorite_game", guidance: "Ask about a childhood game or activity the player enjoyed." },
      { key: "school_day", guidance: "Ask about one simple school-day preference or routine." },
      { key: "childhood_snack", guidance: "Ask about one childhood snack or treat.", weight: 0.6 },
      { key: "cartoon_show", guidance: "Ask about a childhood show, book, song, or toy the player liked." },
      { key: "play_place", guidance: "Ask about a place where the player liked to play or spend time." },
      { key: "small_rule", guidance: "Ask about one harmless childhood rule, habit, or routine." },
      { key: "weekend_activity", guidance: "Ask about what the player liked doing on weekends as a child." },
      { key: "kid_preference", guidance: "Ask about one simple preference the player had as a child." },
    ],
    deep: [
      { key: "safe_memory", guidance: "Ask about a childhood moment when the player felt safe or understood." },
      { key: "upbringing_lesson", guidance: "Ask about one lesson from the player's upbringing." },
      { key: "early_friendship", guidance: "Ask about a childhood friendship that shaped the player." },
      { key: "family_dynamic", guidance: "Ask about one family dynamic from growing up." },
      { key: "belonging", guidance: "Ask about a childhood place or tradition that created belonging." },
      { key: "fear_confidence", guidance: "Ask about an early experience that shaped fear, trust, or confidence." },
      { key: "caretaker_impact", guidance: "Ask about how a caretaker influenced the player." },
      { key: "imagination", guidance: "Ask about how childhood imagination still affects the player." },
    ],
  },
  "Family 🏡": {
    shallow: [
      { key: "home_routine", guidance: "Ask about one ordinary home or family routine." },
      { key: "family_meal", guidance: "Ask about a light family meal or dinner-table preference.", weight: 0.6 },
      { key: "chores", guidance: "Ask about one chore or home task style." },
      { key: "family_role", guidance: "Ask about the player's light role in family situations." },
      { key: "weekend_home", guidance: "Ask about a family weekend or at-home preference." },
      { key: "care_gesture", guidance: "Ask about one small way family members show care." },
      { key: "shared_space", guidance: "Ask about a favorite shared space or home habit." },
      { key: "family_ritual", guidance: "Ask about a simple ritual, tradition, or repeated family moment." },
    ],
    deep: [
      { key: "family_role", guidance: "Ask about the role the player naturally takes in family life." },
      { key: "boundaries", guidance: "Ask about balancing closeness and independence in family relationships." },
      { key: "generational_values", guidance: "Ask about a value or expectation passed through the family." },
      { key: "care_language", guidance: "Ask about how the player's family tends to show care." },
      { key: "conflict_repair", guidance: "Ask about how repair happens after family conflict." },
      { key: "home_stability", guidance: "Ask about what made home feel stable or chaotic." },
      { key: "loyalty", guidance: "Ask about family loyalty, protection, or responsibility." },
      { key: "repeated_conversation", guidance: "Ask about a family conversation or tension that repeats across time." },
    ],
  },
  "Goals ✨": {
    shallow: [
      { key: "small_goal", guidance: "Ask about one small goal or achievement the player would enjoy." },
      { key: "skill_to_try", guidance: "Ask about a skill, class, or hobby the player wants to try." },
      { key: "planning_style", guidance: "Ask about how the player likes planning or tracking goals." },
      { key: "motivation_routine", guidance: "Ask about one light routine that helps the player get started." },
      { key: "bucket_activity", guidance: "Ask about one realistic activity or experience the player looks forward to." },
      { key: "progress_reward", guidance: "Ask about a small reward the player likes after making progress." },
      { key: "energy_time", guidance: "Ask what time, place, or condition helps the player work on goals." },
      { key: "low_pressure_ambition", guidance: "Ask about a low-pressure ambition that would still feel satisfying." },
    ],
    deep: [
      { key: "values", guidance: "Ask about a goal connected to the player's values." },
      { key: "motivation", guidance: "Ask about what keeps the player motivated when progress is slow." },
      { key: "setback", guidance: "Ask about a setback that changed how the player defines success." },
      { key: "accountability", guidance: "Ask about how the player holds themself accountable." },
      { key: "identity", guidance: "Ask about how a goal connects to who the player wants to become." },
      { key: "pivot", guidance: "Ask about a time the player changed direction on an important goal." },
      { key: "fear", guidance: "Ask about a fear or hesitation around pursuing a goal." },
      { key: "future_self", guidance: "Ask about what the player's future self would thank them for starting." },
    ],
  },
  "Work 💼": {
    shallow: [
      { key: "focus_style", guidance: "Ask about how the player likes to focus during work." },
      { key: "meeting_style", guidance: "Ask about one light meeting or collaboration preference." },
      { key: "break_habits", guidance: "Ask about a small break habit that helps the player reset." },
      { key: "workspace_preference", guidance: "Ask about desk, workspace, tool, or environment preferences." },
      { key: "communication_style", guidance: "Ask about work messages, updates, directness, or response style." },
      { key: "task_start", guidance: "Ask about how the player likes starting a work task." },
      { key: "team_role", guidance: "Ask about one light role the player tends to take in a team." },
      { key: "work_snack", guidance: "Ask about one work snack or drink preference.", weight: 0.5 },
    ],
    deep: [
      { key: "motivation", guidance: "Ask about what energizes the player at work." },
      { key: "burnout", guidance: "Ask about what drains the player and how they recover." },
      { key: "leadership_pressure", guidance: "Ask about how responsibility changes the player's emotions or behavior." },
      { key: "trust", guidance: "Ask about what helps the player trust a team or manager." },
      { key: "speaking_up", guidance: "Ask about what helps the player speak up at work." },
      { key: "career_identity", guidance: "Ask about how work affects the player's sense of identity." },
      { key: "role_conflict", guidance: "Ask about handling competing priorities or expectations." },
      { key: "growth", guidance: "Ask about a work experience that changed the player's confidence." },
    ],
  },
  "Love 💖": {
    shallow: [
      { key: "date_preference", guidance: "Ask about one simple date or shared-time preference." },
      { key: "texting_style", guidance: "Ask about texting, replying, calling, or conversation style in dating." },
      { key: "small_gesture", guidance: "Ask about a small gesture that feels caring." },
      { key: "quality_time", guidance: "Ask about how the player likes spending relaxed time with someone." },
      { key: "planning_style", guidance: "Ask about planning dates, surprises, or spontaneous plans." },
      { key: "comfort_activity", guidance: "Ask about a realistic comfort activity in a relationship." },
      { key: "affection_style", guidance: "Ask about one light way the player shows affection." },
      { key: "shared_food", guidance: "Ask about a simple food or drink preference on a date.", weight: 0.5 },
    ],
    deep: [
      { key: "trust", guidance: "Ask about how trust is built or broken in small moments." },
      { key: "boundaries", guidance: "Ask about a boundary that helps the player feel safe and close." },
      { key: "communication", guidance: "Ask about what kind of communication helps the player feel understood." },
      { key: "repair", guidance: "Ask about reconnecting after hurt or misunderstanding." },
      { key: "needs", guidance: "Ask about a need that is hard for the player to say out loud." },
      { key: "intimacy", guidance: "Ask about emotional, intellectual, or experiential intimacy." },
      { key: "pattern", guidance: "Ask about a relationship pattern the player has noticed." },
      { key: "future_love", guidance: "Ask about what the player hopes to build in love." },
    ],
  },
  "Friends 🤝": {
    shallow: [
      { key: "hangout_style", guidance: "Ask about how the player likes spending time with friends." },
      { key: "group_chat", guidance: "Ask about group chat habits, replies, or message style." },
      { key: "friend_role", guidance: "Ask about one light role the player tends to have in a friend group." },
      { key: "party_preference", guidance: "Ask about a realistic social gathering preference." },
      { key: "checking_in", guidance: "Ask about simple ways the player likes checking in with friends." },
      { key: "shared_activity", guidance: "Ask about one activity the player enjoys doing with friends." },
      { key: "inside_joke", guidance: "Ask about light inside-joke or shared ritual energy." },
      { key: "snack_drink", guidance: "Ask about a snack or drink preference when hanging out.", weight: 0.5 },
    ],
    deep: [
      { key: "support", guidance: "Ask about how the player supports friends or receives support." },
      { key: "belonging", guidance: "Ask about friendships that make the player feel like themself." },
      { key: "loyalty", guidance: "Ask about what loyalty means to the player in friendship." },
      { key: "boundaries", guidance: "Ask about a friendship boundary the player values." },
      { key: "distance", guidance: "Ask about maintaining friendship through distance or busy seasons." },
      { key: "meaningful_conversation", guidance: "Ask about a conversation that made the player feel connected." },
      { key: "chosen_family", guidance: "Ask about chosen-family feelings in friendship." },
      { key: "being_remembered", guidance: "Ask about a time being remembered or reached for mattered." },
    ],
  },
  "Hobbies 🎨": {
    shallow: [
      { key: "favorite_hobby", guidance: "Ask about a hobby or interest the player enjoys." },
      { key: "hobby_to_try", guidance: "Ask about a hobby the player wants to try." },
      { key: "relaxation", guidance: "Ask how the player likes relaxing or recharging." },
      { key: "creative_routine", guidance: "Ask about one small creative routine or habit." },
      { key: "learning_style", guidance: "Ask how the player likes learning something new." },
      { key: "tools_places", guidance: "Ask about a tool, place, or setup connected to hobbies." },
      { key: "social_hobby", guidance: "Ask about hobbies done alone versus with other people." },
      { key: "hobby_snack", guidance: "Ask about a snack or drink around hobby time.", weight: 0.4 },
    ],
    deep: [
      { key: "identity", guidance: "Ask how a hobby shapes the player's identity outside responsibilities." },
      { key: "curiosity", guidance: "Ask about curiosity, play, or experimentation in the player's life." },
      { key: "discipline", guidance: "Ask about patience or discipline a hobby has taught the player." },
      { key: "confidence", guidance: "Ask about confidence built through a hobby." },
      { key: "mental_clarity", guidance: "Ask how leisure affects the player's mood or mental clarity." },
      { key: "belonging", guidance: "Ask about belonging or mentorship through a hobby community." },
      { key: "creative_growth", guidance: "Ask about creative growth or a learning curve." },
      { key: "purpose", guidance: "Ask why a hobby matters beyond productivity." },
    ],
  },
  "Travel ✈️": {
    shallow: [
      { key: "travel_style", guidance: "Ask whether the player prefers planned, relaxed, fast, or spontaneous travel." },
      { key: "free_day", guidance: "Ask how the player likes spending a free day in a new place." },
      { key: "packing_habit", guidance: "Ask about packing habits or comfort items." },
      { key: "weather_place", guidance: "Ask about travel weather, scenery, or place preferences." },
      { key: "trip_activity", guidance: "Ask about one activity the player likes doing while traveling." },
      { key: "travel_buddy", guidance: "Ask about light group-trip roles or travel buddy preferences." },
      { key: "airport_waiting", guidance: "Ask about what the player does while waiting during travel." },
      { key: "travel_food", guidance: "Ask about one food or drink preference while traveling.", weight: 0.5 },
    ],
    deep: [
      { key: "perspective_shift", guidance: "Ask about a trip that changed the player's perspective." },
      { key: "culture_shock", guidance: "Ask about a moment that challenged the player's assumptions." },
      { key: "openness", guidance: "Ask how travel affects the player's curiosity or openness." },
      { key: "local_conversation", guidance: "Ask about a conversation with someone local that stayed with the player." },
      { key: "privilege_awareness", guidance: "Ask about a travel moment that made the player more aware of inequality or privilege." },
      { key: "attention", guidance: "Ask about the difference between visiting and truly paying attention." },
      { key: "group_dynamic", guidance: "Ask about what travel reveals about the player in groups." },
      { key: "lesson", guidance: "Ask about a lesson from travel that stayed with the player." },
    ],
  },
  "Random 🎲": {
    shallow: [
      { key: "free_time", guidance: "Ask about what the player does with unexpected free time." },
      { key: "music_media", guidance: "Ask about music, shows, movies, books, or casual entertainment." },
      { key: "food_drink", guidance: "Ask about one everyday food or drink preference.", weight: 0.45 },
      { key: "communication_style", guidance: "Ask about texting, calling, replying, or talking in person." },
      { key: "planning_style", guidance: "Ask about planning ahead versus improvising." },
      { key: "weather_season", guidance: "Ask about weather, seasons, or the player's preferred atmosphere." },
      { key: "places", guidance: "Ask about places where the player likes spending time." },
      { key: "small_routine", guidance: "Ask about one small daily routine or habit." },
      { key: "social_preference", guidance: "Ask about quiet versus lively settings or social energy." },
      { key: "shopping_errands", guidance: "Ask about a realistic shopping, errand, or small-choice habit." },
      { key: "waiting_time", guidance: "Ask what the player does while waiting or between plans." },
      { key: "small_strength", guidance: "Ask about one simple thing the player is good at." },
    ],
    deep: [
      { key: "values", guidance: "Ask about one value that quietly guides the player." },
      { key: "turning_point", guidance: "Ask about one turning point that changed the player's direction." },
      { key: "relationship_pattern", guidance: "Ask about one recurring relationship pattern." },
      { key: "self_understanding", guidance: "Ask about something the player has learned about themself." },
      { key: "regret", guidance: "Ask about a regret or near-miss that still teaches the player something." },
      { key: "hope", guidance: "Ask about a hope the player carries into the future." },
      { key: "belief_change", guidance: "Ask about a belief that softened or strengthened over time." },
      { key: "hidden_story", guidance: "Ask about a part of the player's story they rarely share." },
    ],
  },
};

export function selectQuestionAngles(theme: string, level: "shallow" | "deep", count: number, recentKeys: string[] = []): QuestionAngle[] {
  const catalog = QUESTION_ANGLES[theme]?.[level] ?? GENERIC_QUESTION_ANGLES[level];
  const target = Math.max(1, Math.min(count, catalog.length));
  const recent = new Set(recentKeys.slice(-3));
  let available = catalog.filter((a) => !recent.has(a.key));
  if (available.length < target) available = [...catalog];

  const selected: QuestionAngle[] = [];
  let pool = [...available];
  while (pool.length && selected.length < target) {
    const weights = pool.map((a) => Math.max(a.weight ?? 1, 0.01));
    const total = weights.reduce((s, w) => s + w, 0);
    let r = Math.random() * total;
    let idx = 0;
    for (let i = 0; i < pool.length; i++) {
      r -= weights[i];
      if (r <= 0) { idx = i; break; }
    }
    selected.push(pool[idx]);
    pool = pool.filter((a) => a.key !== pool[idx].key);
  }
  return selected;
}
