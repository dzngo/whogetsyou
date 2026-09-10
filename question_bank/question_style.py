"""Shared generation and evaluation guidance for the two question Levels."""

SHALLOW_MISSIONS = (
    "Everyday tastes: favorites, dislikes, textures, flavors, colors, weather, seasons, and small comforts.",
    "Routines and timing: mornings, evenings, weekends, getting home, sleep, errands, and ordinary rituals.",
    "Entertainment and attention: music, movies, shows, games, apps, reading, hobbies, and things talked about often.",
    "Belongings and personal style: things carried, clothes, accessories, collections, useful possessions, and home comforts.",
    "Places and getting around: preferred settings, local outings, transport habits, travel tastes, and holiday activities.",
    "Shopping and spending: regular orders, treats, impulse buys, things rarely bought, gifts, and practical priorities.",
    "Skills and curiosity: everyday strengths, harmless weaknesses, things to learn, and activities enjoyed for hours.",
    "Social everyday habits: messaging, invitations, group activities, hosting, punctuality, and easy companionship.",
    "Small reactions and quirks: boredom, procrastination, picky preferences, minor annoyances, simple relaxation, and mood boosters.",
    "Simple realistic choices: familiar alternatives, planning versus improvising, comfort versus novelty, and ordinary what-would-I-pick situations.",
)

SHALLOW_GUIDANCE = {
    "definition": "Light everyday familiarity: something the Storyteller can answer immediately and friends can plausibly guess.",
    "answer": "Invite one short answer: an item, time, activity, preference, habit, or simple choice. No explanation required.",
    "style": "Use concise natural first-person questions (my/I). Usually 5–15 words; avoid unnecessary setup and multi-part questions.",
    "allowed": "Generic favorites and polls are good. Stress, mood, and social habits are fine when concrete, light, and non-analytical.",
    "avoid": "Do not require a story, exact recent incident, emotional disclosure, relationship repair, hidden signals, values analysis, or reasons why.",
    "variety": "Vary subjects and answer kinds, not complexity. Shared favorite/usually wording is fine across distinct subjects. Do not paraphrase the same question.",
    "examples": [
        "What's my favorite food?", "What time do I usually wake up?",
        "What app do I use the most?", "What am I usually late for?",
        "What kind of gift would make me happy?", "What am I very picky about?",
        "What do I usually do when stressed?", "What could I do for hours without getting bored?",
    ],
    "counterexamples": [
        "What compliment made you feel truly understood, and why?",
        "Describe the last item you bought and exactly where it is now.",
        "How can others tell when you need advice rather than emotional support?",
    ],
}

DEEP_GUIDANCE = {
    "definition": "Reflective and emotionally safe; a short answer reveals a personal value, memory, belief, hope, or characteristic.",
    "style": "Concrete and answerable without therapy framing, forced disclosure, or a required long explanation.",
}
