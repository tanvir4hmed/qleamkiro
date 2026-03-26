"""
Qleam — Individual Baby Trajectory Tracker
Tracks each baby's personal acoustic history and baseline patterns.

The BabyTrajectory table stores each baby's acoustic snapshots over time,
enabling:
- Personal baseline calculation (baby's typical patterns)
- Deviation detection (changes from personal norm)
- Regression alerts (sudden changes that may indicate issues)
- Developmental progress tracking

Phase 5: Track individual baby patterns separate from population.
"""
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
import numpy as np

logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
BABY_TRAJECTORY_TABLE = os.environ.get("BABY_TRAJECTORY_TABLE", "")

# Acoustic features to track in trajectory
TRAJECTORY_FEATURES = [
    "f0_mean",
    "f0_std",
    "f0_instability",
    "rms_mean",
    "spectral_centroid",
    "zcr",
    "energy_variability",
    "voiced_fraction",
    "duration_s",
    "syllable_rate",
]

# Deviation thresholds
SIGNIFICANT_DEVIATION_THRESHOLD = 1.5  # std devs from personal baseline
REGRESSION_THRESHOLD = 2.0  # std devs indicating potential regression


def update_baby_trajectory(
    child_id: str,
    age_days: int,
    sound_features: Dict[str, Any],
    sound_type: str,
    communication_stage: str,
) -> bool:
    """
    Update a baby's personal trajectory with a new acoustic snapshot.
    
    Stores the session's acoustic features and updates the baby's personal baseline.
    
    Args:
        child_id: Baby's unique identifier
        age_days: Baby's age in days
        sound_features: Acoustic features dict from feature extraction
        sound_type: Type of sound (cry, speech, laugh, etc.)
        communication_stage: Developmental stage (A-F)
    
    Returns:
        True if trajectory updated successfully
    """
    if not BABY_TRAJECTORY_TABLE:
        logger.debug("BABY_TRAJECTORY_TABLE not configured, skipping trajectory update")
        return False
    
    if not child_id or not isinstance(age_days, int):
        logger.warning(f"Invalid trajectory update: child_id={child_id}, age_days={age_days}")
        return False
    
    try:
        trajectory_table = dynamodb.Table(BABY_TRAJECTORY_TABLE)
        
        # Create acoustic snapshot
        acoustic_snapshot = {}
        for feature_key in TRAJECTORY_FEATURES:
            value = sound_features.get(feature_key)
            if value is not None:
                try:
                    value_float = float(value)
                    if np.isfinite(value_float):
                        acoustic_snapshot[feature_key] = value_float
                except (TypeError, ValueError):
                    continue
        
        if not acoustic_snapshot:
            logger.warning("No valid features for trajectory update")
            return False
        
        # Session date as sort key (ISO format for proper sorting)
        session_date = datetime.now(timezone.utc).isoformat()
        
        # Store trajectory record
        trajectory_table.put_item(Item={
            "child_id": child_id,
            "session_date": session_date,
            "age_days": age_days,
            "communication_stage": communication_stage,
            "sound_type": sound_type,
            "acoustic_snapshot": _to_decimal_dict(acoustic_snapshot),
            "created_at": session_date,
        })
        
        logger.info(f"Updated trajectory for child {child_id} at age {age_days} days")
        return True
    
    except Exception as e:
        logger.error(f"Failed to update trajectory: {e}")
        return False


