from typing import Any

from slate import Event, EventCallback

from ..enums import MouseAction
from .widget import Widget


class Checkbox(Widget):
    """A simple button-like widget for checkboxes."""

    content: str
    checked: bool = False
    indicators: tuple[str, str] = ("□", "[ui.primary]▣[/]")

    on_change: Event
    """Called when the Checkbox's value changed.

    Args:
        self: The Checkbox that sent the event. Use `self.checked` to get current state.
    """

    def __init__(
        self,
        content: str,
        checked: bool = False,
        indicators: tuple[str, str] = ("□", "[ui.primary]▣[/]"),
        on_change: list[EventCallback] | None = None,
        **widget_args: Any,
    ) -> None:
        super().__init__(**widget_args)

        self.content = content
        self.checked = checked
        self.indicators = indicators

        self.on_change = Event("Checkbox changed")
        for event in on_change or []:
            self.on_change += event

    def on_click(self, action: MouseAction, __: tuple[int, int]) -> None:
        self.checked = not self.checked
        self.on_toggle(self.checked)

    def get_content(self) -> None:
        return [f"{self.indicators[self.checked]} {self.content}"]
