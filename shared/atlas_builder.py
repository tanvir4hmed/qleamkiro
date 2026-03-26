"""
Qleam — Population Atlas Builder
Maintains population-level acoustic feature distributions per age-day.

The BabyDailyAtlas table stores statistical summaries (centroid, std_dev, percentiles)
for each acoustic feature at each age-day. This enables:
- Population context in insights ("Your baby's pitch is at the 75th percentile")
- Outlier detection (deviations > 2 std_dev from population mean)
- Developmental norms tracking

Phase 4: Build atlas from all sessions, update incrementally.
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
BABY_DAILY_ATLAS_TABLE = os.environ.get("BABY_DAILY_ATLAS_TABLE", "")

# Acoustic features to track in the atlas
ATLAS_FEATURES = [
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


def update_daily_atlas(age_days: int, sound_features: Dict[str, Any]) -> bool:
    """
    Update the population atlas with a new sample.
    
    Uses incremental statistics (Welford's algorithm) to update mean and variance
    without storing all samples. Updates percentiles using reservoir sampling.
    
    Args:
        age_days: Baby's age in days
        sound_features: Acoustic features dict from feature extraction
    
    Returns:
        True if atlas updated successfully
    """
    if not BABY_DAILY_ATLAS_TABLE:
        logger.debug("BABY_DAILY_ATLAS_TABLE not configured, skipping atlas update")
        return False
    
    if not isinstance(age_days, int) or age_days < 0 or age_days > 730:
        logger.warning(f"Invalid age_days: {age_days}")
        return False
    
    try:
        atlas_table = dynamodb.Table(BABY_DAILY_ATLAS_TABLE)
        
        for feature_key in ATLAS_FEATURES:
            value = sound_features.get(feature_key)
            if value is None:
                continue
            
            try:
                value_float = float(value)
                if not np.isfinite(value_float):
                    continue
            except (TypeError, ValueError):
                continue
            
            _update_feature_stats(atlas_table, age_days, feature_key, value_float)
        
        logger.info(f"Updated atlas for age_day={age_days}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to update atlas: {e}")
        return False


def _update_feature_stats(
    table,
    age_day: int,
    feature_key: str,
    new_value: float,
):
    """
    Update statistics for a single feature using incremental algorithm.
    
    Uses Welford's online algorithm for mean and variance:
    https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
    """
    pk = age_day
    sk = feature_key
    
    try:
        # Get current stats
        response = table.get_item(Key={"age_day": pk, "feature_key": sk})
        item = response.get("Item")
        
        if item:
            # Existing record - update incrementally
            n = int(item.get("sample_count", 0))
            old_mean = float(item.get("centroid", 0))
            old_m2 = float(item.get("m2", 0))  # Sum of squared differences
            old_min = float(item.get("min_observed", new_value))
            old_max = float(item.get("max_observed", new_value))
            
            # Welford's algorithm
            n_new = n + 1
            delta = new_value - old_mean
            new_mean = old_mean + delta / n_new
            delta2 = new_value - new_mean
            new_m2 = old_m2 + delta * delta2
            
            # Standard deviation
            new_std = np.sqrt(new_m2 / n_new) if n_new > 1 else 0.0
            
            # Min/max
            new_min = min(old_min, new_value)
            new_max = max(old_max, new_value)
            
            # Update percentiles (simplified - store recent samples)
            recent_samples = item.get("recent_samples", [])
            recent_samples = [float(x) for x in recent_samples]
            recent_samples.append(new_value)
            
            # Keep last 100 samples for percentile calculation
            if len(recent_samples) > 100:
                recent_samples = recent_samples[-100:]
            
            # Calculate percentiles from recent samples
            if len(recent_samples) >= 10:
                p10 = float(np.percentile(recent_samples, 10))
                p25 = float(np.percentile(recent_samples, 25))
                p50 = float(np.percentile(recent_samples, 50))
                p75 = float(np.percentile(recent_samples, 75))
                p90 = float(np.percentile(recent_samples, 90))
            else:
                p10 = p25 = p50 = p75 = p90 = new_mean
            
            # Update record
            table.put_item(Item={
                "age_day": pk,
                "feature_key": sk,
                "centroid": Decimal(str(round(new_mean, 6))),
                "std_dev": Decimal(str(round(new_std, 6))),
                "m2": Decimal(str(round(new_m2, 6))),
                "min_observed": Decimal(str(round(new_min, 6))),
                "max_observed": Decimal(str(round(new_max, 6))),
                "p10": Decimal(str(round(p10, 6))),
                "p25": Decimal(str(round(p25, 6))),
                "p50": Decimal(str(round(p50, 6))),
                "p75": Decimal(str(round(p75, 6))),
                "p90": Decimal(str(round(p90, 6))),
                "sample_count": n_new,
                "recent_samples": [Decimal(str(round(x, 6))) for x in recent_samples],
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })
        
        else:
            # New record - initialize
            table.put_item(Item={
                "age_day": pk,
                "feature_key": sk,
                "centroid": Decimal(str(round(new_value, 6))),
                "std_dev": Decimal("0"),
                "m2": Decimal("0"),
                "min_observed": Decimal(str(round(new_value, 6))),
                "max_observed": Decimal(str(round(new_value, 6))),
                "p10": Decimal(str(round(new_value, 6))),
                "p25": Decimal(str(round(new_value, 6))),
                "p50": Decimal(str(round(new_value, 6))),
                "p75": Decimal(str(round(new_value, 6))),
                "p90": Decimal(str(round(new_value, 6))),
                "sample_count": 1,
                "recent_samples": [Decimal(str(round(new_value, 6)))],
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })
    
    except Exception as e:
        logger.warning(f"Failed to update feature {feature_key} for age_day {age_day}: {e}")


def get_population_context(
    age_days: int,
    sound_features: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Get population context for a baby's acoustic features.
    
    Compares the baby's features to population statistics for their age-day.
    Returns percentiles, z-scores, and outlier flags.
    
    Args:
        age_days: Baby's age in days
        sound_features: Acoustic features dict
    
    Returns:
        {
            "age_day": 45,
            "features": {
                "f0_mean": {
                    "value": 420.5,
                    "percentile": 75,
                    "z_score": 1.2,
                    "population_mean": 380.0,
                    "population_std": 35.0,
                    "is_outlier": False,
                },
                ...
            },
            "outliers": ["spectral_centroid"],
            "has_population_data": True,
        }
    """
    if not BABY_DAILY_ATLAS_TABLE:
        return {"has_population_data": False}
    
    if not isinstance(age_days, int) or age_days < 0 or age_days > 730:
        return {"has_population_data": False}
    
    try:
        atlas_table = dynamodb.Table(BABY_DAILY_ATLAS_TABLE)
        
        # Query all features for this age_day
        response = atlas_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("age_day").eq(age_days)
        )
        items = response.get("Items", [])
        
        if not items:
            # Try nearby ages (±3 days) if no exact match
            return _get_nearby_population_context(atlas_table, age_days, sound_features)
        
        # Build feature context
        feature_context = {}
        outliers = []
        
        for item in items:
            feature_key = item.get("feature_key")
            if feature_key not in sound_features:
                continue
            
            value = sound_features.get(feature_key)
            try:
                value_float = float(value)
            except (TypeError, ValueError):
                continue
            
            pop_mean = float(item.get("centroid", 0))
            pop_std = float(item.get("std_dev", 1))
            sample_count = int(item.get("sample_count", 0))
            
            # Skip if insufficient population data
            if sample_count < 5:
                continue
            
            # Calculate z-score
            z_score = (value_float - pop_mean) / max(pop_std, 0.01)
            
            # Calculate percentile from recent samples
            recent_samples = [float(x) for x in item.get("recent_samples", [])]
            if len(recent_samples) >= 10:
                percentile = int(np.searchsorted(sorted(recent_samples), value_float) / len(recent_samples) * 100)
                percentile = max(1, min(99, percentile))
            else:
                # Estimate from z-score using normal distribution approximation
                # CDF approximation: percentile ≈ 50 + 34.13 * z_score (for |z| < 2)
                if abs(z_score) < 2:
                    percentile = int(50 + 34.13 * z_score)
                else:
                    percentile = 99 if z_score > 0 else 1
                percentile = max(1, min(99, percentile))
            
            # Outlier detection (> 2 std dev)
            is_outlier = abs(z_score) > 2.0
            if is_outlier:
                outliers.append(feature_key)
            
            feature_context[feature_key] = {
                "value": round(value_float, 3),
                "percentile": percentile,
                "z_score": round(z_score, 2),
                "population_mean": round(pop_mean, 3),
                "population_std": round(pop_std, 3),
                "is_outlier": is_outlier,
                "sample_count": sample_count,
            }
        
        return {
            "age_day": age_days,
            "features": feature_context,
            "outliers": outliers,
            "has_population_data": len(feature_context) > 0,
        }
    
    except Exception as e:
        logger.error(f"Failed to get population context: {e}")
        return {"has_population_data": False}


