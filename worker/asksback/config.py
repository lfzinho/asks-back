"""Every tunable number of the follow-up stage, in one place. Teachers override them per exam
(the exam's `followup` settings); anything not overridden keeps these defaults."""

from __future__ import annotations

DEFAULTS = {
    # Credit for points recovered at each help level (concept: N0 100%, N1 75%, N2 50%, N3 25%).
    "weights": {"0": 1.0, "1": 0.75, "2": 0.5, "3": 0.25},
    "max_questions": 3,  # follow-up questions per student
    "max_hints": 3,  # N1..N3: the "3 turns per question" of the cost rule
    "confidence_threshold": 0.7,  # G3 fires below this
    "confidence_values": {"high": 0.9, "medium": 0.6, "low": 0.3},
    "style_z": 2.0,  # G5: how far from the student's own style a feature must be
    "style_min_features": 2,  # G5: how many features must be that far
    "high_real": 0.7,  # real score share that counts as "high"
    "almost_potential": 0.5,  # learning potential needed for "Almost there"
    "window_minutes": 15,  # time to answer all follow-ups, from when the student opens them
    "reply_soft_seconds": 180,  # soft timer shown per question
}

TRIGGERS = {
    "G1": {"name": "Correct, no justification", "type": "justification", "verifies": True},
    "G2": {"name": "Partial answer", "type": "elaboration", "verifies": False},
    "G3": {"name": "Ambiguity", "type": "clarification", "verifies": False},
    "G4": {"name": "Known misconception", "type": "misconception", "verifies": False},
    "G5": {"name": "Uncertain authorship", "type": "transfer", "verifies": True},
}
TRIGGER_ORDER = ["G3", "G4", "G1", "G2", "G5"]  # tie-break when two triggers can change the same points

PROFILES = {
    "mastered": {"label": "Mastered", "action": "Move on"},
    "almost": {"label": "Almost there", "action": "Short review"},
    "building": {"label": "Building", "action": "Guided reteaching"},
    "not_reached": {"label": "Not reached", "action": "Reteach the concept"},
    "verify": {"label": "Verify understanding", "action": "Talk with the teacher"},
}


def settings(overrides: dict | None = None) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (overrides or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update({str(a): b for a, b in v.items()})
        elif k in out and v is not None:
            out[k] = v
    return out
