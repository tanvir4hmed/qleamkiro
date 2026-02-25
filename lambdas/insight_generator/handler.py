"""
Qleam — Insight Generator Lambda
Translates system state into structured, non-diagnostic parent guidance.

Phase 4 — Three-Source Evidence Model:
- 60% Acoustic signal    — real-time audio features (summary + Phase 3 rich features)
- 15% Research priors    — developmental stage norms + session context (feeding, health)
- 25% Feedback history   — parent reinforcement over time
  → Acoustic is ground truth; feedback personalises without dominating early sessions.
- Insight now includes evidence breakdown for transparency.

Trigger: Step Function third state
Input:  { child_id, session_id, cluster_id }
Output: Structured insight JSON stored in Session table
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    BEDROCK_MODEL_ID,
    CHILD_PROFILE_TABLE,
    DISCLAIMER,
    INTENT_LABELS,
    POPULATION_MODEL_TABLE,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    USE_BEDROCK,
)
from normalization import normalize_probability_distribution
from evidence_model import determine_probable_intent_v2

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)
population_model_table = dynamodb.Table(POPULATION_MODEL_TABLE)


# =============================================================================
# DynamoDB Helpers
# =============================================================================

def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _float_to_decimal(obj: Any) -> Any:
    """Convert floats to Decimal for DynamoDB."""
    import math
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return obj
    if hasattr(obj, 'item'):
        try:
            obj = obj.item()
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return Decimal("0")
        if math.isinf(obj):
            return Decimal("0") if obj < 0 else Decimal("1")
        return Decimal(str(obj))
    if isinstance(obj, bool):
        return Decimal("1") if obj else Decimal("0")
    if isinstance(obj, str):
        try:
            return Decimal(obj)
        except Exception:
            return obj
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


# =============================================================================
# DynamoDB Fetchers
# =============================================================================

def get_session(session_id: str) -> Optional[Dict]:
    response = session_table.get_item(Key={"session_id": session_id})
    return _decimal_to_float(response.get("Item"))


def get_child_profile(child_id: str) -> Optional[Dict]:
    response = child_profile_table.get_item(Key={"child_id": child_id})
    return _decimal_to_float(response.get("Item"))


def get_cluster(cluster_id: str) -> Optional[Dict]:
    response = sound_cluster_table.get_item(Key={"cluster_id": cluster_id})
    return _decimal_to_float(response.get("Item"))


def get_semantic_bridge(cluster_id: str) -> Optional[Dict]:
    """Get the highest-confidence semantic bridge for a cluster."""
    response = semantic_bridge_table.query(
        IndexName="cluster_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("cluster_id").eq(cluster_id)
    )
    bridges = response.get("Items", [])
    if not bridges:
        return None
    return _decimal_to_float(max(bridges, key=lambda b: float(b.get("semantic_confidence_score", 0))))


def get_population_prior(developmental_stage: str) -> Optional[Dict[str, float]]:
    """
    Load the Phase 8 FL population prior for a given developmental stage.

    Returns the prior distribution if it exists AND is reliable
    (n_participants >= FL_MIN_PARTICIPANTS). Returns None otherwise,
    causing evidence_model to fall back to static literature priors.
    """
    try:
        response = population_model_table.get_item(
            Key={"stage": developmental_stage.upper()},
            ProjectionExpression="population_prior, n_participants, is_reliable",
        )
        item = _decimal_to_float(response.get("Item") or {})
        if not item:
            return None
        if not item.get("is_reliable"):
            logger.debug(f"Population prior for {developmental_stage} exists but not reliable — using literature priors")
            return None
        prior = item.get("population_prior")
        if prior and isinstance(prior, dict):
            logger.debug(f"Using FL population prior for stage={developmental_stage} n={item.get('n_participants')}")
            return prior
    except Exception as e:
        logger.warning(f"Failed to load population prior for {developmental_stage}: {e}")
    return None


# =============================================================================
# Rule-Based Insight Sections (used when Bedrock is off or fails)
# =============================================================================

INTENT_SECTIONS = {
    "hunger": {
        "what_i_hear": "Baby's sounds show a rhythmic, building intensity — a classic early hunger signal.",
        "what_it_means": "This rhythmic, escalating pattern often suggests hunger or a feeding need.",
        "what_to_try": [
            "Offer feeding and watch for rooting or hand-to-mouth movement",
            "Check when baby last fed — is it close to their usual interval?",
            "Try gentle tummy rubs to ease any digestive discomfort",
        ],
    },
    "connection": {
        "what_i_hear": "Baby's sounds are calm and flowing — gentle vocalizations typical of social engagement.",
        "what_it_means": "This calm, fluid pattern often appears when babies are seeking interaction and warmth.",
        "what_to_try": [
            "Make gentle eye contact and mirror baby's sounds back to them",
            "Talk or sing softly — babies love responsive back-and-forth",
            "Hold baby close and respond warmly to each vocalization",
        ],
    },
    "discomfort": {
        "what_i_hear": "Baby's sounds show high intensity with irregular, persistent bursts — often linked to physical discomfort.",
        "what_it_means": "This irregular, intense pattern may indicate physical discomfort — worth checking the basics.",
        "what_to_try": [
            "Check diaper, temperature, and clothing for anything irritating",
            "Try a different hold or position — sometimes that's all it takes",
            "Offer a gentle clockwise belly massage to ease gas",
        ],
    },
    "overstimulation": {
        "what_i_hear": "Baby's sounds are sustained and intense — a pattern sometimes seen with sensory overload.",
        "what_it_means": "Babies sometimes vocalize like this when their nervous system needs a break from stimulation.",
        "what_to_try": [
            "Move to a quieter, dimmer room and slow everything down",
            "Hold baby firmly against your chest for calming deep pressure",
            "Reduce eye contact briefly — even gentle gaze can be too much when overwhelmed",
        ],
    },
    "fatigue": {
        "what_i_hear": "Baby's sounds have a repetitive, fussing quality with short bursts — a common tired-baby pattern.",
        "what_it_means": "This fussy, repetitive pattern is commonly seen when babies are overtired and need rest.",
        "what_to_try": [
            "Create a calm sleep space — dim lights and reduce noise",
            "Start your soothing routine: swaddle, rock, or try white noise",
            "Watch for tired signs: rubbing eyes, yawning, or blank staring",
        ],
    },
    "exploration": {
        "what_i_hear": "Baby's sounds are varied and flowing — this vocal play is typical of an alert, curious state.",
        "what_it_means": "These varied sounds often mean baby is alert and actively engaging with their world.",
        "what_to_try": [
            "Mirror baby's sounds back gently — this is early proto-conversation",
            "Show interesting objects or faces at 20–30cm distance",
            "This is a great time for gentle, interactive play",
        ],
    },
    "unknown": {
        "what_i_hear": "Baby's sound pattern is still being learned — more sessions will build a clearer picture.",
        "what_it_means": "We're still learning this baby's unique patterns. Each session improves accuracy.",
        "what_to_try": [
            "Record more sessions to help build a reliable baseline",
            "Try the basics: check feeding, comfort, connection, and rest",
            "Trust your instincts — you know your baby best",
        ],
    },
}


def get_rule_based_sections(intent_key: str) -> Dict:
    """Return structured rule-based insight sections."""
    base = INTENT_SECTIONS.get(intent_key, INTENT_SECTIONS["unknown"])
    return {
        "what_i_hear": base["what_i_hear"],
        "what_it_means": base["what_it_means"],
        "what_to_try": list(base["what_to_try"]),
        "source": "rule-based",
    }


# =============================================================================
# LINGUISTIC Mode Insight (Phase 7)
# =============================================================================

LINGUISTIC_FALLBACK_INSIGHTS = {
    "FIRST_WORDS": {
        "what_i_hear": "Your child is producing clear, intentional word-like sounds with real communicative purpose.",
        "what_it_means": "Each session helps track their vocabulary growth. These are the building blocks of language.",
        "what_to_try": [
            "Respond to every word attempt — acknowledgement encourages more speech",
            "Name objects together during play to expand vocabulary",
            "Read simple picture books and point to objects as you name them",
        ],
    },
    "WORD_COMBINATIONS": {
        "what_i_hear": "Your child is linking sounds and words in multi-word patterns — a key leap in language.",
        "what_it_means": "Two-word combinations show the grammar system is developing. This is a major milestone.",
        "what_to_try": [
            "Expand what your child says — if they say 'more milk', respond 'yes, more cold milk'",
            "Ask open questions that need more than one word to answer",
            "Narrate everyday activities: 'We're washing the big red apple'",
        ],
    },
    "EARLY_SENTENCES": {
        "what_i_hear": "Your child is forming multi-word sentences with structure and intent.",
        "what_it_means": "Sentence formation at this stage reflects strong language development.",
        "what_to_try": [
            "Engage in back-and-forth conversation and give your child time to respond",
            "Model complete sentences in response to shorter ones they produce",
            "Introduce simple stories with cause and effect to build narrative thinking",
        ],
    },
}


def _generate_linguistic_insight_with_bedrock(
    developmental_stage: str,
    rich_features: dict,
) -> dict:
    """Generate language-development insight via Bedrock for LINGUISTIC mode sessions."""
    try:
        bedrock = boto3.client("bedrock-runtime")
        model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)

        syllable_rate = round(float(rich_features.get("syllable_rate", 0.0)), 2)
        pause_ratio = round(float(rich_features.get("pause_ratio", 0.5)), 2)
        f0_range = round(float(rich_features.get("f0_range", 0.0)), 1)
        hnr_db = round(float(rich_features.get("hnr_db", 0.0)), 1)
        cbr = round(float(rich_features.get("cbr_estimate", 0.0)), 3)
        stage_label = developmental_stage.replace("_", " ").title()

        prompt = f"""You are a warm, supportive language development analyst helping parents understand their child's speech progress.

