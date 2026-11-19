"""What a person says while the assistant speaks without meaning to cut it off: "mmh", "ouais", "yeah", "right".

One set for every language: a household mixes them ("ok", "yeah" in French), and no word here is a real reply in
another language. Measured by the `acknowledgements` bench (`bench/voice/`), spoken by a speech model then heard by a
transcription model, as on a satellite. Imports nothing heavy, so the bench reads it without the `voice` extra.
"""

import re

ACKNOWLEDGEMENTS = frozenset(
    [
        # sounds, in any language
        "mmh",
        "mmm",
        "mm",
        "mhm",
        "hm",
        "hmm",
        "hum",
        "uh",
        "huh",
        "ah",
        "oh",
        "ok",
        "okay",
        # French
        "ouais",
        "ouai",
        "oui",
        "d'accord",
        "daccord",
        "bah",
        "ben",
        "euh",
        "voilà",
        "vois",
        "je",
        "exact",
        "exactement",
        "carrément",
        "super",
        "cool",
        "bon",
        "ouf",
        # English
        "yeah",
        "yea",
        "yep",
        "yup",
        "yes",
        "right",
        "sure",
        "alright",
        "all",
        "got",
        "it",
        "gotcha",
        "i",
        "see",
        "exactly",
        "totally",
        "true",
        "nice",
        "great",
        "wow",
    ]
)
_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœ']+")


def is_acknowledgement(text: str) -> bool:
    """True when every word is an acknowledgement; nothing heard is not one."""
    words = _WORD.findall(text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'"))
    return bool(words) and all(word in ACKNOWLEDGEMENTS for word in words)
