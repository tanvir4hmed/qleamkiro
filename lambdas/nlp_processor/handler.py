"""
Qleam — NLP Processor Lambda
Extracts semantic concepts from parent free-text notes and updates the concept graph.

Trigger: Async invoke from feedback_processor when notes are non-empty
Input:  { child_id, cluster_id, notes, session_id }
Output: { status, concepts_updated }
"""
import json
import logging
import os
import sys

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from concept_graph import upsert_concept
from constants import BEDROCK_MODEL_ID, CONCEPT_GRAPH_TABLE

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

_VALID_INTENTS = {"hunger", "thirst", "sleep", "discomfort", "pain", "cold", "hot",
                  "connection", "attention", "comfort", "fear"}

_SYSTEM_PROMPT = """You are a semantic analysis assistant for a baby language app.
Analyze a parent's free-text note about what happened when their baby cried.
Extract structured information in JSON format.

Rules:
- extracted_intent: ONE of hunger|thirst|sleep|discomfort|pain|cold|hot|connection|attention|comfort|fear, or null if unclear
- detected_objects: list of concrete nouns/objects mentioned (toys, food items, places, etc.). Max 5. Lowercase. Empty list if none.
- confidence_modifier: float 0.5–1.0. Reduce if parent uses hedging words ("I think", "maybe", "not sure", "probably"). High (0.9+) for definitive statements.

Respond ONLY with valid JSON, no explanation:
{"extracted_intent": "hunger", "detected_objects": ["bottle", "bib"], "confidence_modifier": 0.85}"""


def _extract_with_bedrock(notes: str) -> dict:
    """Call Bedrock to extract intent/objects from parent free text."""
    model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": f"Parent's note: {notes[:500]}"}
        ],
    }
    response = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    result_text = json.loads(response["body"].read())["content"][0]["text"].strip()
    return json.loads(result_text)


def lambda_handler(event: dict, context) -> dict:
    """
    NLP Processor handler.

    Args:
        event: {
            "child_id": str,
            "cluster_id": str,
            "notes": str,
            "session_id": str
        }
    """
    child_id = event.get("child_id", "")
    cluster_id = event.get("cluster_id", "")
    notes = str(event.get("notes", "")).strip()
    session_id = event.get("session_id", "")

    if not child_id or not notes:
        logger.warning("NLP processor called with missing child_id or notes — skipping")
        return {"status": "skipped", "reason": "missing_fields"}

    logger.info(f"NLP processing for child={child_id} session={session_id} notes_len={len(notes)}")

    try:
        extraction = _extract_with_bedrock(notes)
    except Exception as e:
        logger.error(f"Bedrock extraction failed: {e}")
        return {"status": "error", "reason": "bedrock_failed"}

    extracted_intent = extraction.get("extracted_intent")
    detected_objects = extraction.get("detected_objects", [])
    confidence_modifier = float(extraction.get("confidence_modifier", 0.75))

    logger.info(
        f"Extracted: intent={extracted_intent} objects={detected_objects} "
        f"confidence_modifier={confidence_modifier:.2f}"
    )

    concepts_updated = []

    # Update concept graph for detected objects (personal concepts)
    for obj in detected_objects[:5]:
        obj_clean = str(obj).strip().lower()
        if obj_clean:
            try:
                concept_id = upsert_concept(
                    child_id=child_id,
                    label=obj_clean,
                    category="personal",
                    table=concept_graph_table,
                    cluster_id=cluster_id or None,
                    description=notes,
                )
                concepts_updated.append({"label": obj_clean, "concept_id": concept_id, "category": "personal"})
            except Exception as e:
                logger.warning(f"Failed to upsert personal concept '{obj_clean}': {e}")

    # Update universal concept for extracted intent
    if extracted_intent and extracted_intent in _VALID_INTENTS:
        try:
            concept_id = upsert_concept(
                child_id=child_id,
                label=extracted_intent,
                category="universal",
                table=concept_graph_table,
                cluster_id=cluster_id or None,
                description=None,  # Don't store raw notes on universal concepts
            )
            concepts_updated.append({"label": extracted_intent, "concept_id": concept_id, "category": "universal"})
        except Exception as e:
            logger.warning(f"Failed to upsert universal concept '{extracted_intent}': {e}")

    logger.info(f"NLP processor updated {len(concepts_updated)} concepts for child {child_id}")
    return {
        "status": "ok",
        "child_id": child_id,
        "session_id": session_id,
        "concepts_updated": len(concepts_updated),
        "extracted_intent": extracted_intent,
        "detected_objects": detected_objects,
    }
