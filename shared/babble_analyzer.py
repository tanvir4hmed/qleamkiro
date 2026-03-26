"""
Qleam — Babble Analyzer
Analyzes babbling patterns for developmental stages C-F (6-24 months).

Babble Types:
- Canonical: Repetitive syllables (ba-ba, da-da, ma-ma)
- Vowel Play: Extended vowel sounds (aaa, ooo, eee)
- Responsive: Babbling in response to adult speech (turn-taking)
- Proto-Word: Word-like sounds with consistent meaning

Phase 6: Babble analysis for stages C-D-E-F.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# Babble Type Definitions
# =============================================================================

BABBLE_TYPES = {
    "canonical": {
        "label": "Canonical Babbling",
        "icon": "👶",
        "description": "Repetitive syllables like 'ba-ba' or 'da-da'",
        "age_range": (180, 365),
        "what_hearing": "Repetitive consonant-vowel combinations with clear syllable structure",
        "what_means": "Your baby is practicing the building blocks of speech. This is a crucial milestone in language development.",
        "what_try": [
            "Repeat the sounds back to encourage practice",
            "Introduce simple words that match the sounds (ba-ba → ball)",
            "Celebrate this milestone - it's a sign of healthy development!",
        ],
    },
    "vowel_play": {
        "label": "Vowel Play",
        "icon": "🎵",
        "description": "Extended vowel sounds and vocal experimentation",
        "age_range": (90, 270),
        "what_hearing": "Long, drawn-out vowel sounds like 'aaa', 'ooo', or 'eee' with varying pitch",
        "what_means": "Your baby is exploring their voice and learning to control pitch and volume.",
        "what_try": [
            "Imitate the sounds to show you're listening",
            "Vary your pitch when responding to encourage experimentation",
            "Sing simple songs to model melodic patterns",
        ],
    },
    "responsive": {
        "label": "Responsive Babbling",
        "icon": "💬",
        "description": "Babbling in response to adult speech (turn-taking)",
        "age_range": (180, 548),
        "what_hearing": "Babbling that occurs after you speak, with pauses for your response",
        "what_means": "Your baby is learning the rhythm of conversation and practicing turn-taking.",
        "what_try": [
            "Wait for baby to finish before responding",
            "Respond as if having a real conversation",
            "Ask simple questions and wait for 'answers'",
        ],
    },
    "proto_word": {
        "label": "Proto-Words",
        "icon": "🗣️",
        "description": "Consistent sound patterns used with specific meaning",
        "age_range": (270, 548),
        "what_hearing": "Specific sounds your baby uses consistently for the same object or action",
        "what_means": "Your baby is creating their own 'words' before learning conventional ones. This shows intentional communication.",
        "what_try": [
            "Respond to proto-words as if they're real words",
            "Model the correct word while acknowledging their attempt",
            "Keep track of proto-words to monitor vocabulary development",
        ],
    },
}


def analyze_babble(
    sound_features: Dict[str, Any],
    age_days: int,
    transcript: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Analyze babbling patterns from acoustic features.
    
    Uses acoustic features to classify babble type and provide developmental context.
    
    Args:
        sound_features: Acoustic features dict from feature extraction
        age_days: Baby's age in days
        transcript: Optional transcript result (for proto-word detection)
    
    Returns:
        {
            "babble_type": "canonical",
            "confidence": 0.75,
            "babble_label": "Canonical Babbling",
            "babble_icon": "👶",
            "age_appropriate": True,
            "what_hearing": "...",
            "what_means": "...",
            "what_try": [...],
            "babble_features": {
                "syllable_rate": 3.5,
                "repetition_score": 0.82,
                "vowel_duration": 0.45,
                "consonant_clarity": 0.68,
            },
        }
    """
    # Extract babble-specific features
    babble_features = _extract_babble_features(sound_features, transcript)
    
    # Classify babble type
    babble_type, confidence = _classify_babble_type(babble_features, age_days)
    
    # Get babble type info
    babble_info = BABBLE_TYPES.get(babble_type, BABBLE_TYPES["vowel_play"])
    
    # Check age appropriateness
    age_range = babble_info.get("age_range", (0, 730))
    age_appropriate = age_range[0] <= age_days <= age_range[1]
    
    return {
        "babble_type": babble_type,
        "confidence": round(confidence, 3),
        "babble_label": babble_info.get("label", "Babbling"),
        "babble_icon": babble_info.get("icon", "👶"),
        "age_appropriate": age_appropriate,
        "what_hearing": babble_info.get("what_hearing", ""),
        "what_means": babble_info.get("what_means", ""),
        "what_try": babble_info.get("what_try", []),
        "babble_features": babble_features,
        "description": babble_info.get("description", ""),
    }