CHILD'S DEVELOPMENTAL STAGE: {stage_label}

ACOUSTIC MEASUREMENTS FROM THIS SESSION:
- Syllable rate: {syllable_rate} syllables/second
- Pause ratio: {pause_ratio} (proportion of silence — higher = more pauses between utterances)
- Pitch range: {f0_range} Hz (wider = more expressive prosody)
- Voice clarity (HNR): {hnr_db} dB (higher = cleaner, more resonant speech)
- Canonical babbling ratio: {cbr} (residual babble — lower at this stage is normal)

Return ONLY a JSON object with exactly these three fields:
{{
  "what_i_hear": "1-2 sentences describing what the acoustic measurements show about this child's current speech. Focus on positive signals. Plain, warm language.",
  "what_it_means": "1-2 sentences about what this means for their language development. Use 'suggests', 'indicates', 'is consistent with'. Never diagnose.",
  "what_to_try": ["specific actionable language activity 1", "specific actionable language activity 2", "specific actionable language activity 3"]
}}

Guidelines:
- Write for a parent who wants practical language development support, not medical information
- Focus on language development, not cry interpretation
- Keep each sentence under 25 words
- The 3 activities must be immediately doable at home
- Return ONLY the JSON object"""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 450,
            "temperature": 0.35,
            "messages": [{"role": "user", "content": prompt}],
        })

        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        raw_text = result["content"][0]["text"]

        sections = _parse_bedrock_json(raw_text)
        if sections and "what_i_hear" in sections:
            if isinstance(sections.get("what_to_try"), str):
                sections["what_to_try"] = [sections["what_to_try"]]
            return {
                "what_i_hear": sections.get("what_i_hear", ""),
                "what_it_means": sections.get("what_it_means", ""),
                "what_to_try": sections.get("what_to_try", [])[:3],
                "source": "bedrock",
            }

        raise ValueError(f"Could not parse Bedrock JSON: {raw_text[:200]}")

    except Exception as e:
        logger.warning(f"Bedrock failed for LINGUISTIC insight, using rule-based: {e}")
        return None


def _generate_linguistic_insight(
    session_id: str,
    child_id: str,
    developmental_stage: str,
    rich_features: dict,
    feature_scores: Optional[Dict] = None,
) -> dict:
    """
    Generate and store language-development insight for LINGUISTIC-mode sessions.
    Skips intent classification — focuses on language metrics instead.
    """
    use_bedrock = os.environ.get("USE_BEDROCK", str(USE_BEDROCK)).lower() == "true"

    insight_sections = None
    if use_bedrock:
        insight_sections = _generate_linguistic_insight_with_bedrock(developmental_stage, rich_features)

    if not insight_sections:
        # Rule-based fallback — stage-based
        fallback_key = developmental_stage if developmental_stage in LINGUISTIC_FALLBACK_INSIGHTS else "WORD_COMBINATIONS"
        base = LINGUISTIC_FALLBACK_INSIGHTS[fallback_key]
        insight_sections = {
            "what_i_hear": base["what_i_hear"],
            "what_it_means": base["what_it_means"],
            "what_to_try": list(base["what_to_try"]),
            "source": "rule-based",
        }

    # Build observed_pattern from feature_scores so the acoustic chart can render
    fs = feature_scores or {}
    observed_pattern = {
        "emotional_intensity": round(float(fs.get("emotional_intensity", 0)), 3),
        "rhythm":              round(float(fs.get("rhythm", 0)), 3),
        "repetition":          round(float(fs.get("repetition", 0)), 3),
        "expressive_flow":     round(float(fs.get("expressive_flow", 0)), 3),
    }

    insight = {
        "insight_type": "language_development",
        "developmental_stage": developmental_stage,
        "observed_pattern": observed_pattern,
        "insight_sections": insight_sections,
        "suggested_response": "  |  ".join(insight_sections.get("what_to_try", [])),
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    save_insight_to_session(session_id, insight)

    logger.info(
        f"LINGUISTIC insight generated for session {session_id}: "
        f"stage={developmental_stage} source={insight_sections['source']}"
    )
    return {
        "status": "insight_generated",
        "session_id": session_id,
        "insight": insight,
    }


# =============================================================================
# Acoustic Feature-Based Intent Classifier
# =============================================================================

def classify_intent_from_features(feature_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Pure acoustic feature-based intent classification.
    Does NOT use parent feedback — derived entirely from audio signal.

    Feature semantics (all 0.0-1.0):
    - emotional_intensity: pitch variance + energy variance (0=calm, 1=distressed)
    - rhythm: regularity of sound bursts (1=very rhythmic, 0=irregular)
    - repetition: MFCC self-similarity (1=same sounds repeated, 0=varied)
    - expressive_flow: vocalization continuity (1=long/continuous, 0=short bursts)

    Pattern logic derived from infant vocalization research:
    - Hunger: rhythmic escalation with building intensity
    - Discomfort: intense, arrhythmic, persistent
    - Connection: calm, flowing, low intensity (babbling/cooing)
    - Fatigue: moderate intensity, repetitive fussing, fragmented
    - Overstimulation: high sustained intensity, irregular
    - Exploration: varied, calm, flowing
    """
    ei = feature_scores.get("emotional_intensity", 0.5)
    rh = feature_scores.get("rhythm", 0.5)
    rep = feature_scores.get("repetition", 0.5)
    ef = feature_scores.get("expressive_flow", 0.5)

    # Hunger: intense + rhythmic (feeding cry = rhythmic escalation)
    hunger = ei * 0.50 + rh * 0.40 + rep * 0.10

    # Discomfort: very intense + arrhythmic + persistent repetition
    discomfort = ei * 0.60 + (1.0 - rh) * 0.25 + rep * 0.15

    # Connection/Social: calm + flowing + slightly rhythmic (cooing, babbling)
    connection = (1.0 - ei) * 0.45 + ef * 0.45 + rh * 0.10

    # Fatigue: moderate intensity + repetitive + fragmented flow (fussing)
    # Moderate intensity peaks at ei=0.45 (not too calm, not too distressed)
    moderate_ei = max(0.0, 1.0 - abs(ei - 0.45) * 2.2)
    fatigue = rep * 0.35 + (1.0 - ef) * 0.35 + moderate_ei * 0.30

    # Overstimulation: high intensity + irregular + sustained cry
    overstimulation = ei * 0.50 + (1.0 - rh) * 0.30 + ef * 0.20

    # Exploration: calm + varied sounds + flowing
    exploration = (1.0 - ei) * 0.35 + (1.0 - rep) * 0.35 + ef * 0.30

    raw = {
        "hunger": max(0.0, hunger),
        "discomfort": max(0.0, discomfort),
        "connection": max(0.0, connection),
        "fatigue": max(0.0, fatigue),
        "overstimulation": max(0.0, overstimulation),
        "exploration": max(0.0, exploration),
    }

    return normalize_probability_distribution(raw)


