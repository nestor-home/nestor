"""What a page refuses to do, said in French to the person using the admin."""


class Refused(Exception):
    """Rendered as an error page with `status`; `message` is shown as is, so it never holds a secret."""

    def __init__(self, status: int, title: str, message: str, *, back: str | None = None) -> None:
        super().__init__(f"{status} {title}: {message}")
        self.status, self.title, self.message, self.back = status, title, message, back