def _extract_babble_features(
    sound_features: Dict[str, Any],
    transcript: Optional[Dict] = None,
) -> Dict[str, float]:
    """
    Extract babble-specific features from acoustic features.
    
    Returns:
        {
            "syllable_rate": 3.5,        # Syllables per second
            "repetition_score": 0.82,    # How repetitive (0-1)
            "vowel_duration": 0.45,      # Average vowel duration
            "consonant_clarity": 0.68,   # Consonant clarity (0-1)
            "pitch_variation": 0.35,     # Pitch variability
            "turn_taking_score": 0.60,   # Turn-taking likelihood (0-1)
        }
    """
    # Syllable rate (from existing feature)
    syllable_rate = float(sound_features.get("syllable_rate", 0))
    
    # Repetition score (from energy variability - low variability = repetitive)
    energy_var = float(sound_features.get("energy_variability", 0.5))
    repetition_score = max(0, 1.0 - energy_var)
    
    # Vowel duration (estimate from voiced fraction and duration)
    voiced_fraction = float(sound_features.get("voiced_fraction", 0.5))
    duration_s = float(sound_features.get("duration_s", 1.0))
    vowel_duration = (voiced_fraction * duration_s) / max(syllable_rate, 1)
    
    # Consonant clarity (from spectral centroid and zcr)
    spectral_centroid = float(sound_features.get("spectral_centroid", 2000))
    zcr = float(sound_features.get("zcr", 0.05))
    # Higher spectral centroid + moderate zcr = clearer consonants
    consonant_clarity = min(1.0, (spectral_centroid / 3000) * (zcr / 0.1))
    
    # Pitch variation (from f0_instability)
    f0_instability = float(sound_features.get("f0_instability", 0.2))
    pitch_variation = min(1.0, f0_instability)
    
    # Turn-taking score (estimate from pauses - not directly available)
    # Use energy variability as proxy (high variability = more pauses = turn-taking)
    turn_taking_score = min(1.0, energy_var * 2)
    
    return {
        "syllable_rate": round(syllable_rate, 2),
        "repetition_score": round(repetition_score, 3),
        "vowel_duration": round(vowel_duration, 3),
        "consonant_clarity": round(consonant_clarity, 3),
        "pitch_variation": round(pitch_variation, 3),
        "turn_taking_score": round(turn_taking_score, 3),
    }


def _classify_babble_type(
    babble_features: Dict[str, float],
    age_days: int,
) -> tuple:
    """
    Classify babble type from features.
    
    Returns:
        (babble_type, confidence) tuple
    """
    syllable_rate = babble_features.get("syllable_rate", 0)
    repetition_score = babble_features.get("repetition_score", 0)
    vowel_duration = babble_features.get("vowel_duration", 0)
    consonant_clarity = babble_features.get("consonant_clarity", 0)
    turn_taking_score = babble_features.get("turn_taking_score", 0)
    
    scores = {}
    
    # Canonical babbling: High syllable rate + high repetition + clear consonants
    if 180 <= age_days <= 365:
        canonical_score = (
            0.4 * min(1.0, syllable_rate / 4.0) +
            0.4 * repetition_score +
            0.2 * consonant_clarity
        )
        scores["canonical"] = canonical_score
    
    # Vowel play: Long vowel duration + low syllable rate
    if 90 <= age_days <= 270:
        vowel_play_score = (
            0.5 * min(1.0, vowel_duration / 0.5) +
            0.3 * (1.0 - min(1.0, syllable_rate / 3.0)) +
            0.2 * (1.0 - consonant_clarity)
        )
        scores["vowel_play"] = vowel_play_score
    
    # Responsive babbling: High turn-taking score
    if 180 <= age_days <= 548:
        responsive_score = (
            0.6 * turn_taking_score +
            0.2 * min(1.0, syllable_rate / 3.0) +
            0.2 * consonant_clarity
        )
        scores["responsive"] = responsive_score
    
    # Proto-words: Moderate syllable rate + high consonant clarity + low repetition
    if 270 <= age_days <= 548:
        proto_word_score = (
            0.4 * consonant_clarity +
            0.3 * (1.0 - repetition_score) +
            0.3 * min(1.0, syllable_rate / 2.5)
        )
        scores["proto_word"] = proto_word_score
    
    # Default to vowel_play if no scores
    if not scores:
        scores["vowel_play"] = 0.5
    
    # Get highest scoring type
    babble_type = max(scores.items(), key=lambda x: x[1])
    
    return babble_type[0], babble_type[1]