def describe_features_in_words(feature_scores: Dict[str, float], deviation_level: str) -> Dict[str, str]:
    """Translate numeric feature scores into warm, parent-readable descriptions."""
    ei = feature_scores.get("emotional_intensity", 0.5)
    rh = feature_scores.get("rhythm", 0.5)
    rep = feature_scores.get("repetition", 0.5)
    ef = feature_scores.get("expressive_flow", 0.5)

    if ei < 0.30:
        tone = "calm and settled"
    elif ei < 0.55:
        tone = "mildly expressive"
    elif ei < 0.75:
        tone = "noticeably expressive"
    else:
        tone = "highly intense"

    if rh > 0.65:
        pattern = "very rhythmic and regular"
    elif rh > 0.40:
        pattern = "somewhat rhythmic"
    else:
        pattern = "irregular and varied"

    if rep > 0.65:
        repetition = "repeating the same sounds"
    elif rep > 0.40:
        repetition = "some repeated patterns"
    else:
        repetition = "varied, changing sounds"

    if ef > 0.60:
        flow = "long, continuous vocalizations"
    elif ef > 0.35:
        flow = "moderate length with some pauses"
    else:
        flow = "short bursts with pauses"

    baseline_map = {
        "none": "within baby's normal baseline",
        "low": "slightly different from usual",
        "moderate": "noticeably different from usual",
        "high": "significantly different from usual",
    }

    return {
        "emotional_tone": tone,
        "sound_pattern": pattern,
        "repetition": repetition,
        "continuity": flow,
        "vs_baseline": baseline_map.get(deviation_level, "within normal range"),
    }


