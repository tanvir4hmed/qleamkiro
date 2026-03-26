"""
Qleam — Developmental Stage Router
Routes analysis and feedback based on baby's developmental stage.

6 Developmental Stages:
- Stage A (0-90 days): Newborn cry-only period
- Stage B (91-180 days): Early vocalizations, cooing
- Stage C (181-270 days): Canonical babbling begins
- Stage D (271-365 days): Advanced babbling, proto-words
- Stage E (366-548 days): First words, word combinations
- Stage F (549-730 days): Multi-word phrases, sentences

Phase 6: Stage-aware routing for analysis and feedback.
"""
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Developmental Stage Definitions
# =============================================================================

DEVELOPMENTAL_STAGES = {
    "A": {
        "name": "Newborn",
        "age_range": (0, 90),
        "description": "Cry-only period with reflexive vocalizations",
        "primary_signals": ["cry"],
        "secondary_signals": [],
        "dunstan_applicable": True,
        "feedback_focus": ["emotion", "intensity", "pattern"],
        "analysis_mode": "cry_only",
    },
    "B": {
        "name": "Early Vocalizations",
        "age_range": (91, 180),
        "description": "Cooing, vowel sounds, early vocal play",
        "primary_signals": ["cry", "vocalization"],
        "secondary_signals": ["laugh"],
        "dunstan_applicable": False,
        "feedback_focus": ["emotion", "vocalization_type", "responsiveness"],
        "analysis_mode": "cry_and_vocalization",
    },
    "C": {
        "name": "Canonical Babbling",
        "age_range": (181, 270),
        "description": "Repetitive syllables (ba-ba, da-da)",
        "primary_signals": ["cry", "babble"],
        "secondary_signals": ["laugh", "vocalization"],
        "dunstan_applicable": False,
        "feedback_focus": ["emotion", "babble_type", "syllable_structure"],
        "analysis_mode": "cry_and_babble",
    },
    "D": {
        "name": "Advanced Babbling",
        "age_range": (271, 365),
        "description": "Varied babbling, proto-words, intonation patterns",
        "primary_signals": ["babble", "cry"],
        "secondary_signals": ["proto_word", "laugh"],
        "dunstan_applicable": False,
        "feedback_focus": ["babble_type", "proto_words", "emotion", "turn_taking"],
        "analysis_mode": "babble_primary",
    },
    "E": {
        "name": "First Words",
        "age_range": (366, 548),
        "description": "First words, word combinations, intentional communication",
        "primary_signals": ["speech", "babble"],
        "secondary_signals": ["cry", "laugh"],
        "dunstan_applicable": False,
        "feedback_focus": ["words", "word_count", "clarity", "emotion"],
        "analysis_mode": "speech_primary",
    },
    "F": {
        "name": "Multi-Word Phrases",
        "age_range": (549, 730),
        "description": "Multi-word phrases, simple sentences, complex communication",
        "primary_signals": ["speech"],
        "secondary_signals": ["babble", "cry", "laugh"],
        "dunstan_applicable": False,
        "feedback_focus": ["words", "sentence_structure", "vocabulary", "emotion"],
        "analysis_mode": "speech_advanced",
    },
}


def get_stage_for_age(age_days: int) -> str:
    """
    Get developmental stage for given age.
    
    Args:
        age_days: Baby's age in days
    
    Returns:
        Stage code: "A", "B", "C", "D", "E", or "F"
    """
    if age_days <= 90:
        return "A"
    elif age_days <= 180:
        return "B"
    elif age_days <= 270:
        return "C"
    elif age_days <= 365:
        return "D"
    elif age_days <= 548:
        return "E"
    else:
        return "F"


def get_stage_info(stage: str) -> Dict:
    """
    Get full information for a developmental stage.
    
    Args:
        stage: Stage code ("A"-"F")
    
    Returns:
        Stage info dict or empty dict if invalid
    """
    return DEVELOPMENTAL_STAGES.get(stage, {})


def should_analyze_cry(stage: str, sound_type: str) -> bool:
    """
    Determine if cry analysis should be performed for this stage/sound.
    
    Args:
        stage: Developmental stage ("A"-"F")
        sound_type: Sound type from classifier
    
    Returns:
        True if cry analysis should be performed
    """
    stage_info = get_stage_info(stage)
    if not stage_info:
        return sound_type == "cry"
    
    # Always analyze if sound_type is cry
    if sound_type == "cry":
        return True
    
    # For mixed signals, analyze cry if it's a primary signal for this stage
    if sound_type == "mixed":
        return "cry" in stage_info.get("primary_signals", [])
    
    return False


