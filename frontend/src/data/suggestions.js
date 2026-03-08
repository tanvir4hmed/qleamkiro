/**
 * Qleam — Context-Aware Suggestion Engine
 *
 * Each emotion has a pool of condition-tagged suggestions.
 * Selection avoids repeats, respects context, and escalates
 * when the baby is persistently unsettled.
 *
 * Conditions:
 *   age_max_days  — only show if child age <= this
 *   age_min_days  — only show if child age >= this
 *   group         — dedup group (pick max 1 per group)
 *   variants      — alternative phrasings (randomly picked)
 */

const SUGGESTIONS = {
  hungry: [
    {
      text: "Try offering a feed — hunger cries tend to build when the need isn't met",
      group: "feed",
      variants: [
        "Your baby might be ready to eat",
        "Hunger cries often escalate — offering a feed now may settle things quickly",
      ],
    },
    {
      text: "If you recently fed, try burping first — sometimes gas mimics hunger",
      group: "burp_check",
    },
    {
      text: "Check if rooting reflex is present — gently stroke their cheek",
      group: "check",
      age_max_days: 120,
    },
    {
      text: "Watch for hand-to-mouth movements — another hunger cue to confirm",
      group: "observe",
    },
    {
      text: "Try a different feeding position if baby is fussy at the breast or bottle",
      group: "position",
    },
    {
      text: "If bottle feeding, check that the flow rate matches your baby's age",
      group: "flow",
    },
    {
      text: "Cluster feeding is normal in the first few months — baby may want to feed again soon",
      group: "cluster",
      age_max_days: 90,
    },
    {
      text: "Offer skin-to-skin contact while feeding — it can help baby settle and feed better",
      group: "skin_to_skin",
      age_max_days: 120,
    },
  ],
  tired: [
    {
      text: "Start a calming routine — dim lights, reduce stimulation, lower your voice",
      group: "routine",
      variants: [
        "Try dimming the lights and reducing noise to help your baby wind down",
      ],
    },
    {
      text: "Try gentle rocking, swaddling, or white noise",
      group: "soothe",
      variants: [
        "Rhythmic motion (rocking, swaying) can help soothe a tired baby",
      ],
    },
    {
      text: "Watch for sleep cues: eye rubbing, ear pulling, looking away",
      group: "observe",
    },
    {
      text: "Try putting baby down slightly awake — they may self-settle",
      group: "self_settle",
      age_min_days: 60,
    },
    {
      text: "A warm bath before bed can signal that it's time to sleep",
      group: "bath",
    },
    {
      text: "Swaddling can help newborns feel secure and settle faster",
      group: "swaddle",
      age_max_days: 120,
    },
    {
      text: "Check the room temperature — babies sleep best around 18-22°C (65-72°F)",
      group: "temp",
    },
    {
      text: "If overtired, baby may fight sleep harder — a shorter wake window next time may help",
      group: "wake_window",
    },
  ],
  discomfort: [
    {
      text: "Check diaper, clothing tightness, and temperature (too hot or cold)",
      group: "check",
      variants: [
        "A quick comfort check — diaper, clothing, room temperature",
      ],
    },
    {
      text: "Try repositioning — baby might need a change of position",
      group: "position",
    },
    {
      text: "Check for tags, seams, or rough fabric touching skin",
      group: "fabric",
    },
    {
      text: "A change of scenery can sometimes help — try moving to a different room",
      group: "scenery",
    },
    {
      text: "Skin-to-skin contact can help soothe general discomfort",
      group: "skin_to_skin",
    },
    {
      text: "Check if baby's fingers or toes are caught in clothing (hair tourniquet)",
      group: "tourniquet",
    },
    {
      text: "Try a warm (not hot) compress on baby's tummy if they seem bloated",
      group: "warm",
    },
  ],
  gas: [
    {
      text: "Try gentle tummy massage in clockwise circles",
      group: "massage",
      variants: [
        "Clockwise belly massage can help move trapped gas through the digestive system",
      ],
    },
    {
      text: "Bicycle legs gently to help release trapped gas",
      group: "bicycle",
      variants: [
        "Gently cycling baby's legs can help relieve gas pressure",
      ],
    },
    {
      text: "Hold baby upright and gently pat or rub the back",
      group: "upright",
    },
    {
      text: "Try holding baby face-down along your forearm (the 'colic hold')",
      group: "colic_hold",
      age_max_days: 120,
    },
    {
      text: "If breastfeeding, consider whether something in your diet might be causing gas",
      group: "diet",
    },
    {
      text: "Tummy time (when awake and supervised) can help with gas throughout the day",
      group: "tummy_time",
    },
    {
      text: "Anti-colic bottles with slower flow can reduce air swallowed during feeding",
      group: "bottle",
    },
    {
      text: "A warm bath can relax abdominal muscles and help gas pass",
      group: "bath",
    },
  ],
  pain: [
    {
      text: "Check for obvious pain sources: hair tourniquet, pinching, rash",
      group: "check",
    },
    {
      text: "Gently examine fingers, toes, and body for anything unusual",
      group: "examine",
    },
    {
      text: "If crying persists or seems unusual, consult your pediatrician",
      group: "doctor",
    },
    {
      text: "Try skin-to-skin contact — your warmth and heartbeat can provide comfort",
      group: "skin_to_skin",
    },
    {
      text: "Check gums for teething signs — swollen, red, or with visible bumps",
      group: "teething",
      age_min_days: 90,
    },
    {
      text: "If baby has a fever or seems unwell, seek medical advice",
      group: "fever",
    },
    {
      text: "A cool teething ring (not frozen) can help if teething is the cause",
      group: "teething_ring",
      age_min_days: 90,
    },
  ],
  burp: [
    {
      text: "Hold baby upright against your shoulder and gently pat the back",
      group: "shoulder",
      variants: [
        "The over-the-shoulder hold with gentle back pats usually works well",
      ],
    },
    {
      text: "Try sitting baby upright with chin support and gentle back rubs",
      group: "sitting",
    },
    {
      text: "If breastfeeding, try burping between switching sides",
      group: "between_feeds",
    },
    {
      text: "Try the face-down-on-lap position with gentle back patting",
      group: "lap",
    },
    {
      text: "Some babies need 5-10 minutes of upright holding after feeds",
      group: "wait",
    },
    {
      text: "A gentle bounce while holding upright can help the burp come up",
      group: "bounce",
    },
  ],
  content: [
    {
      text: "Continue what you're doing — baby seems settled",
      group: "continue",
    },
    {
      text: "Respond with gentle voice to encourage communication",
      group: "talk",
      variants: [
        "Talk back to your baby — responding to vocalizations builds language",
      ],
    },
    {
      text: "This is a great time for face-to-face interaction and play",
      group: "play",
    },
    {
      text: "Observe for any changes that might indicate a shift in mood",
      group: "observe",
    },
    {
      text: "Tummy time during content periods builds strength and coordination",
      group: "tummy_time",
      age_max_days: 180,
    },
  ],
};

