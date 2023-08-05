from __future__ import annotations

from typing import Iterable
from .widget import Widget, _overflows
from ..enums import MouseAction

__all__ = [
    "Container",
    "Tower",
    "Row",
]


class Container(Widget):
    """A widget that displays others based on some arrangement algorithm.

    See `Tower` and `Splitter` for the implementations you should use.
    """

    style_map = Widget.style_map | {
        "idle": {"scrollbar_y": "ui.secondary"},
        "hover": {"fill": Widget.style_map["idle"]["fill"]},
    }

    def __init__(self, *children: Widget, **widget_args: Any) -> None:
        self.children = []
        for child in children:
            self.append(child)

        super().__init__(**widget_args)

        self._should_layout = False
        self._layout_state: int = -1
        self._mouse_target: Widget | None = None

    @property
    def visible_children(self) -> list[Widget]:
        return [widget for widget in self.children if not "hidden" in widget.groups]

    def __iadd__(self, other: object) -> Container:
        if not isinstance(other, Widget):
            raise TypeError(
                f"Can only append widgets to containers, not {type(other)!r}."
            )

        self.append(other)
        return self

    def _as_layout_state(self) -> int:
        """Generates an integer that represents the current layout."""

        if any(w.eid == "sidebar" for w in self.visible_children):
            print(
                " ".join(
                    f"{widget.position[0]};{widget.position[1]}-{widget.width_hint}x{widget.height_hint}"
                    for widget in self.visible_children
                )
            )

        return hash(
            " ".join(
                f"{widget.position[0]};{widget.position[1]}-{widget.width_hint}x{widget.height_hint}"
                for widget in self.visible_children
            )
        )

    def append(self, widget: Widget) -> None:
        """Adds a new widget setting its parent attribute to self."""

        self.children.append(widget)
        widget.parent = self
        self._should_layout = True

    def extend(self, widgets: Iterable[Widget]) -> None:
        """Extends our children by the given iterable."""

        for widget in widgets:
            self.append(widget)

    def remove(self, widget: Widget) -> None:
        """Removes a widget from self, resetting its parent attribute to None."""

        self.children.remove(widget)
        widget.parent = None
        self._should_layout = True

    def pop(self, index: int) -> Widget:
        """Pops a widget from our children.

        Returns:
            The widget that was just removed.
        """

        widget = self.children[i]
        self.remove(widget)

        return widget

    def clear(self) -> None:
        """Removes all widgets."""

        for widget in self.children:
            self.remove(widget)

    def update_children(self, widgets: Iterable[Widget]) -> None:
        """Updates our children to the given iterable."""

        self.clear()
        self.extend(widgets)

    def move_by(self, x: int, y: int) -> None:
        """Moves the widget (and all its children) to the given position."""

        super().move_by(x, y)

        for child in self.children:
            child.move_by(x, y)

    def arrange(self, x: int, y: int) -> None:
        """Arranges this widget's contents based on an algorithm.

        Args:
            x: The x position this widget starts at.
            y: The y position this widget starts at.
        """

        raise NotImplementedError

    def get_content(self) -> list[str]:
        """Calls our `arrange` method and returns a single empty line."""

        # layout_state = self._as_layout_state()

        # if layout_state != self._layout_state:
        start_x = self.position[0] + (self.frame.left != "")
        start_y = self.position[1] + (self.frame.top != "") + (self._clip_start or 0)

        self.arrange(start_x - self.scroll[0], start_y - self.scroll[1])
        # self._layout_state = layout_state

        return [""]

    def handle_keyboard(self, key: str) -> bool:
        # TODO: This is temporary
        if key == "up":
            self.scroll = self.scroll[0], self.scroll[1] - 1
            return True

        if key == "down":
            self.scroll = self.scroll[0], self.scroll[1] + 1
            return True

        if key == "left":
            self.scroll = self.scroll[0] - 1, self.scroll[1]
            return True

        if key == "right":
            self.scroll = self.scroll[0] + 1, self.scroll[1]
            return True

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        if self._mouse_target is not None:
            if action is MouseAction.LEFT_RELEASE:
                self._mouse_target.handle_mouse(action, position)
                self._mouse_target = None
                return True

            if action is MouseAction.HOVER and not self._mouse_target.contains(
                position
            ):
                self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

        for widget in self.visible_children:
            if not widget.contains(position):
                continue

            if widget.handle_mouse(action, position):
                if self._mouse_target not in [widget, None]:
                    self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

                self._mouse_target = widget
                return True

        return super().handle_mouse(action, position)

    def drawables(self) -> Iterator[Widget]:
        # TODO: Implement child-clipping

        yield self

        for widget in self.children:
            yield from widget.drawables()

    def build(self) -> list[tuple[Span, ...]]:
        return super().build(
            virt_width=max(
                (widget.computed_width for widget in self.children), default=1
            ),
            virt_height=sum(widget.computed_height for widget in self.children),
        )