# =============================================================================
# [Phase 4] Three-Source Evidence Model — replaces 70/30 two-source model
# =============================================================================

def determine_cluster_stability(cluster: Dict) -> str:
    """Determine cluster stability label."""
    frequency_count = cluster.get("frequency_count", 1)
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    if frequency_count >= 10 and reinforcement_weight >= 0.7:
        return "stable"
    elif frequency_count >= 5 or reinforcement_weight >= 0.5:
        return "emerging"
    else:
        return "forming"


# =============================================================================
# Bedrock Insight Generation
# =============================================================================

def _parse_bedrock_json(text: str) -> Optional[Dict]:
    """Robustly parse JSON from Bedrock response."""
    text = text.strip()

    # Strip code block markers
    if "```" in text:
        parts = re.split(r'```(?:json)?', text)
        for part in parts:
            part = part.strip().rstrip('`').strip()
            if part.startswith('{'):
                text = part
                break

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract first {...} object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def generate_insight_with_bedrock(
    cluster: Dict,
    probable_intent: Dict,
    feature_narrative: Dict,
    semantic_bridge: Optional[Dict],
    developmental_stage: str = "UNKNOWN",
    session_context: Optional[Dict] = None,
    child_name: str = "",
) -> Dict:
    """
    Generate structured 3-section parent insight using Amazon Bedrock Claude.
    Falls back to rule-based sections if Bedrock fails.
    """
    try:
        bedrock = boto3.client("bedrock-runtime")
        model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)

        cluster_count = cluster.get("frequency_count", 1)
        stability = determine_cluster_stability(cluster)
        confidence_pct = int(probable_intent["confidence"] * 100)
        intent_label = probable_intent["label"]

        alt_intents = probable_intent.get("top_intents", [])[1:3]
        alt_text = "\n".join(
            [f"- {i['label']} ({int(i['weight'] * 100)}%)" for i in alt_intents]
        ) if alt_intents else "- No strong alternatives"

        word_note = ""
        if semantic_bridge:
            word_note = (
                f"\n- Baby has said '{semantic_bridge.get('word_token')}' "
                f"near this pattern {semantic_bridge.get('co_occurrence_count', 1)} time(s)"
            )

        # Context note for Bedrock
        ctx_notes = []
        if session_context:
            fma = session_context.get("feeding_minutes_ago")
            if isinstance(fma, (int, float)):
                ctx_notes.append(f"last feeding approximately {int(fma)} minutes ago")
            health = session_context.get("health_state", "")
            if health and health not in ("unknown", ""):
                ctx_notes.append(f"health state: {health}")
        context_note = (
            "\nSESSION CONTEXT:\n- " + "\n- ".join(ctx_notes)
            if ctx_notes else ""
        )

        stage_label = developmental_stage.replace("_", " ").title()
        name_line = f"\nBABY'S NAME: {child_name}" if child_name else ""

        prompt = f"""You are Qleam, a supportive baby communication assistant helping parents understand their infant's sounds.

AUDIO ANALYSIS FROM THIS SESSION:
- Emotional tone: {feature_narrative['emotional_tone']}
- Sound pattern: {feature_narrative['sound_pattern']}
- Repetition: {feature_narrative['repetition']}
- Continuity: {feature_narrative['continuity']}
- Compared to baby's usual: {feature_narrative['vs_baseline']}

BABY'S DEVELOPMENTAL STAGE: {stage_label}{name_line}{context_note}

PATTERN HISTORY:
- This sound pattern has been recorded {cluster_count} time(s) for this baby
- Pattern maturity: {stability} (forming -> emerging -> stable)
- Primary signal: {intent_label} ({confidence_pct}% confidence){word_note}

Alternative possibilities:
{alt_text}

Return ONLY a JSON object with exactly these three fields:
{{
  "what_i_hear": "1-2 sentences describing what the audio shows. Mention specific sound characteristics. Warm and plain language.",
  "what_it_means": "1-2 sentences about what this often suggests. Use uncertain language: 'often suggests', 'may indicate', 'many babies do this when'. Never diagnose.",
  "what_to_try": ["specific actionable step 1", "specific actionable step 2", "specific actionable step 3"]
}}

Guidelines:
- Write for a new parent who needs clear, warm, reassuring support
- Never use medical or clinical terms
- Keep each sentence under 20 words
- Each action step: max 10 words, start with a verb, immediately doable
- If baby's name is provided, use it naturally 1-2 times (e.g., "Emma's sounds suggest...")
- If confidence is low or pattern is still forming, acknowledge gently
- Return ONLY the JSON object, no other text"""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 450,
            "temperature": 0.35,
            "messages": [{"role": "user", "content": prompt}]
        })

        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        raw_text = result["content"][0]["text"]

        sections = _parse_bedrock_json(raw_text)
        if sections and "what_i_hear" in sections:
            if isinstance(sections.get("what_to_try"), str):
                sections["what_to_try"] = [sections["what_to_try"]]
            return {
                "what_i_hear": sections.get("what_i_hear", ""),
                "what_it_means": sections.get("what_it_means", ""),
                "what_to_try": sections.get("what_to_try", [])[:3],
                "source": "bedrock",
            }

        raise ValueError(f"Could not parse Bedrock JSON: {raw_text[:200]}")

    except Exception as e:
        logger.warning(f"Bedrock failed, using rule-based: {e}")
        return get_rule_based_sections(probable_intent.get("key", "unknown"))


