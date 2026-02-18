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
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
USE_BEDROCK: bool = os.environ.get("USE_BEDROCK", "false").lower() == "true"

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
