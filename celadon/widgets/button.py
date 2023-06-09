from __future__ import annotations

from typing import Callable

from slate import Event, EventCallback

from ..enums import MouseAction, Alignment
from .widget import Widget


class Button(Widget):
    """A simple, pressable/clickable button."""

    on_submit: Event
    """Called when the Button is clicked/pressed using a primary input (mouse1, return).

    Args:
        self: The instance that sent the event.
    """

    on_alt_submit: Event
    """Called when the Button is clicked/pressed using a primary input (mouse2, opt+ret?).

    Args:
        self: The instance that sent the event.
    """

    style_map = Widget.style_map | {
        "hover": {
            "fill": "@ui.panel1-2",
        },
        "active": {
            "fill": "@ui.primary",
            "content": "ui.panel1",
        },
    }

    def __init__(
        self,
        content: str,
        on_submit: list[EventCallback] | None = None,
        on_alt_submit: list[EventCallback] | None = None,
        route: str | None = None,
        **widget_args: Any,
    ):
        super().__init__(**widget_args)

        self.content = content

        self.on_submit = Event("Button submitted")
        for callback in on_submit or []:
            self.on_submit += callback

        if route is not None:
            self.on_submit += lambda *_: self.app.route(route)

        self.on_alt_submit = Event("Button alternate submitted")
        for callback in on_alt_submit or []:
            self.on_alt_submit += callback

    def on_click(self, action: MouseAction, __: tuple[int, int]) -> None:
        def _execute(callback: Callable[[Button], None] | Callable[[], None]) -> None:
            callback(self)

        if "right" in action.value and self.on_alt_submit:
            _execute(self.on_alt_submit)
            return

        _execute(self.on_submit)

    def get_content(self) -> list[str]:
        return [self.content]