def should_analyze_babble(stage: str, sound_type: str) -> bool:
    """
    Determine if babble analysis should be performed for this stage/sound.
    
    Args:
        stage: Developmental stage ("A"-"F")
        sound_type: Sound type from classifier
    
    Returns:
        True if babble analysis should be performed
    """
    stage_info = get_stage_info(stage)
    if not stage_info:
        return False
    
    # Babble analysis only for stages C-F
    if stage not in ["C", "D", "E", "F"]:
        return False
    
    # Analyze if sound_type is speech or mixed (babble detected in speech)
    if sound_type in ["speech", "mixed"]:
        return True
    
    return False


def should_analyze_speech(stage: str, sound_type: str) -> bool:
    """
    Determine if speech/word analysis should be performed for this stage/sound.
    
    Args:
        stage: Developmental stage ("A"-"F")
        sound_type: Sound type from classifier
    
    Returns:
        True if speech analysis should be performed
    """
    stage_info = get_stage_info(stage)
    if not stage_info:
        return False
    
    # Speech analysis only for stages E-F
    if stage not in ["E", "F"]:
        return False
    
    # Analyze if sound_type is speech or mixed
    if sound_type in ["speech", "mixed"]:
        return True
    
    return False


def get_feedback_schema(stage: str) -> Dict:
    """
    Get feedback schema for a developmental stage.
    
    Returns the appropriate feedback questions and options based on stage.
    
    Args:
        stage: Developmental stage ("A"-"F")
    
    Returns:
        Feedback schema dict with questions and options
    """
    stage_info = get_stage_info(stage)
    if not stage_info:
        stage_info = DEVELOPMENTAL_STAGES["A"]
    
    focus_areas = stage_info.get("feedback_focus", [])
    
    schema = {
        "stage": stage,
        "stage_name": stage_info.get("name", "Unknown"),
        "questions": [],
    }
    
    # Build questions based on focus areas
    if "emotion" in focus_areas:
        schema["questions"].append({
            "id": "emotion_accuracy",
            "type": "rating",
            "question": "How accurate was the emotion detection?",
            "scale": 5,
            "required": True,
        })
        schema["questions"].append({
            "id": "emotion_correction",
            "type": "select",
            "question": "If incorrect, what was the actual emotion?",
            "options": ["hungry", "tired", "discomfort", "gas", "pain", "burp", "content"],
            "required": False,
        })
    
    if "babble_type" in focus_areas:
        schema["questions"].append({
            "id": "babble_type",
            "type": "select",
            "question": "What type of babbling did you hear?",
            "options": ["canonical", "vowel_play", "responsive", "proto_word", "none"],
            "required": False,
        })
    
    if "proto_words" in focus_areas:
        schema["questions"].append({
            "id": "proto_words_detected",
            "type": "boolean",
            "question": "Did you hear any proto-words (word-like sounds)?",
            "required": False,
        })
    
    if "words" in focus_areas:
        schema["questions"].append({
            "id": "words_detected",
            "type": "boolean",
            "question": "Did your baby say any recognizable words?",
            "required": False,
        })
        schema["questions"].append({
            "id": "word_list",
            "type": "text",
            "question": "If yes, what words did they say?",
            "required": False,
        })
    
    if "turn_taking" in focus_areas:
        schema["questions"].append({
            "id": "turn_taking",
            "type": "rating",
            "question": "Was your baby responding to your voice?",
            "scale": 5,
            "required": False,
        })
    
    # Always include general feedback
    schema["questions"].append({
        "id": "general_feedback",
        "type": "text",
        "question": "Any additional observations?",
        "required": False,
    })
    
    return schema


def get_analysis_routing(age_days: int, sound_type: str) -> Dict:
    """
    Get complete analysis routing for a session.
    
    Determines which analysis modules should run based on stage and sound type.
    
    Args:
        age_days: Baby's age in days
        sound_type: Sound type from classifier
    
    Returns:
        {
            "stage": "C",
            "stage_name": "Canonical Babbling",
            "run_cry_analysis": True,
            "run_babble_analysis": True,
            "run_speech_analysis": False,
            "run_transcription": False,
            "use_dunstan": False,
            "primary_analysis": "babble",
        }
    """
    stage = get_stage_for_age(age_days)
    stage_info = get_stage_info(stage)
    
    routing = {
        "stage": stage,
        "stage_name": stage_info.get("name", "Unknown"),
        "age_days": age_days,
        "sound_type": sound_type,
        "run_cry_analysis": should_analyze_cry(stage, sound_type),
        "run_babble_analysis": should_analyze_babble(stage, sound_type),
        "run_speech_analysis": should_analyze_speech(stage, sound_type),
        "run_transcription": stage in ["E", "F"] and sound_type in ["speech", "mixed"],
        "use_dunstan": stage_info.get("dunstan_applicable", False) and sound_type == "cry",
        "analysis_mode": stage_info.get("analysis_mode", "cry_only"),
    }
    
    # Determine primary analysis
    if routing["run_speech_analysis"]:
        routing["primary_analysis"] = "speech"
    elif routing["run_babble_analysis"]:
        routing["primary_analysis"] = "babble"
    elif routing["run_cry_analysis"]:
        routing["primary_analysis"] = "cry"
    else:
        routing["primary_analysis"] = "none"
    
    return routing