def get_babble_developmental_context(
    babble_type: str,
    age_days: int,
) -> Dict[str, Any]:
    """
    Get developmental context for detected babble type.
    
    Args:
        babble_type: Detected babble type
        age_days: Baby's age in days
    
    Returns:
        {
            "is_age_appropriate": True,
            "developmental_stage": "on_track",
            "milestone_context": "...",
            "next_milestone": "...",
        }
    """
    babble_info = BABBLE_TYPES.get(babble_type, {})
    age_range = babble_info.get("age_range", (0, 730))
    
    is_age_appropriate = age_range[0] <= age_days <= age_range[1]
    
    # Determine developmental stage
    if age_days < age_range[0]:
        developmental_stage = "advanced"
        milestone_context = f"Your baby is showing {babble_info.get('label', 'babbling')} earlier than typical. This is a positive sign!"
    elif age_days > age_range[1]:
        developmental_stage = "delayed"
        milestone_context = f"Your baby is still showing {babble_info.get('label', 'babbling')}. Consider discussing with your pediatrician."
    else:
        developmental_stage = "on_track"
        milestone_context = f"Your baby's {babble_info.get('label', 'babbling')} is right on track for their age."
    
    # Next milestone
    next_milestones = {
        "vowel_play": "canonical babbling (repetitive syllables)",
        "canonical": "proto-words (consistent sound-meaning pairs)",
        "responsive": "proto-words and first words",
        "proto_word": "first true words",
    }
    next_milestone = next_milestones.get(babble_type, "continued language development")
    
    return {
        "is_age_appropriate": is_age_appropriate,
        "developmental_stage": developmental_stage,
        "milestone_context": milestone_context,
        "next_milestone": next_milestone,
        "expected_age_range": f"{age_range[0]}-{age_range[1]} days",
    }


def compare_babble_to_population(
    babble_features: Dict[str, float],
    age_days: int,
    population_context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Compare baby's babble features to population norms.
    
    Args:
        babble_features: Extracted babble features
        age_days: Baby's age in days
        population_context: Optional population context from atlas
    
    Returns:
        {
            "syllable_rate_percentile": 65,
            "consonant_clarity_percentile": 72,
            "interpretation": "Your baby's babbling is developing well",
        }
    """
    if not population_context or not population_context.get("has_population_data"):
        return {"has_comparison": False}
    
    pop_features = population_context.get("features", {})
    
    comparison = {}
    
    # Compare syllable rate
    if "syllable_rate" in pop_features:
        syllable_percentile = pop_features["syllable_rate"].get("percentile", 50)
        comparison["syllable_rate_percentile"] = syllable_percentile
    
    # Interpretation
    if comparison:
        avg_percentile = np.mean(list(comparison.values()))
        if avg_percentile > 75:
            interpretation = "Your baby's babbling is developing very well"
        elif avg_percentile > 50:
            interpretation = "Your baby's babbling is developing typically"
        elif avg_percentile > 25:
            interpretation = "Your baby's babbling is developing at their own pace"
        else:
            interpretation = "Consider discussing your baby's babbling with your pediatrician"
        
        comparison["interpretation"] = interpretation
        comparison["has_comparison"] = True
    else:
        comparison["has_comparison"] = False
    
    return comparison