def get_personal_context(
    child_id: str,
    age_days: int,
    sound_features: Dict[str, Any],
    population_context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Get personal context by comparing current features to baby's baseline.
    
    Calculates:
    - Personal baseline (baby's typical values)
    - Deviation from baseline (how different from usual)
    - Trend direction (improving/stable/regressing)
    - Comparison to population (personal vs population percentile)
    
    Args:
        child_id: Baby's unique identifier
        age_days: Baby's age in days
        sound_features: Current session's acoustic features
        population_context: Optional population context from atlas
    
    Returns:
        {
            "has_personal_history": True,
            "sessions_count": 15,
            "baseline": {
                "f0_mean": {"mean": 385.0, "std": 12.5},
                ...
            },
            "deviations": {
                "f0_mean": {
                    "current": 420.0,
                    "baseline_mean": 385.0,
                    "deviation_z": 2.8,
                    "is_significant": True,
                    "direction": "higher"
                },
                ...
            },
            "significant_deviations": ["f0_mean", "rms_mean"],
            "regression_flags": [],
            "trend": "stable",
        }
    """
    if not BABY_TRAJECTORY_TABLE or not child_id:
        return {"has_personal_history": False}
    
    try:
        trajectory_table = dynamodb.Table(BABY_TRAJECTORY_TABLE)
        
        # Query recent history (last 30 days or 20 sessions)
        response = trajectory_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id),
            ScanIndexForward=False,  # Most recent first
            Limit=20,
        )
        items = response.get("Items", [])
        
        if len(items) < 3:
            # Need at least 3 sessions to establish baseline
            return {
                "has_personal_history": False,
                "sessions_count": len(items),
                "message": "Building personal baseline (need 3+ sessions)",
            }
        
        # Calculate personal baseline from history
        baseline = _calculate_personal_baseline(items)
        
        # Calculate deviations from baseline
        deviations = {}
        significant_deviations = []
        regression_flags = []
        
        for feature_key in TRAJECTORY_FEATURES:
            if feature_key not in baseline or feature_key not in sound_features:
                continue
            
            current_value = sound_features.get(feature_key)
            try:
                current_float = float(current_value)
            except (TypeError, ValueError):
                continue
            
            baseline_mean = baseline[feature_key]["mean"]
            baseline_std = baseline[feature_key]["std"]
            
            # Skip if no variance in baseline (all values identical)
            if baseline_std < 0.01:
                continue
            
            # Calculate deviation z-score
            deviation_z = (current_float - baseline_mean) / baseline_std
            
            # Determine direction
            if abs(deviation_z) < 0.5:
                direction = "typical"
            elif deviation_z > 0:
                direction = "higher"
            else:
                direction = "lower"
            
            # Check significance
            is_significant = abs(deviation_z) > SIGNIFICANT_DEVIATION_THRESHOLD
            is_regression = abs(deviation_z) > REGRESSION_THRESHOLD
            
            if is_significant:
                significant_deviations.append(feature_key)
            
            if is_regression:
                regression_flags.append({
                    "feature": feature_key,
                    "deviation_z": round(deviation_z, 2),
                    "message": f"{feature_key} is {abs(deviation_z):.1f} std devs from personal baseline",
                })
            
            deviations[feature_key] = {
                "current": round(current_float, 3),
                "baseline_mean": round(baseline_mean, 3),
                "baseline_std": round(baseline_std, 3),
                "deviation_z": round(deviation_z, 2),
                "is_significant": is_significant,
                "direction": direction,
            }
        
        # Determine overall trend
        trend = _determine_trend(items, age_days)
        
        # Compare personal vs population
        personal_vs_population = None
        if population_context and population_context.get("has_population_data"):
            personal_vs_population = _compare_personal_to_population(
                baseline, population_context
            )
        
        return {
            "has_personal_history": True,
            "sessions_count": len(items),
            "baseline": baseline,
            "deviations": deviations,
            "significant_deviations": significant_deviations,
            "regression_flags": regression_flags,
            "trend": trend,
            "personal_vs_population": personal_vs_population,
        }
    
    except Exception as e:
        logger.error(f"Failed to get personal context: {e}")
        return {"has_personal_history": False, "error": str(e)}


def _calculate_personal_baseline(history_items: List[Dict]) -> Dict[str, Dict]:
    """
    Calculate personal baseline statistics from history.
    
    Returns:
        {
            "f0_mean": {"mean": 385.0, "std": 12.5, "min": 360.0, "max": 410.0},
            ...
        }
    """
    baseline = {}
    
    # Collect values per feature
    feature_values = {key: [] for key in TRAJECTORY_FEATURES}
    
    for item in history_items:
        snapshot = item.get("acoustic_snapshot", {})
        for feature_key in TRAJECTORY_FEATURES:
            value = snapshot.get(feature_key)
            if value is not None:
                try:
                    feature_values[feature_key].append(float(value))
                except (TypeError, ValueError):
                    continue
    
    # Calculate statistics
    for feature_key, values in feature_values.items():
        if len(values) >= 3:
            values_array = np.array(values)
            baseline[feature_key] = {
                "mean": float(np.mean(values_array)),
                "std": float(np.std(values_array)),
                "min": float(np.min(values_array)),
                "max": float(np.max(values_array)),
                "count": len(values),
            }
    
    return baseline


def _determine_trend(history_items: List[Dict], current_age: int) -> str:
    """
    Determine developmental trend from recent history.
    
    Returns:
        "improving", "stable", "regressing", or "insufficient_data"
    """
    if len(history_items) < 5:
        return "insufficient_data"
    
    try:
        # Look at f0_instability trend (should decrease with age = improving)
        # and voiced_fraction trend (should increase with age = improving)
        instability_values = []
        voiced_values = []
        ages = []
        
        for item in history_items[:10]:  # Last 10 sessions
            snapshot = item.get("acoustic_snapshot", {})
            age = item.get("age_days")
            
            if age is not None:
                ages.append(age)
                instability_values.append(float(snapshot.get("f0_instability", 0)))
                voiced_values.append(float(snapshot.get("voiced_fraction", 0)))
        
        if len(ages) < 5:
            return "insufficient_data"
        
        # Calculate trends (correlation with age)
        ages_array = np.array(ages)
        instability_array = np.array(instability_values)
        voiced_array = np.array(voiced_values)
        
        # Normalize to 0-1 range for comparison
        age_range = ages_array.max() - ages_array.min()
        if age_range < 7:  # Less than a week of data
            return "stable"
        
        # Instability should decrease (negative correlation = good)
        instability_corr = np.corrcoef(ages_array, instability_array)[0, 1]
        
        # Voiced fraction should increase (positive correlation = good)
        voiced_corr = np.corrcoef(ages_array, voiced_array)[0, 1]
        
        # Combined trend score
        trend_score = -instability_corr + voiced_corr
        
        if trend_score > 0.3:
            return "improving"
        elif trend_score < -0.3:
            return "regressing"
        else:
            return "stable"
    
    except Exception as e:
        logger.warning(f"Failed to determine trend: {e}")
        return "insufficient_data"


def _compare_personal_to_population(
    baseline: Dict[str, Dict],
    population_context: Dict,
) -> Dict[str, Any]:
    """
    Compare baby's personal baseline to population norms.
    
    Returns:
        {
            "f0_mean": {
                "personal_mean": 385.0,
                "population_mean": 380.5,
                "personal_percentile": 58,
                "interpretation": "slightly_above_average"
            },
            ...
        }
    """
    comparison = {}
    
    pop_features = population_context.get("features", {})
    
    for feature_key, baseline_stats in baseline.items():
        if feature_key not in pop_features:
            continue
        
        personal_mean = baseline_stats["mean"]
        pop_mean = pop_features[feature_key].get("population_mean")
        pop_std = pop_features[feature_key].get("population_std")
        
        if pop_mean is None or pop_std is None or pop_std < 0.01:
            continue
        
        # Calculate where personal baseline sits in population
        z_score = (personal_mean - pop_mean) / pop_std
        
        # Estimate percentile from z-score
        if abs(z_score) < 2:
            percentile = int(50 + 34.13 * z_score)
        else:
            percentile = 99 if z_score > 0 else 1
        percentile = max(1, min(99, percentile))
        
        # Interpretation
        if abs(z_score) < 0.5:
            interpretation = "average"
        elif z_score > 1.5:
            interpretation = "well_above_average"
        elif z_score > 0.5:
            interpretation = "slightly_above_average"
        elif z_score < -1.5:
            interpretation = "well_below_average"
        else:
            interpretation = "slightly_below_average"
        
        comparison[feature_key] = {
            "personal_mean": round(personal_mean, 3),
            "population_mean": round(pop_mean, 3),
            "personal_percentile": percentile,
            "z_score": round(z_score, 2),
            "interpretation": interpretation,
        }
    
    return comparison


def get_trajectory_summary(child_id: str, limit: int = 30) -> Dict[str, Any]:
    """
    Get summary of baby's trajectory over time.
    Useful for visualization and debugging.
    
    Args:
        child_id: Baby's unique identifier
        limit: Maximum number of sessions to return
    
    Returns:
        {
            "child_id": "abc123",
            "sessions": [
                {
                    "session_date": "2026-03-26T15:30:22Z",
                    "age_days": 45,
                    "sound_type": "cry",
                    "f0_mean": 385.0,
                    ...
                },
                ...
            ],
            "baseline": {...},
            "trend": "improving"
        }
    """
    if not BABY_TRAJECTORY_TABLE or not child_id:
        return {}
    
    try:
        trajectory_table = dynamodb.Table(BABY_TRAJECTORY_TABLE)
        
        response = trajectory_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = response.get("Items", [])
        
        # Format sessions
        sessions = []
        for item in items:
            snapshot = item.get("acoustic_snapshot", {})
            session = {
                "session_date": item.get("session_date"),
                "age_days": item.get("age_days"),
                "sound_type": item.get("sound_type"),
                "communication_stage": item.get("communication_stage"),
            }
            # Add acoustic features
            for key, value in snapshot.items():
                session[key] = float(value)
            sessions.append(session)
        
        # Calculate baseline and trend
        baseline = _calculate_personal_baseline(items) if len(items) >= 3 else {}
        trend = _determine_trend(items, items[0].get("age_days", 0)) if items else "insufficient_data"
        
        return {
            "child_id": child_id,
            "sessions_count": len(sessions),
            "sessions": sessions,
            "baseline": baseline,
            "trend": trend,
        }
    
    except Exception as e:
        logger.error(f"Failed to get trajectory summary: {e}")
        return {}


def _to_decimal_dict(d: Dict[str, float]) -> Dict[str, Decimal]:
    """Convert float dict to Decimal dict for DynamoDB."""
    return {k: Decimal(str(round(v, 6))) for k, v in d.items()}