# =============================================================================
# Build Insight
# =============================================================================

def build_insight(
    session: Dict,
    profile: Dict,
    cluster: Dict,
    semantic_bridge: Optional[Dict],
) -> Dict:
    """Build the enhanced structured insight output (Phase 4 — Three-Source Evidence Model)."""

    feature_scores  = session.get("feature_scores", {})
    deviation_level = session.get("deviation_level", "none")
    deviation_score = session.get("deviation_score", 0.0)

    # Phase 3 data stored in session by feature_extraction Lambda
    rich_features     = session.get("rich_features") or {}
    session_context   = session.get("session_context") or {}

    # Developmental stage: prefer session-level (recorded at analysis time), fall back to profile
    developmental_stage = (
        session.get("developmental_stage")
        or profile.get("developmental_stage")
        or "UNKNOWN"
    )

    # Phase 4: pull session count, trust scores, and baby name from child profile
    session_count        = int(profile.get("session_count") or 0)
    parent_trust_score   = float(profile.get("parent_trust_score") or 0.5)
    context_reliability  = float(profile.get("context_reliability") or 0.8)
    child_name           = str(profile.get("name") or "")

    # 1. Feature narrative — always computed from audio data, no feedback involved
    feature_narrative = describe_features_in_words(feature_scores, deviation_level)

    # 2. [Phase 4] Three-source evidence model: 60% acoustic + 15% research + 25% feedback
    #    [Phase 8] Research prior replaced by FL population prior when available + reliable
    #    Confidence capped by session count; feedback weight scaled by parent trust score (FRS)
    population_prior = get_population_prior(developmental_stage)
    probable_intent = determine_probable_intent_v2(
        cluster=cluster,
        feature_scores=feature_scores,
        rich_features=rich_features,
        developmental_stage=developmental_stage,
        session_context=session_context,
        session_count=session_count,
        parent_trust_score=parent_trust_score,
        context_reliability=context_reliability,
        population_prior=population_prior,
    )
    cluster_stability = determine_cluster_stability(cluster)

    # 3. Generate insight sections (Bedrock or rule-based)
    use_bedrock = os.environ.get("USE_BEDROCK", str(USE_BEDROCK)).lower() == "true"
    if use_bedrock:
        insight_sections = generate_insight_with_bedrock(
            cluster, probable_intent, feature_narrative, semantic_bridge,
            developmental_stage=developmental_stage,
            session_context=session_context,
            child_name=child_name,
        )
    else:
        insight_sections = get_rule_based_sections(probable_intent["key"])

    # 4. Semantic alignment (if word detected)
    semantic_alignment = None
    if semantic_bridge:
        semantic_alignment = {
            "word_detected": semantic_bridge.get("word_token"),
            "alignment_confidence": round(float(semantic_bridge.get("semantic_confidence_score", 0)), 3),
            "co_occurrence_count": semantic_bridge.get("co_occurrence_count", 0),
        }

    insight = {
        "observed_pattern": {
            "emotional_intensity": round(feature_scores.get("emotional_intensity", 0), 3),
            "rhythm": round(feature_scores.get("rhythm", 0), 3),
            "repetition": round(feature_scores.get("repetition", 0), 3),
            "expressive_flow": round(feature_scores.get("expressive_flow", 0), 3),
            "deviation": deviation_level,
            "deviation_score": round(deviation_score, 3),
            "cluster_stability": cluster_stability,
            "cluster_frequency": cluster.get("frequency_count", 1),
        },
        "feature_narrative": feature_narrative,
        "probable_intent": probable_intent,
        "semantic_alignment": semantic_alignment,
        "insight_sections": insight_sections,
        # Backward-compat flat text
        "suggested_response": "  |  ".join(insight_sections.get("what_to_try", [])),
        "readiness_score": round(profile.get("readiness_score", 0.5), 3),
        "language_maturity_level": profile.get("language_maturity_level", "pre-linguistic"),
        "developmental_stage": developmental_stage,
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return insight


# =============================================================================
# Save Insight
# =============================================================================

def _build_rejection_insight(session: Dict, reason: str = "quality") -> Dict:
    """
    Lightweight insight returned when recording cannot be analysed.

    reason values:
      "quality"  — no signal / no vocal activity / too short
      "adult"    — biological validation flagged adult voice (mimicry suspected)
    """
    if reason == "adult":
        what_i_hear = "This recording contains adult speech rather than baby sounds."
        what_it_means = (
            "The voice patterns match an adult, not a baby. "
            "Make sure to record while your baby is vocalising, not while you're talking."
        )
        what_to_try = [
            "Wait for baby to make sounds, then start recording",
            "Hold the phone 20–30 cm from baby's face",
            "Stay quiet yourself while recording",
        ]
        label = "Adult voice detected"
    else:
        what_i_hear = "We couldn't detect clear baby sounds in this recording."
        what_it_means = (
            "This usually means the recording was too quiet, too short, or "
            "captured background noise rather than your baby's voice."
        )
        what_to_try = [
            "Hold the phone 20–30 cm from your baby's mouth",
            "Record somewhere quieter if possible",
            "Try again when baby is actively making sounds",
        ]
        label = "No baby sounds detected"

    return {
        "probable_intent": {
            "key": "unknown",
            "label": label,
            "confidence": 0.0,
            "confidence_tier": "low",
        },
        "insight_sections": {
            "what_i_hear": what_i_hear,
            "what_it_means": what_it_means,
            "what_to_try": what_to_try,
            "source": "quality-rejection",
        },
        # No developmental_stage — don't show a misleading stage label on rejected sessions
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_insight_to_session(session_id: str, insight: Dict, efp: Optional[Dict] = None):
    """Save generated insight (and EFP) to session record.

    EFP (Expected Feedback Profile) is stored separately on the session so the
    feedback_processor can retrieve it without parsing the full insight blob.
    """
    update_expr = "SET insight = :ins, insight_generated_at = :iga"
    expr_values: Dict = {
        ":ins": _float_to_decimal(insight),
        ":iga": datetime.now(timezone.utc).isoformat(),
    }
    if efp:
        update_expr += ", efp = :efp"
        expr_values[":efp"] = _float_to_decimal(efp)

    session_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


# =============================================================================
# Lambda Handler
# =============================================================================

def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Insight Generator Lambda handler.

    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "cluster_id": str
        }
    """
    logger.info(f"Insight generator started for session {event.get('session_id')}")

    child_id = event["child_id"]
    session_id = event["session_id"]
    cluster_id = event["cluster_id"]

    # 1. Fetch all required data
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    # 1a. Quality gate check — reject recordings with no vocal content
    # Only truly critical issues block analysis.
    # too_silent alone is NOT critical — 1s of sound in a 5s recording is still analysable.
    _CRITICAL_GATE_ISSUES = ("no_signal", "no_vocal_activity_detected", "too_short:")
    quality_gate = session.get("quality_gate", {})
    gate_issues = quality_gate.get("issues", [])
    critical_issues = [
        i for i in gate_issues
        if any(i.startswith(p) for p in _CRITICAL_GATE_ISSUES)
    ]
    if critical_issues and not quality_gate.get("passed", True):
        logger.warning(
            f"Quality gate rejection for session {session_id}: {critical_issues}"
        )
        rejection_insight = _build_rejection_insight(session, reason="quality")
        save_insight_to_session(session_id, rejection_insight)
        return {
            "status": "insight_generated",
            "session_id": session_id,
            "insight": rejection_insight,
        }

    # 1b. Adult/mimicry check — reject when biological validation detects adult voice
    biological = session.get("biological", {})
    if biological.get("mimicry_suspected") is True:
        logger.warning(
            f"Adult voice detected for session {session_id}: "
            f"vtl={biological.get('vtl_cm')}cm f0={biological.get('f0_hz')}Hz"
        )
        rejection_insight = _build_rejection_insight(session, reason="adult")
        save_insight_to_session(session_id, rejection_insight)
        return {
            "status": "insight_generated",
            "session_id": session_id,
            "insight": rejection_insight,
        }

    # Branch: LINGUISTIC mode sessions get language-development insight
    developmental_mode = session.get("developmental_mode", "")
    if developmental_mode == "LINGUISTIC":
        developmental_stage = session.get("developmental_stage", "WORD_COMBINATIONS")
        rich_features = session.get("rich_features", {})
        feature_scores = session.get("feature_scores", {})
        return _generate_linguistic_insight(
            session_id, child_id, developmental_stage, rich_features, feature_scores
        )

    profile = get_child_profile(child_id)
    if not profile:
        raise ValueError(f"Child profile {child_id} not found")

    cluster = get_cluster(cluster_id)
    if not cluster:
        raise ValueError(f"Cluster {cluster_id} not found")

    semantic_bridge = get_semantic_bridge(cluster_id)

    # 2. Build enhanced insight
    insight = build_insight(session, profile, cluster, semantic_bridge)

    # 3. Extract EFP (Expected Feedback Profile) from insight for delta scoring later
    efp = insight.get("probable_intent", {}).get("evidence", {}).get("blended")

    # 4. Save insight + EFP to session
    save_insight_to_session(session_id, insight, efp=efp)

    logger.info(
        f"Insight generated for session {session_id}: "
        f"intent={insight['probable_intent']['label']} "
        f"confidence={insight['probable_intent']['confidence']:.2%} "
        f"source={insight['insight_sections']['source']}"
    )

    return {
        "status": "insight_generated",
        "session_id": session_id,
        "insight": insight,
    }
