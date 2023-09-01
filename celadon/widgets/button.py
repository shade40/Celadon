from __future__ import annotations

from typing import Callable

from slate import Event, EventCallback
from zenith.markup import RE_MARKUP

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

    rules = """
    Button:
        content_style: bold
        alignment: [center, center]

        height: 3
        frame: verticalouter

        .compact:
            height: 3
            frame: horizontalouter

        /idle:
            fill_style: '@ui.primary-1'
            frame_style: ui.panel1-2

        /hover:
            fill_style: '@ui.primary+1'
            frame_style: ui.panel1

        /active:
            fill_style: '@ui.primary+3'
            frame_style: ui.panel1+2

        /selected:
            fill_style: '@ui.primary+2'
    """

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
        self.width = len(RE_MARKUP.sub(self.content, "")) + 4

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