class Tower(Container):
    """Arranges widgets in a vertical tower.

    ```
    +----------------+ <- alignment=("center", "center")
    |                |
    |     +---+      |
    |     |   | <------- width=0.5
    |     +---+      |
    |   +--------+   |
    |   |        | <---- width=1.0
    |   +--------+   |
    |    +-----+     |
    |    |     | <------ width=7
    |    +-----+     |
    |                |
    +----------------+
    ```
    """

    def arrange(self, x: int, y: int) -> None:
        """Arranges children into a tower.

        Args:
            x: The x position this widget starts at.
            y: The y position this widget starts at.
        """
        children = self.visible_children

        width = self._framed_width - self.has_scrollbar(1)
        height = self._framed_height - self.has_scrollbar(0)

        x_alignment, y_alignment = self.alignment[0].value, self.alignment[1].value

        # Relative or static widths
        total = 0
        for widget in children:
            if widget.is_fill_height():
                continue

            widget.compute_dimensions(width, height)
            total += widget.computed_height

        # Fill heights
        autos = len([wdg for wdg in children if wdg.is_fill_height()])
        chunk, extra = divmod(self._framed_height - total, autos or 1)

        for widget in children:
            if not widget.is_fill_height():
                height = self._framed_height
            else:
                height = chunk + extra
                extra = 0

            widget.compute_dimensions(width, height)

            offset = self.computed_width - widget.computed_width

            if x_alignment == "end":
                widget.move_to(x + offset, y)

            elif x_alignment == "center":
                widget.move_to(x + offset // 2, y)

            else:
                widget.move_to(x, y)

            y += widget.computed_height

        # Aligning the result horizontally
        total = y
        offset = self._framed_height - total

        if offset > 0:
            if y_alignment == "start":
                offset = 0

            elif y_alignment == "center":
                offset //= 2

            for widget in children:
                widget.move_by(0, offset)


class Row(Container):
    """Arranges widgets in a horizontal row.

    ```
    +----------------------------+ <- alignment=("start", "center")
    |                            |
    |      +--------++----------+|
    |+----+|        ||          ||
    ||    ||        ||          ||
    |+----+|        ||          ||
    |  ^   +--------++----------+|
    |  |          ^         ^    |
    +--|----------|---------|----+
       |_ width=6 |         |
                  |_ width=0.3
                            |_ width=0.3
    ```
    """

    def arrange(self, x: int, y: int) -> None:
        """Arranges children into a row.

        Args:
            x: The x position this widget starts at.
            y: The y position this widget starts at.
        """

        children = self.visible_children

        width = self._framed_width - self.has_scrollbar(1)
        height = self._framed_height - self.has_scrollbar(0)

        x_alignment, y_alignment = self.alignment[0].value, self.alignment[1].value

        # Relative or static widths
        total = 0
        for widget in children:
            if widget.is_fill_width():
                continue

            widget.compute_dimensions(width, height)
            total += widget.computed_width

        # Fill widths
        autos = len([wdg for wdg in children if wdg.is_fill_width()])
        chunk, extra = divmod(width - total, autos or 1)

        for widget in children:
            if not widget.is_fill_width():
                width = self._framed_width
            else:
                width = chunk + extra
                extra = 0

            widget.compute_dimensions(width, height)

            offset = self.computed_width - widget.computed_width

            if y_alignment == "end":
                widget.move_to(x, y + offset)

            elif y_alignment == "center":
                widget.move_to(x, y + offset // 2)

            else:
                widget.move_to(x, y)

            x += widget.computed_width

        # Aligning the result horizontally
        total = x
        offset = self._framed_width - total

        if offset > 0:
            if x_alignment == "start":
                offset = 0

            elif x_alignment == "center":
                offset //= 2

            for widget in children:
                widget.move_by(offset, 0)
