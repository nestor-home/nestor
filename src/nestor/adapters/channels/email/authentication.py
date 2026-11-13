"""Who wrote a mail: whether a person did, and whether the receiving server vouches for its sender."""

from email.message import EmailMessage


def automatic(message: EmailMessage) -> bool:
    """Mail no person wrote (RFC 3834 `Auto-Submitted`, a responder's or a list's `Precedence`)."""
    submitted = str(message.get("Auto-Submitted", "no")).strip().lower()
    precedence = str(message.get("Precedence", "")).strip().lower()
    return submitted != "no" or precedence in ("bulk", "junk", "list", "auto_reply")


def authenticated(message: EmailMessage, sender: str) -> bool:
    """Whether the receiving server vouches for the sender: DMARC passed, or both DKIM and SPF did."""
    results = " ".join(str(r) for r in message.get_all("Authentication-Results") or []).lower()
    return "dmarc=pass" in results or ("dkim=pass" in results and "spf=pass" in results)
