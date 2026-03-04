"""
Qleam — Word Analyzer
Analyzes detected words against age-appropriate expectations.
Determines baby vs adult speech patterns based on vocabulary,
sentence complexity, and word count relative to developmental stage.

Research-based word milestones:
- 0-6 months: No words expected, only cooing/babbling
- 6-12 months: First words possible ("mama", "dada", "baba") — 0-3 words typical
- 12-18 months: 3-20 words, single word utterances, mostly nouns
- 18-24 months: 50-200 words, 2-3 word combinations ("more milk", "mama go")
- 24-36 months: 200-1000 words, short sentences, pronouns, verbs

Sources:
- CDI (MacArthur-Bates Communicative Development Inventories)
- Fenson et al. (2007) — vocabulary norms
- Bloom (1973) — early word combinations
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Age-based word expectations (research-based norms)
# ---------------------------------------------------------------------------
WORD_EXPECTATIONS = {
    "0_6m": {
        "expected_words": 0,
        "max_words": 0,
        "description": "No words expected at this age. Only cooing, vowel sounds, and early babbling",
        "typical_sounds": ["cooing", "vowel sounds", "gurgling", "early babbling"],
        "if_words_found": "Words detected at this age are unexpected and likely from an adult or older child",
        "adult_indicator_threshold": 1,  # Any words = likely adult
    },
    "6_12m": {
        "expected_words": 1,
        "max_words": 5,
        "description": "First words may appear — typically 'mama', 'dada', 'baba'. Usually 0-3 words",
        "typical_words": ["mama", "dada", "baba", "no", "bye", "hi"],
        "if_too_many_words": "More words than typical for this age. The speaker may be older or an adult",
        "adult_indicator_threshold": 8,  # >8 distinct words very unusual
    },
    "12_18m": {
        "expected_words": 10,
        "max_words": 50,
        "description": "Vocabulary growing — typically 3-20 words. Mostly nouns, some verbs",
        "typical_words": ["mama", "dada", "ball", "dog", "cat", "more", "no", "up", "milk", "water", "baby", "shoe", "book"],
        "if_too_many_words": "Vocabulary size suggests an older child or adult",
        "adult_indicator_threshold": 30,
    },
    "18_24m": {
        "expected_words": 50,
        "max_words": 200,
        "description": "Vocabulary explosion — 50-200 words. Starting 2-3 word combinations",
        "typical_patterns": ["two-word combinations", "simple requests", "naming things"],
        "example_phrases": ["more milk", "mama go", "want that", "no sleep", "big dog"],
        "adult_indicator_threshold": 100,  # Per utterance, not vocabulary
    },
    "24_36m": {
        "expected_words": 200,
        "max_words": 1000,
        "description": "200-1000 words. Short sentences, pronouns, verbs, questions",
        "typical_patterns": ["short sentences", "questions", "pronouns", "past tense attempts"],
        "example_phrases": ["I want milk", "where daddy go?", "me do it", "that's mine"],
        "adult_indicator_threshold": 150,
    },
}


def _has_non_latin_script(words: set) -> bool:
    """
    Check if any words contain non-Latin characters (CJK, Arabic, Devanagari, etc.).

    Baby first words are universally in the family's spoken language using basic
    phonemes. If transcription returns CJK/Arabic/etc. characters for a young
    baby, it's either an adult speaker or a transcription language misdetection.
    """
    import re
    # Match any character outside Basic Latin + Latin Extended ranges
    non_latin_pattern = re.compile(r'[^\u0000-\u024F\u1E00-\u1EFF]')
    for word in words:
        if non_latin_pattern.search(word):
            return True
    return False


def _get_age_bracket(age_days: Optional[int]) -> str:
    """Convert age in days to bracket."""
    if age_days is None or age_days < 0:
        return "0_6m"
    months = age_days / 30.44
    if months < 6:
        return "0_6m"
    elif months < 12:
        return "6_12m"
    elif months < 18:
        return "12_18m"
    elif months < 24:
        return "18_24m"
    else:
        return "24_36m"


def analyze_words_by_age(
    word_analysis: Dict,
    age_days: Optional[int],
    is_adult_voice: bool = False,
) -> Dict[str, Any]:
    """
    Analyze detected words against age expectations.

    Args:
        word_analysis: Output from speech_transcriber.analyze_words_for_display()
        age_days: Child's age in days
        is_adult_voice: Whether adult voice was detected by voice analysis

    Returns:
        {
            "speaker_assessment": "baby" | "adult" | "uncertain",
            "age_match": True/False,
            "age_match_detail": str,
            "registered_age_bracket": str,
            "probable_age_bracket": str,  # Based on word analysis
            "word_count_assessment": str,
            "vocabulary_assessment": str,
            "mismatch_warning": str or None,
            "display_summary": str,
        }
    """
    age_bracket = _get_age_bracket(age_days)
    expectations = WORD_EXPECTATIONS.get(age_bracket, WORD_EXPECTATIONS["0_6m"])

    word_count = word_analysis.get("word_count", 0)
    unique_words = word_analysis.get("unique_word_count", 0)
    has_sentences = word_analysis.get("has_sentences", False)
    display_words = word_analysis.get("display_words", [])
    display_text = word_analysis.get("display_text", "")

    bracket_labels = {
        "0_6m": "0-6 months",
        "6_12m": "6-12 months",
        "12_18m": "12-18 months",
        "18_24m": "18-24 months",
        "24_36m": "24-36 months",
    }

    # --- Speaker assessment (baby vs adult) ---
    adult_threshold = expectations.get("adult_indicator_threshold", 50)
    speaker = "uncertain"

    # Check if detected words use non-Latin script (strong adult/misdetection signal)
    found_words = set(w["word"].lower() for w in display_words) if display_words else set()
    non_latin_words = _has_non_latin_script(found_words)

    if is_adult_voice:
        speaker = "adult"
    elif age_bracket == "0_6m" and word_count > 0:
        speaker = "adult"  # No baby speaks at 0-6 months
    elif non_latin_words and age_bracket in ("0_6m", "6_12m", "12_18m"):
        speaker = "adult"  # Non-Latin script at young ages = adult or transcription error
    elif unique_words > adult_threshold:
        speaker = "adult"  # Too many words for registered age
    elif has_sentences and age_bracket in ("0_6m", "6_12m"):
        speaker = "adult"  # Sentences at this age = adult
    elif word_count == 0:
        speaker = "baby"
    else:
        # Heuristic: check if words match baby-typical vocabulary
        if age_bracket in ("6_12m", "12_18m"):
            typical = set(expectations.get("typical_words", []))
            overlap = found_words & typical
            if len(overlap) > 0 and unique_words <= expectations["max_words"]:
                speaker = "baby"
            elif unique_words > expectations["max_words"]:
                speaker = "adult"
            elif non_latin_words:
                speaker = "adult"  # Foreign script with no typical word overlap
            else:
                speaker = "uncertain"
        else:
            speaker = "baby" if unique_words <= expectations["max_words"] else "adult"

    # --- Age match assessment ---
    age_match = True
    probable_bracket = age_bracket
    mismatch_warning = None

    if word_count > 0:
        # Find which age bracket the word count best matches
        probable_bracket = _estimate_age_from_words(unique_words, has_sentences, display_text)

        if probable_bracket != age_bracket:
            age_match = False
            mismatch_warning = (
                f"Word patterns suggest {bracket_labels.get(probable_bracket, probable_bracket)} "
                f"level, but child is registered as {bracket_labels.get(age_bracket, age_bracket)}"
            )

    # --- Word count assessment ---
    if word_count == 0:
        word_assessment = "No words detected"
    elif unique_words <= expectations.get("expected_words", 0):
        word_assessment = f"{unique_words} word(s) — within typical range for {bracket_labels[age_bracket]}"
    elif unique_words <= expectations.get("max_words", 0):
        word_assessment = f"{unique_words} word(s) — good vocabulary for {bracket_labels[age_bracket]}"
    else:
        word_assessment = f"{unique_words} word(s) — above typical range for {bracket_labels[age_bracket]}"

    # --- Build display summary ---
    if speaker == "adult":
        summary = f"Adult speech detected with {word_count} words"
    elif speaker == "baby" and word_count > 0:
        if age_match:
            summary = f"Your baby said {word_count} word(s) — consistent with {bracket_labels[age_bracket]}"
        else:
            summary = f"Words detected but pattern suggests {bracket_labels.get(probable_bracket, 'different age')}"
    elif speaker == "uncertain":
        summary = f"{word_count} word(s) detected — speaker identity uncertain"
    else:
        summary = "No words detected in this recording"

    return {
        "speaker_assessment": speaker,
        "age_match": age_match,
        "age_match_detail": expectations.get("description", ""),
        "registered_age_bracket": bracket_labels.get(age_bracket, age_bracket),
        "probable_age_bracket": bracket_labels.get(probable_bracket, probable_bracket),
        "word_count_assessment": word_assessment,
        "mismatch_warning": mismatch_warning,
        "display_summary": summary,
        "adult_indicator_threshold": adult_threshold,
    }


def _estimate_age_from_words(
    unique_words: int,
    has_sentences: bool,
    text: str,
) -> str:
    """Estimate probable age bracket based on word patterns."""
    # Sentence complexity check
    words_in_text = len(text.split()) if text else 0

    if has_sentences and words_in_text > 10:
        return "24_36m"
    elif has_sentences and words_in_text > 5:
        return "18_24m"
    elif unique_words > 20:
        return "18_24m"
    elif unique_words > 5:
        return "12_18m"
    elif unique_words > 0:
        return "6_12m"
    else:
        return "0_6m"
