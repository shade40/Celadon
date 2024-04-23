from __future__ import annotations

from typing import Any

from slate import Event

from ..enums import MouseAction

from .text import Text
from .button import Button
from .container import Tower
from .widget import wrap_callback, _compute


class Dropdown(Tower):
    """A dropdown inspired by HTML's select, taking Button objects."""

    indicators = ["▼", "▲"]

    rules = """
    Dropdown:
        width: shrink

        \> Button:
            width: null
    """

    # Display over other content
    layer = 1

    # Stack without gaps
    gap = 0
    fallback_gap = 0

    def __init__(
        self,
        title: str,
        items: list[Button] | None = None,
        name: str | None = None,
        **widget_args: Any,
    ) -> None:
        super().__init__(*(items or []), **widget_args)

        self.value = title
        self.label = title
        self.name = name
        self.is_open = False

        self._trigger = Button("")
        self.insert(0, self._trigger)
        self.insert(1, Button(title, on_submit=[self._select_option]))

        self._trigger.on_submit += wrap_callback(self.toggle)
        self.height = 1

        def _update_trigger_content() -> None:
            self._trigger.content = f"{self.label} {self.indicators[self.is_open]}"

        def _close_on_deselect() -> None:
            if self.selected_index is None:
                self.close()

        self.pre_content += wrap_callback(_update_trigger_content)
        self.pre_build += wrap_callback(_close_on_deselect)

    def serialize(self) -> dict[str, Any]:
        if self.name is None:
            raise ValueError(f"dropdown {self!r} cannot be serialized without a name.")

        return {self.name: self.value}

    def _select_option(self, button: Button) -> bool:
        """Selects one of the option buttons and updates our state."""

        if button not in self.children:
            raise ValueError("can't select {button!r} since it's not part of {self!r}")

        self.close()
        self.value = button.name or button.content
        self.label = button.content

        return True

    def open(self) -> None:
        """Opens the dropdown."""

        self.is_open = True

    def close(self) -> None:
        """Closes the dropdown."""

        self.is_open = False

    def toggle(self) -> bool:
        """Toggles the dropdown."""

        if self.is_open:
            self.close()
        else:
            self.open()

        return self.is_open

    def append(self, widget: Widget) -> None:
        """Let's any new button child select options."""

        if not isinstance(widget, (Button, Text)):
            raise TypeError(
                "dropdown can only take Buttons and Texts, got {type(widget)!r}."
            )

        super().append(widget)

        if isinstance(widget, Button):
            widget.on_submit += self._select_option

    def drawables(self) -> Iterator[Widget]:
        """Yields children based on whether the dropdown is open."""

        if not self.is_open:
            yield from (self, self._trigger)
            return

        yield from super().drawables()

    def _compute_shrink_width(self) -> int:
        return max(len(widget.content) for widget in self.children) + 4

    @property
    def visible_children(self) -> list[Widget]:
        """Yields visible children based on whether the dropdown is open."""

        if self.is_open:
            return [widget for widget in self.children if not "hidden" in widget.groups]

        return super().visible_children

    def build(
        self, *, virt_width: int | None = None, virt_height: int | None = None
    ) -> list[tuple[Span, ...]]:
        """Fakes `computed_height` while open to allow for dropdown behavior."""

        self.computed_height = len(self.children) if self.is_open else 1

        return super().build(virt_width=virt_width, virt_height=virt_height)
