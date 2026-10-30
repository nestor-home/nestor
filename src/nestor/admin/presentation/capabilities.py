"""Satellite capabilities as the household reads them; an unknown one keeps its technical name."""

_LABELS = {
    "audio.capture": "micro",
    "audio.playback": "haut-parleur",
    "audio.speech_activity": "détection de parole",
    "vision.person_detection": "détection de personnes (sans image transmise)",
    "expression.emotion": "expressions",
    "motion.head": "mouvements de tête",
}


def french_capability(name: str) -> str:
    return _LABELS.get(name, name)
