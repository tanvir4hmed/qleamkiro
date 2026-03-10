"""
Qleam â€” Shared Constants
Central configuration for all Lambda functions
"""
import os

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
FEEDBACK_TABLE: str = os.environ.get("FEEDBACK_TABLE", "qleam-dev-Feedback")
TRAINING_FEATURES_TABLE: str = os.environ.get("TRAINING_FEATURES_TABLE", "qleam-dev-TrainingFeatures")

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
# Optional AWS Managed Inference Services
# =============================================================================
# Cry/intent custom model endpoint (SageMaker real-time inference).
USE_SAGEMAKER_INTENT_ENDPOINT: bool = os.environ.get("USE_SAGEMAKER_INTENT_ENDPOINT", "false").lower() == "true"
SAGEMAKER_INTENT_ENDPOINT_NAME: str = os.environ.get("SAGEMAKER_INTENT_ENDPOINT_NAME", "")

# HuBERT feature extraction endpoint (SageMaker Serverless).
SAGEMAKER_HUBERT_ENDPOINT: str = os.environ.get("SAGEMAKER_HUBERT_ENDPOINT", "")

# Model version management (Phase 3).
MODEL_VERSIONS_TABLE: str = os.environ.get("MODEL_VERSIONS_TABLE", "")
TRAINING_STEP_FUNCTION_ARN: str = os.environ.get("TRAINING_STEP_FUNCTION_ARN", "")

# Speech transcription for linguistic sessions (Amazon Transcribe).
USE_TRANSCRIBE_FOR_LINGUISTIC: bool = os.environ.get("USE_TRANSCRIBE_FOR_LINGUISTIC", "false").lower() == "true"
TRANSCRIBE_TIMEOUT_SECONDS: int = int(os.environ.get("TRANSCRIBE_TIMEOUT_SECONDS", "25"))

# =============================================================================
# Environment
# =============================================================================
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "dev")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "DEBUG")

# =============================================================================
# Intent Labels
# =============================================================================
INTENT_LABELS = {
    # Canonical v2 taxonomy (9 baby classes + 1 technical class)
    "hunger": "Hungry / Feeding Need",
    "fatigue": "Sleepy / Fatigued",
    "pain": "Pain",
    "discomfort": "Discomfort (physical needs)",
    "closeness": "Needs Closeness / Cuddle",
    "frustration": "Frustrated / Angry",
    "happy": "Happy / Content",
    "exploration": "Neutral / Coos / Exploratory",
    "distress_unknown": "Distress - Unknown",
    "non_baby_spoof_noise": "Non-baby / Spoof / Noise",
    # Backward compatibility aliases
    "connection": "Needs Closeness / Cuddle",
    "overstimulation": "Frustrated / Angry",
    "unknown": "Distress - Unknown",
}

# =============================================================================
# Suggested Responses (rule-based MVP)
# =============================================================================
SUGGESTED_RESPONSES = {
    "hunger": "Offer feeding and check feeding cues (rooting, hand-to-mouth, searching behavior).",
    "fatigue": "Start a sleep routine in a calm, dim environment and reduce stimulation.",
    "pain": "Check immediate pain triggers and seek medical guidance if distress remains high.",
    "discomfort": "Check diaper, temperature, clothing, gas, and body position; provide soothing comfort.",
    "closeness": "Hold baby close, make gentle eye contact, and respond with soft voice.",
    "frustration": "Reduce sensory load, slow transitions, and help baby re-regulate with calm soothing.",
    "happy": "Keep engaging with smiles, mirroring, and gentle play to reinforce positive interaction.",
    "exploration": "Respond to coos and babbles with turn-taking sound play.",
    "distress_unknown": "Use a calm checklist: feeding, rest, comfort, environment, then re-observe.",
    "non_baby_spoof_noise": "Record closer to the baby and reduce background/adult speech for analysis.",
    # Backward compatibility aliases
    "connection": "Hold baby close and respond warmly.",
    "overstimulation": "Reduce stimulation and move to a quieter space.",
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
    # (91,   180,  "EARLY_VOCAL",       "PRE_LINGUISTIC"),
    # (181,  270,  "CANONICAL_BABBLE",  "PRE_LINGUISTIC"),  # 6-9m: still pre-linguistic per spec
    # (271,  365,  "PROTO_WORDS",       "TRANSITION"),
    # (366,  548,  "FIRST_WORDS",       "LINGUISTIC"),
    # # System scope is capped to 0-24 months; older ages are clamped here.
    # (549,  99999, "WORD_COMBINATIONS", "LINGUISTIC"),
    (91, 99999, "NEWBORN", "PRE_LINGUISTIC"),
]

# =============================================================================
# Audio Quality Gate Thresholds (Phase 1 â€” Layer 0)
# Spec: TECHNICAL_PIPELINE.md Layer 0 / SCIENTIFIC_MATHEMATICS.md Section 1
# =============================================================================
QUALITY_MIN_DURATION_SECONDS: float = 3.0   # Was 2.0 â€” spec: Layer 0 gate
QUALITY_MAX_DURATION_SECONDS: float = 600.0  # Was 60 â€” spec: Layer 0 gate max 600s
QUALITY_MIN_SNR_DB: float = 10.0            # Was 5.0  â€” spec: Layer 0 gate
QUALITY_MAX_SILENCE_RATIO: float = 0.80     # Was 0.85 â€” spec: Layer 0 gate
QUALITY_MAX_CLIPPING_RATIO: float = 0.005   # Was 0.05 â€” spec: Layer 0 gate (0.5%)
LOMBARD_NOISE_FLOOR_DB: float = -30.0       # Above this â†’ Lombard effect warning