def _get_nearby_population_context(
    table,
    age_days: int,
    sound_features: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Get population context from nearby ages if exact age not available.
    Tries ±1, ±2, ±3 days.
    """
    for offset in [1, -1, 2, -2, 3, -3]:
        nearby_age = age_days + offset
        if nearby_age < 0 or nearby_age > 730:
            continue
        
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("age_day").eq(nearby_age)
        )
        items = response.get("Items", [])
        
        if items:
            logger.info(f"Using nearby age {nearby_age} for population context (requested {age_days})")
            # Recursively call main function with nearby age
            result = get_population_context(nearby_age, sound_features)
            if result.get("has_population_data"):
                result["age_day_actual"] = nearby_age
                result["age_day_requested"] = age_days
                result["using_nearby_age"] = True
                return result
    
    return {"has_population_data": False}


def get_atlas_summary(age_days: int) -> Dict[str, Any]:
    """
    Get summary statistics for all features at a given age.
    Useful for debugging and visualization.
    
    Args:
        age_days: Baby's age in days
    
    Returns:
        {
            "age_day": 45,
            "features": {
                "f0_mean": {"mean": 380.0, "std": 35.0, "count": 120},
                ...
            }
        }
    """
    if not BABY_DAILY_ATLAS_TABLE:
        return {}
    
    try:
        atlas_table = dynamodb.Table(BABY_DAILY_ATLAS_TABLE)
        response = atlas_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("age_day").eq(age_days)
        )
        items = response.get("Items", [])
        
        features = {}
        for item in items:
            feature_key = item.get("feature_key")
            features[feature_key] = {
                "mean": float(item.get("centroid", 0)),
                "std": float(item.get("std_dev", 0)),
                "min": float(item.get("min_observed", 0)),
                "max": float(item.get("max_observed", 0)),
                "count": int(item.get("sample_count", 0)),
                "p10": float(item.get("p10", 0)),
                "p50": float(item.get("p50", 0)),
                "p90": float(item.get("p90", 0)),
            }
        
        return {
            "age_day": age_days,
            "features": features,
        }
    
    except Exception as e:
        logger.error(f"Failed to get atlas summary: {e}")
        return {}
