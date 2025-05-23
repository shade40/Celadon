from typing import Any

from .text import Text


class Link(Text):
    """A purpose-made Text object for hyperlinks."""

    rules = """
    Link:
        height: 1
        width: shrink
        content_style: 'main.primary-1 underline'

        /hover:
            content_style: 'main.primary bold underline'
    """

    def __init__(self, content: str, to: str | None = None, **widget_args: Any) -> None:
        if to is None:
            to = content.lower()

        if not to.startswith("/"):
            to = "/" + to

        super().__init__(f"[~{to}]{content}[/~]", **widget_args)