const ESCALATION_SUGGESTIONS = [
  "Your baby seems persistently unsettled. If basic comfort measures haven't helped, check temperature and consider whether they might be feeling unwell.",
  "Multiple unsettled sessions — try a completely different approach. If you've been stimulating, try calm darkness. If you've been still, try gentle movement.",
  "If your baby has been crying for an extended period without settling, it's okay to call your pediatrician for guidance.",
  "Take a moment for yourself too — a persistently fussy baby is stressful. It's okay to put baby down safely and take a short break.",
];

/**
 * Select 2-3 suggestions based on context.
 *
 * @param {string} emotion - Primary emotion key
 * @param {object} options
 * @param {number} options.ageDays - Child age in days
 * @param {string} options.childId - For localStorage tracking
 * @param {number} options.sessionCountToday - Sessions today (for escalation)
 * @returns {string[]} Selected suggestion texts
 */
function pickSuggestions(emotion, options = {}) {
  const { ageDays, childId, sessionCountToday = 0 } = options;
  const pool = SUGGESTIONS[emotion] || SUGGESTIONS.discomfort;

  // Escalation: 3+ cry sessions today
  if (sessionCountToday >= 3) {
    const escIdx = Math.min(sessionCountToday - 3, ESCALATION_SUGGESTIONS.length - 1);
    const escalation = ESCALATION_SUGGESTIONS[Math.max(0, escIdx)];
    return [escalation];
  }

  // Filter by age conditions
  const eligible = pool.filter((s) => {
    if (s.age_max_days !== undefined && ageDays !== null && ageDays !== undefined && ageDays > s.age_max_days) return false;
    if (s.age_min_days !== undefined && ageDays !== null && ageDays !== undefined && ageDays < s.age_min_days) return false;
    return true;
  });

  // Get recently shown for this child
  const storageKey = `qleam_sugg_${childId || 'default'}_${emotion}`;
  let recentTexts = [];
  try {
    recentTexts = JSON.parse(localStorage.getItem(storageKey) || '[]');
  } catch (_) {}

  // Filter out recently shown (by base text)
  const fresh = eligible.filter((s) => !recentTexts.includes(s.text));
  const source = fresh.length >= 2 ? fresh : eligible;

  // Pick 2-3 from different groups
  const picked = [];
  const usedGroups = new Set();
  const shuffled = [...source].sort(() => Math.random() - 0.5);

  for (const s of shuffled) {
    if (picked.length >= 3) break;
    if (usedGroups.has(s.group)) continue;
    usedGroups.add(s.group);

    // Pick a random variant or use base text
    let text = s.text;
    if (s.variants && s.variants.length > 0 && Math.random() > 0.5) {
      text = s.variants[Math.floor(Math.random() * s.variants.length)];
    }
    picked.push(text);
  }

  // Update history (keep last 5 base texts)
  const newRecent = [...recentTexts, ...picked].slice(-5);
  try {
    localStorage.setItem(storageKey, JSON.stringify(newRecent));
  } catch (_) {}

  return picked.length > 0 ? picked : [pool[0].text];
}

export { SUGGESTIONS, ESCALATION_SUGGESTIONS, pickSuggestions };
