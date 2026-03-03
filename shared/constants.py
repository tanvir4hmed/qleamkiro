"""
Qleam â€” Shared Constants
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
MILESTONES_TABLE: str = os.environ.get("MILESTONES_TABLE", "qleam-dev-Milestones")
POPULATION_MODEL_TABLE: str = os.environ.get("POPULATION_MODEL_TABLE", "qleam-dev-PopulationModel")
TRAINING_CANDIDATE_TABLE: str = os.environ.get("TRAINING_CANDIDATE_TABLE", "qleam-dev-TrainingCandidate")
MODEL_REGISTRY_TABLE: str = os.environ.get("MODEL_REGISTRY_TABLE", "qleam-dev-ModelRegistry")

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
    (91,   180,  "EARLY_VOCAL",       "PRE_LINGUISTIC"),
    (181,  270,  "CANONICAL_BABBLE",  "PRE_LINGUISTIC"),  # 6-9m: still pre-linguistic per spec
    (271,  365,  "PROTO_WORDS",       "TRANSITION"),
    (366,  548,  "FIRST_WORDS",       "LINGUISTIC"),
    (549,  730,  "WORD_COMBINATIONS", "LINGUISTIC"),
    (731,  99999, "EARLY_SENTENCES",  "LINGUISTIC"),
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

# =============================================================================
# Milestone Types (Phase 6)
# =============================================================================
MILESTONE_TYPES = {
    "FIRST_CANONICAL_BABBLE":     "First session with CBR > 0.20",
    "FIRST_PROTO_WORD_CANDIDATE": "First cluster meeting proto-word criteria",
    "FIRST_CONFIRMED_PROTO_WORD": "Cluster promoted to established signal",
    "LINGUISTIC_MODE_TRANSITION": "First session in LINGUISTIC mode",
    "CONCEPT_GRAPH_10_NODES":     "Personal concept graph reached 10 confirmed concepts",
    "CONCEPT_GRAPH_25_NODES":     "Personal concept graph reached 25 confirmed concepts",
    "FIRST_MLU_2":                "Estimated MLU reached 2.0 (two-morpheme utterances)",
    "FIRST_MLU_3":                "Estimated MLU reached 3.0 (three-morpheme utterances)",
    "VOCAB_SIZE_20":              "Confirmed vocabulary reached 20 concepts",
    "VOCAB_SIZE_50":              "Confirmed vocabulary reached 50 concepts",
}

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
# Federated Learning (Phase 8 â€” FIVL)
# Spec: SCIENTIFIC_MATHEMATICS.md Section 10, Theorem 10.1-10.2
# =============================================================================
FL_EPSILON: float = 1.0          # Differential privacy Îµ (privacy budget)
FL_DELTA: float = 1e-5           # Differential privacy Î´ (failure probability)
FL_MIN_PARTICIPANTS: int = 10    # Minimum sessions per stage before aggregation
FL_FRS_QUALITY_GATE: float = 0.60   # Minimum FRS for session to be included
FL_DELTA_QUALITY_GATE: float = 0.65  # Minimum delta_score for session to be included
FL_RESEARCH_FLOOR: float = 0.10  # Research prior floor â€” never fully replaced by FL
FL_ROUND_INTERVAL_HOURS: int = 24    # How often aggregation runs (via EventBridge)

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
CRY_MODEL_RETRAIN_THRESHOLD: int = int(os.environ.get("CRY_MODEL_RETRAIN_THRESHOLD", "10"))
CRY_MODEL_MIN_SAMPLES_PER_EMOTION: int = int(os.environ.get("CRY_MODEL_MIN_SAMPLES_PER_EMOTION", "5"))
CRY_MODEL_MIN_TOTAL_SAMPLES: int = int(os.environ.get("CRY_MODEL_MIN_TOTAL_SAMPLES", "10"))

# =============================================================================
# Multimodal Cry Feature Encoding (Phase: Context + Behavioral features)
# All values use -1 for "unknown / not recorded" to distinguish from "absent".
# =============================================================================

# feeding_status — derived from feeding_minutes_ago
FEEDING_STATUS_MUCH_EARLY: int = 0    # > 90 min earlier than normal
FEEDING_STATUS_EARLY: int = 1         # 30–90 min earlier than normal
FEEDING_STATUS_NORMAL: int = 2        # ±30 min of expected feed time
FEEDING_STATUS_LATE: int = 3          # 30–90 min later than normal
FEEDING_STATUS_MUCH_LATE: int = 4     # > 90 min later than normal
FEEDING_STATUS_UNKNOWN: int = -1

# sleep_status
SLEEP_STATUS_JUST_WOKE: int = 0       # < 30 min awake
SLEEP_STATUS_RESTED: int = 1          # 30 min – 3 hr awake
SLEEP_STATUS_PROBABLY_TIRED: int = 2  # 3–5 hr awake
SLEEP_STATUS_OVERTIRED: int = 3       # > 5 hr awake
SLEEP_STATUS_UNKNOWN: int = -1

# health_flag — derived from health_state string
HEALTH_FLAG_HEALTHY: int = 0
HEALTH_FLAG_FUSSY: int = 1            # Behavioural, non-illness
HEALTH_FLAG_TEETHING: int = 2
HEALTH_FLAG_SICK_MILD: int = 3
HEALTH_FLAG_SICK_SEVERE: int = 4      # Fever / doctor visit
HEALTH_FLAG_UNKNOWN: int = -1

# Behavioral cue flags (binary: 0=absent, 1=present, -1=unknown)
BEHAVIORAL_FLAG_ABSENT: int = 0
BEHAVIORAL_FLAG_PRESENT: int = 1
BEHAVIORAL_FLAG_UNKNOWN: int = -1

# location_code — derived from environment string
LOCATION_HOME_QUIET: int = 0
LOCATION_HOME_NOISY: int = 1
LOCATION_OUTDOOR: int = 2
LOCATION_CAR: int = 3
LOCATION_OTHER: int = 4
LOCATION_UNKNOWN: int = -1

# noise_level — auto-derived from environment
NOISE_LEVEL_QUIET: int = 0            # home_quiet
NOISE_LEVEL_MODERATE: int = 1        # outdoor, car
NOISE_LEVEL_LOUD: int = 2            # home_noisy
NOISE_LEVEL_UNKNOWN: int = -1

# trigger_code (12m+ only)
TRIGGER_NONE: int = 0
TRIGGER_WOKE_FROM_SLEEP: int = 1
TRIGGER_FEEDING_DUE: int = 2
TRIGGER_ACTIVITY_INTERRUPTED: int = 3
TRIGGER_OBJECT_TAKEN: int = 4
TRIGGER_CAREGIVER_LEFT: int = 5
TRIGGER_OVERSTIMULATION: int = 6
TRIGGER_TRANSITION: int = 7          # Bath, car, bedtime
TRIGGER_PAIN_EVENT: int = 8
TRIGGER_UNKNOWN: int = -1

# Encoding lookup maps (string → int) for use in Lambda handlers
HEALTH_STATE_ENCODING = {
    "healthy": HEALTH_FLAG_HEALTHY,
    "fussy":   HEALTH_FLAG_FUSSY,
    "teething":HEALTH_FLAG_TEETHING,
    "sick":    HEALTH_FLAG_SICK_MILD,
    "other":   HEALTH_FLAG_SICK_MILD,
    "unknown": HEALTH_FLAG_UNKNOWN,
}

ENVIRONMENT_TO_LOCATION = {
    "home_quiet": LOCATION_HOME_QUIET,
    "home_noisy": LOCATION_HOME_NOISY,
    "outdoor":    LOCATION_OUTDOOR,
    "car":        LOCATION_CAR,
    "other":      LOCATION_OTHER,
    "unknown":    LOCATION_UNKNOWN,
}

ENVIRONMENT_TO_NOISE = {
    "home_quiet": NOISE_LEVEL_QUIET,
    "home_noisy": NOISE_LEVEL_LOUD,
    "outdoor":    NOISE_LEVEL_MODERATE,
    "car":        NOISE_LEVEL_MODERATE,
    "other":      NOISE_LEVEL_UNKNOWN,
    "unknown":    NOISE_LEVEL_UNKNOWN,
}

# Feature version tag — models trained with 12 acoustic features are "v1";
# models trained with the full 22-feature multimodal vector are "v2".
CRY_FEATURE_VERSION_V1: str = "v1"   # 12 acoustic features (legacy)
CRY_FEATURE_VERSION_V2: str = "v2"   # 22 features: 12 acoustic + 10 context/behavioral

# Private Baby Language Model
PRIVATE_LANG_MATCH_THRESHOLD: float = float(os.environ.get("PRIVATE_LANG_MATCH_THRESHOLD", "0.75"))
PRIVATE_LANG_MIN_OBSERVATIONS: int = int(os.environ.get("PRIVATE_LANG_MIN_OBSERVATIONS", "2"))