def get_multi_signal_headline(
    stage: str,
    cry_emotion: Optional[str] = None,
    babble_type: Optional[str] = None,
    word_count: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Get headline for multi-signal sessions (cry + babble, cry + speech, etc.).
    
    Args:
        stage: Developmental stage
        cry_emotion: Detected cry emotion (if any)
        babble_type: Detected babble type (if any)
        word_count: Number of words detected (if any)
    
    Returns:
        (headline, icon) tuple
    """
    stage_info = get_stage_info(stage)
    
    # Stage E-F: Words take priority
    if stage in ["E", "F"] and word_count and word_count > 0:
        if cry_emotion:
            return (f"Your baby said {word_count} word(s) while {cry_emotion}", "🗣️😢")
        else:
            return (f"Your baby said {word_count} word(s)!", "🗣️")
    
    # Stage C-D: Babble + cry
    if stage in ["C", "D"] and babble_type and cry_emotion:
        babble_names = {
            "canonical": "repetitive babbling",
            "vowel_play": "vowel sounds",
            "responsive": "responsive babbling",
            "proto_word": "word-like sounds",
        }
        babble_name = babble_names.get(babble_type, "babbling")
        return (f"Your baby is {babble_name} and crying ({cry_emotion})", "👶😢")
    
    # Stage C-D: Babble only
    if stage in ["C", "D"] and babble_type:
        babble_names = {
            "canonical": "Repetitive babbling detected!",
            "vowel_play": "Vowel play detected!",
            "responsive": "Responsive babbling detected!",
            "proto_word": "Word-like sounds detected!",
        }
        return (babble_names.get(babble_type, "Babbling detected!"), "👶")
    
    # Default: Cry emotion
    if cry_emotion:
        emotion_icons = {
            "hungry": "🍼",
            "tired": "😴",
            "discomfort": "😟",
            "gas": "💨",
            "pain": "🩹",
            "burp": "🫧",
            "content": "😊",
        }
        icon = emotion_icons.get(cry_emotion, "😢")
        return (f"{cry_emotion.capitalize()}", icon)
    
    # Fallback
    return ("Mixed sounds detected", "🔊")


def get_stage_appropriate_suggestions(stage: str, sound_type: str) -> list:
    """
    Get stage-appropriate suggestions for parents.
    
    Args:
        stage: Developmental stage
        sound_type: Sound type detected
    
    Returns:
        List of suggestion strings
    """
    suggestions = []
    
    if stage == "A":
        suggestions = [
            "Respond promptly to cries to build trust",
            "Try different soothing techniques (rocking, swaddling, white noise)",
            "Keep a cry diary to identify patterns",
        ]
    elif stage == "B":
        suggestions = [
            "Respond to cooing sounds to encourage vocalization",
            "Make eye contact and smile when baby vocalizes",
            "Imitate baby's sounds to promote turn-taking",
        ]
    elif stage == "C":
        suggestions = [
            "Repeat babbling sounds back to encourage practice",
            "Introduce simple words during daily routines",
            "Read books with repetitive sounds (ba-ba, da-da)",
        ]
    elif stage == "D":
        suggestions = [
            "Respond to proto-words as if they're real words",
            "Expand on baby's sounds ('ba' → 'Yes, ball!')",
            "Play turn-taking games (peek-a-boo, pat-a-cake)",
        ]
    elif stage == "E":
        suggestions = [
            "Celebrate first words with enthusiasm",
            "Expand single words into short phrases",
            "Name objects during play and daily activities",
        ]
    elif stage == "F":
        suggestions = [
            "Ask simple questions and wait for responses",
            "Expand two-word phrases into full sentences",
            "Read books together and discuss pictures",
        ]
    
    return suggestions
