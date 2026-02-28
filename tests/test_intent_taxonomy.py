import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../shared"))

from intent_taxonomy import canonical_intent_key, normalize_intent_distribution


def test_canonical_intent_key_maps_legacy_aliases():
    assert canonical_intent_key("connection", allow_technical=False) == "closeness"
    assert canonical_intent_key("overstimulation", allow_technical=False) == "frustration"
    assert canonical_intent_key("unknown", allow_technical=False) == "distress_unknown"


def test_normalize_intent_distribution_canonicalizes_and_normalizes():
    raw = {
        "connection": 0.6,
        "hunger": 0.2,
        "overstimulation": 0.2,
    }
    out = normalize_intent_distribution(raw, include_technical=False, fill_missing=True)

    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert out["closeness"] > 0.0
    assert out["frustration"] > 0.0
    assert out["hunger"] > 0.0
