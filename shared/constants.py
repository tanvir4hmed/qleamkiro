"""
Qleam — Shared Constants
Central configuration for all Lambda functions
"""
import os

# =============================================================================
# EMA & Clustering
# =============================================================================
ALPHA_VALUE: float = float(os.environ.get("ALPHA_VALUE", "0.3"))
CLUSTER_SIMILARITY_THRESHOLD: float = float(os.environ.get("CLUSTER_SIMILARITY_THRESHOLD", "0.85"))

# =============================================================================
# Reinforcement Learning Rates
# =============================================================================
REINFORCEMENT_LEARNING_RATE: float = 0.1
REINFORCEMENT_DECAY_NEUTRAL: float = 0.02
REINFORCEMENT_DECAY_INEFFECTIVE: float = 0.05
REINFORCEMENT_MAX: float = 1.0
REINFORCEMENT_MIN: float = 0.0
REINFORCEMENT_NEUTRAL_START: float = 0.5

SEMANTIC_CONFIDENCE_INCREMENT: float = 0.05
SEMANTIC_CONFIDENCE_MAX: float = 1.0

# =============================================================================
# Deviation Detection
# =============================================================================
MIN_SESSIONS_FOR_DEVIATION: int = 3
DEVIATION_THRESHOLD_MODERATE: float = 0.3
DEVIATION_THRESHOLD_HIGH: float = 0.6

# =============================================================================
# Audio Processing
# =============================================================================
MAX_AUDIO_DURATION_SECONDS: int = 30
SAMPLE_RATE: int = 22050
N_MFCC: int = 13
HOP_LENGTH: int = 512
N_FFT: int = 2048

# =============================================================================
# DynamoDB Table Names (from env vars)
# =============================================================================
CHILD_PROFILE_TABLE: str = os.environ.get("CHILD_PROFILE_TABLE", "qleam-dev-ChildProfile")
SESSION_TABLE: str = os.environ.get("SESSION_TABLE", "qleam-dev-Session")
SOUND_CLUSTER_TABLE: str = os.environ.get("SOUND_CLUSTER_TABLE", "qleam-dev-SoundCluster")
SEMANTIC_BRIDGE_TABLE: str = os.environ.get("SEMANTIC_BRIDGE_TABLE", "qleam-dev-SemanticBridge")
FEEDBACK_TABLE: str = os.environ.get("FEEDBACK_TABLE", "qleam-dev-Feedback")
CONCEPT_GRAPH_TABLE: str = os.environ.get("CONCEPT_GRAPH_TABLE", "qleam-dev-ConceptGraph")

# =============================================================================
# S3
# =============================================================================
S3_BUCKET_NAME: str = os.environ.get("S3_BUCKET_NAME", "qleam-dev-audio-storage")

# =============================================================================
# Step Functions
# =============================================================================
STEP_FUNCTION_ARN: str = os.environ.get("STEP_FUNCTION_ARN", "")

# =============================================================================
# Bedrock
# =============================================================================
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
USE_BEDROCK: bool = os.environ.get("USE_BEDROCK", "true").lower() == "true"

# =============================================================================
# Environment
# =============================================================================
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "dev")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "DEBUG")

# =============================================================================
# Intent Labels
# =============================================================================
INTENT_LABELS = {
    "hunger": "Hunger / Feeding Need",
    "connection": "Connection Seeking",
    "discomfort": "Physical Discomfort",
    "overstimulation": "Overstimulation",
    "fatigue": "Fatigue / Sleep Need",
    "exploration": "Exploratory Vocalization",
    "unknown": "Pattern Under Development",
}

# =============================================================================
# Suggested Responses (rule-based MVP)
# =============================================================================
SUGGESTED_RESPONSES = {
    "hunger": "Offer feeding or check hunger cues. Look for rooting reflex or hand-to-mouth movement.",
    "connection": "Provide calm eye contact and gentle verbal reassurance. Hold and respond warmly.",
    "discomfort": "Check for physical discomfort — diaper, temperature, or position. Offer comfort.",
    "overstimulation": "Reduce stimulation. Move to a quieter environment and offer calm, quiet comfort.",
    "fatigue": "Create a calm sleep environment. Reduce light and noise. Offer soothing routine.",
    "exploration": "Engage with gentle vocal mirroring. Respond to sounds with similar sounds.",
    "unknown": "Continue observing. More sessions will help build a clearer pattern.",
}

# =============================================================================
# Disclaimer
# =============================================================================
DISCLAIMER = (
    "This is a behavioral pattern observation, not medical advice. "
    "Qleam provides probabilistic interpretations to support parental awareness. "
    "Always consult a healthcare professional for medical concerns."
)

# =============================================================================
# Developmental Stages (Phase 1)
# Each entry: (min_days_inclusive, max_days_inclusive, stage_name, mode)
# mode: PRE_LINGUISTIC | TRANSITION | LINGUISTIC
# =============================================================================
DEVELOPMENTAL_STAGE_MAP = [
    (0,    90,   "NEWBORN",           "PRE_LINGUISTIC"),
    (91,   180,  "EARLY_VOCAL",       "PRE_LINGUISTIC"),
    (181,  270,  "CANONICAL_BABBLE",  "TRANSITION"),
    (271,  365,  "PROTO_WORDS",       "TRANSITION"),
    (366,  548,  "FIRST_WORDS",       "LINGUISTIC"),
    (549,  730,  "WORD_COMBINATIONS", "LINGUISTIC"),
    (731,  99999, "EARLY_SENTENCES",  "LINGUISTIC"),
]

# =============================================================================
# Audio Quality Gate Thresholds (Phase 1 — Layer 0)
# =============================================================================
QUALITY_MIN_DURATION_SECONDS: float = 2.0
QUALITY_MAX_DURATION_SECONDS: float = 60.0
QUALITY_MIN_SNR_DB: float = 5.0
QUALITY_MAX_SILENCE_RATIO: float = 0.85
QUALITY_MAX_CLIPPING_RATIO: float = 0.05
LOMBARD_NOISE_FLOOR_DB: float = -30.0  # Above this → Lombard effect warning

# =============================================================================
# Biological Validation Thresholds (Phase 1 — Layer 1)
# =============================================================================
VTL_INFANT_MAX_CM: float = 12.0       # Above this → likely adult vocal tract
VTL_SPEED_OF_SOUND_CM_S: float = 34300.0
INFANT_F0_MIN_HZ: float = 200.0       # Below this → likely adult fundamental freq
STRONG_INFANT_F0_HZ: float = 300.0    # Above this → strong infant signal
