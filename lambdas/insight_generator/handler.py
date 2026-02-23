"""
Qleam — Insight Generator Lambda
Translates system state into structured, non-diagnostic parent guidance.

Enhancement v2:
- Acoustic-first intent classification (70% audio signal, 30% feedback history)
  → Parent feedback fine-tunes over time but cannot override the audio data
- Structured Bedrock insight with 3 clear sections parents can act on
- Feature narrative: translate scores into plain-English audio descriptions
- Top-3 intent transparency for parent awareness

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
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    USE_BEDROCK,
)
from normalization import normalize_probability_distribution

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)


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
# Hybrid Intent Determination: 70% acoustic + 30% feedback history
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


def determine_probable_intent(cluster: Dict, feature_scores: Dict) -> Dict:
    """
    Hybrid intent determination: 70% acoustic features + 30% feedback history.

    The acoustic signal is the primary truth source — it's derived directly from
    the audio recording and is immune to incorrect parent feedback.
    Parent feedback (via reinforcement_engine) fine-tunes over many sessions
    but contributes only 30% so a wrong single feedback doesn't mislead results.
    """
    ACOUSTIC_WEIGHT = 0.70
    FEEDBACK_WEIGHT = 0.30

    # Primary: acoustic classification from this session's audio
    acoustic_intents = classify_intent_from_features(feature_scores)

    # Secondary: learned intent distribution from parent feedback history
    feedback_intents = cluster.get("probable_intents", {})

    # Blend both distributions
    all_keys = set(acoustic_intents.keys()) | set(feedback_intents.keys())
    blended = {}
    for key in all_keys:
        a = acoustic_intents.get(key, 0.0)
        f = feedback_intents.get(key, 0.0)
        blended[key] = ACOUSTIC_WEIGHT * a + FEEDBACK_WEIGHT * f

    blended = normalize_probability_distribution(blended)

    best_key = max(blended, key=blended.get)
    best_weight = blended[best_key]

    # Confidence grows with pattern history and semantic alignment
    frequency_count = cluster.get("frequency_count", 1)
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    semantic_alignment = cluster.get("semantic_alignment_score", 0.0)

    frequency_factor = min(frequency_count / 10.0, 1.0)
    semantic_factor = 1.0 + (semantic_alignment * 0.2)

    # Confidence: acoustic signal strength x history factor
    confidence = best_weight * (0.55 + reinforcement_weight * 0.25 * frequency_factor) * semantic_factor
    confidence = min(confidence, 0.92)  # Never claim certainty

    label = INTENT_LABELS.get(best_key, best_key.replace("_", " ").title())

    # Top 3 intents for transparency
    top_intents = sorted(blended.items(), key=lambda x: -x[1])[:3]

    return {
        "label": label,
        "key": best_key,
        "confidence": round(confidence, 3),
        "top_intents": [
            {
                "key": k,
                "label": INTENT_LABELS.get(k, k.replace("_", " ").title()),
                "weight": round(v, 3),
            }
            for k, v in top_intents
        ],
    }


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

        prompt = f"""You are Qleam, a supportive baby communication assistant helping parents understand their infant's sounds.

AUDIO ANALYSIS FROM THIS SESSION:
- Emotional tone: {feature_narrative['emotional_tone']}
- Sound pattern: {feature_narrative['sound_pattern']}
- Repetition: {feature_narrative['repetition']}
- Continuity: {feature_narrative['continuity']}
- Compared to baby's usual: {feature_narrative['vs_baseline']}

PATTERN HISTORY:
- This sound pattern has been recorded {cluster_count} time(s) for this baby
- Pattern maturity: {stability} (forming -> emerging -> stable)
- Primary acoustic signal: {intent_label} ({confidence_pct}% confidence){word_note}

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
- Keep each sentence under 25 words
- The 3 action steps must be immediately doable
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
    """Build the enhanced structured insight output."""

    feature_scores = session.get("feature_scores", {})
    deviation_level = session.get("deviation_level", "none")
    deviation_score = session.get("deviation_score", 0.0)

    # 1. Feature narrative — always computed from audio data, no feedback involved
    feature_narrative = describe_features_in_words(feature_scores, deviation_level)

    # 2. Hybrid intent: 70% acoustic signal + 30% feedback history
    probable_intent = determine_probable_intent(cluster, feature_scores)
    cluster_stability = determine_cluster_stability(cluster)

    # 3. Generate insight sections (Bedrock or rule-based)
    use_bedrock = os.environ.get("USE_BEDROCK", str(USE_BEDROCK)).lower() == "true"
    if use_bedrock:
        insight_sections = generate_insight_with_bedrock(
            cluster, probable_intent, feature_narrative, semantic_bridge
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
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return insight


# =============================================================================
# Save Insight
# =============================================================================

def save_insight_to_session(session_id: str, insight: Dict):
    """Save generated insight to session record."""
    session_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET insight = :ins, insight_generated_at = :iga",
        ExpressionAttributeValues={
            ":ins": _float_to_decimal(insight),
            ":iga": datetime.now(timezone.utc).isoformat(),
        }
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

    profile = get_child_profile(child_id)
    if not profile:
        raise ValueError(f"Child profile {child_id} not found")

    cluster = get_cluster(cluster_id)
    if not cluster:
        raise ValueError(f"Cluster {cluster_id} not found")

    semantic_bridge = get_semantic_bridge(cluster_id)

    # 2. Build enhanced insight
    insight = build_insight(session, profile, cluster, semantic_bridge)

    # 3. Save insight to session
    save_insight_to_session(session_id, insight)

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