PRAGMATIC_TYPES = ["declaration", "request", "question", "exclamation"]

# =============================================================================
# Biological Validation Thresholds (Phase 1 â€” Layer 1)
# Spec: SCIENTIFIC_MATHEMATICS.md Theorem 3.1 / TECHNICAL_PIPELINE.md Layer 1
# =============================================================================
VTL_INFANT_MAX_CM: float = 13.0       # Was 12.0 â€” Bayesian-optimal per Theorem 3.1
VTL_UNCERTAIN_MIN_CM: float = 12.5    # 12.5â€“13.0 â†’ UNCERTAIN band
VTL_SPEED_OF_SOUND_CM_S: float = 34300.0  # Deprecated: use temperature-corrected value
VTL_AMBIENT_TEMP_C: float = 20.0      # Default ambient temperature for c(T) calc
INFANT_F0_MIN_HZ: float = 250.0       # Was 200 â€” spec: adult threshold â‰¥ 250 Hz (Theorem 3.1)
STRONG_INFANT_F0_HZ: float = 300.0    # Above this â†’ strong infant signal

# =============================================================================
# Training Candidate Acceptance (Phase 1)
# =============================================================================
TRAINING_ACCEPT_DELTA_MIN: float = float(os.environ.get("TRAINING_ACCEPT_DELTA_MIN", "0.72"))
TRAINING_ACCEPT_FRS_MIN: float = float(os.environ.get("TRAINING_ACCEPT_FRS_MIN", "0.70"))
TRAINING_ACCEPT_ACOUSTIC_RELIABILITY_MIN: float = float(
    os.environ.get("TRAINING_ACCEPT_ACOUSTIC_RELIABILITY_MIN", "0.62")
)
TRAINING_ACCEPT_TOP_MARGIN_MIN: float = float(os.environ.get("TRAINING_ACCEPT_TOP_MARGIN_MIN", "0.08"))
TRAINING_ACCEPT_SCORE_MIN: float = float(os.environ.get("TRAINING_ACCEPT_SCORE_MIN", "0.76"))

# Stage-level training dataset profile reliability and blend controls.
TRAINING_DATASET_MIN_SAMPLES: int = int(os.environ.get("TRAINING_DATASET_MIN_SAMPLES", "120"))
TRAINING_DATASET_BLEND_MAX_ALPHA: float = float(
    os.environ.get("TRAINING_DATASET_BLEND_MAX_ALPHA", "0.18")
)
TRAINING_DATASET_BLEND_SATURATION_SAMPLES: int = int(
    os.environ.get("TRAINING_DATASET_BLEND_SATURATION_SAMPLES", "2000")
)

# =============================================================================
# Online Supervised Acoustic Training (Phase 3)
# =============================================================================
TRAINING_MODEL_MIN_TRAIN_SAMPLES: int = int(os.environ.get("TRAINING_MODEL_MIN_TRAIN_SAMPLES", "120"))
TRAINING_MODEL_MIN_VAL_SAMPLES: int = int(os.environ.get("TRAINING_MODEL_MIN_VAL_SAMPLES", "24"))
TRAINING_MODEL_MIN_LABEL_SUPPORT: int = int(os.environ.get("TRAINING_MODEL_MIN_LABEL_SUPPORT", "8"))
TRAINING_MODEL_MIN_ACCURACY: float = float(os.environ.get("TRAINING_MODEL_MIN_ACCURACY", "0.55"))
TRAINING_MODEL_PROMOTION_MARGIN: float = float(os.environ.get("TRAINING_MODEL_PROMOTION_MARGIN", "0.02"))
TRAINING_MODEL_RETRAIN_EVERY_N: int = int(os.environ.get("TRAINING_MODEL_RETRAIN_EVERY_N", "25"))
TRAINING_MODEL_MAX_CANDIDATES_PER_STAGE: int = int(
    os.environ.get("TRAINING_MODEL_MAX_CANDIDATES_PER_STAGE", "4000")
)

# =============================================================================
# Sound Classification (New Pipeline)
# =============================================================================
# Sound types: speech, cry, laugh, silence, noise, mixed
SOUND_CLASSIFICATION_CONFIDENCE_MIN: float = 0.25  # Below this = noise/unknown

# Transcription (AWS Transcribe — always enabled in new pipeline)
ENABLE_TRANSCRIPTION: bool = os.environ.get("ENABLE_TRANSCRIPTION", "true").lower() == "true"
TRANSCRIBE_LANGUAGE_CODE: str = os.environ.get("TRANSCRIBE_LANGUAGE_CODE", "en-US")
ENABLE_TRANSCRIBE_LANGUAGE_ID: bool = os.environ.get("ENABLE_TRANSCRIBE_LANGUAGE_ID", "true").lower() == "true"

# Cry Emotion Training Model
CRY_MODEL_RETRAIN_THRESHOLD: int = int(os.environ.get("CRY_MODEL_RETRAIN_THRESHOLD", "20"))
CRY_MODEL_MIN_SAMPLES_PER_EMOTION: int = int(os.environ.get("CRY_MODEL_MIN_SAMPLES_PER_EMOTION", "5"))
CRY_MODEL_MIN_TOTAL_SAMPLES: int = int(os.environ.get("CRY_MODEL_MIN_TOTAL_SAMPLES", "15"))

# Private Baby Language Model
PRIVATE_LANG_MATCH_THRESHOLD: float = float(os.environ.get("PRIVATE_LANG_MATCH_THRESHOLD", "0.75"))
PRIVATE_LANG_MIN_OBSERVATIONS: int = int(os.environ.get("PRIVATE_LANG_MIN_OBSERVATIONS", "2"))
