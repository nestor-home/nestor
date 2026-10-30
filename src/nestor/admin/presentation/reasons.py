"""The delivery policy's reasons and subjects, which the domain writes in English, said in French.

An unknown text is shown as written: a new reason is still readable, only not translated.
"""

import re

_REASONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(f"^{pattern}$"), french)
    for pattern, french in (
        (r"asked for it in writing", "la personne a demandé une réponse écrite"),
        (r"quiet hours: nothing spoken", "heures calmes : rien n'est dit à voix haute"),
        (
            r"no presence information: back to the conversation it came from",
            "aucune information de présence : retour à la conversation d'origine",
        ),
        (r"(?P<name>.+) is away", "{name} n'est pas à la maison"),
        (r"(?P<name>.+) is in a room without a satellite", "{name} est dans une pièce sans satellite"),
        (r"(?P<name>.+) is in the (?P<room>.+)", "{name} est dans la pièce « {room} »"),
        (
            r"(?P<name>.+) is home, room unknown: main satellite",
            "{name} est à la maison, pièce inconnue : satellite principal",
        ),
        (r"no satellite where (?P<name>.+) may be", "aucun satellite là où {name} peut se trouver"),
    )
)

_STATUSES = {"completed": "terminée", "failed": "en échec", "cancelled": "annulée", "running": "en cours"}
_SUBJECT = re.compile(r"^(?:task (?P<task>\S+) (?P<status>\w+)|watch (?P<watch>\S+))(?P<follow> \(follow-up\))?$")


def french_reason(reason: str) -> str:
    for pattern, french in _REASONS:  # in order: the first match wins
        if match := pattern.match(reason):
            return french.format(**match.groupdict())
    return reason


def french_subject(about: str) -> str:
    """`task 3f2a1c completed` → `tâche 3f2a1c terminée`; `watch 9d (follow-up)` → `veille 9d (relance)`."""
    match = _SUBJECT.match(about)
    if match is None:
        return about
    if match["task"]:
        text = f"tâche {match['task']} {french_task_status(match['status'])}"
    else:
        text = f"veille {match['watch']}"
    return f"{text} (relance)" if match["follow"] else text


def french_task_status(status: str) -> str:
    return _STATUSES.get(status, status)


def french_watch_end(reason: str) -> str:
    return {"matched": "trouvée", "expired": "expirée", "cancelled": "annulée"}.get(reason, reason)
