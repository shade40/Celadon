from __future__ import annotations

from typing import Iterable
from .widget import Widget, _overflows, _compute
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

    gap: int | float | None = None
    fallback_gap: int | float = 1

    def __init__(self, *children: Widget, **widget_args: Any) -> None:
        self.children = []
        for child in children:
            self.append(child)

        super().__init__(**widget_args)

        self._should_layout = False
        self._layout_state: int = -1
        self._mouse_target: Widget | None = None
        self._outer_dimensions = (1, 1)

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
        virt_width, virt_height = self._outer_dimensions

        return super().build(virt_width=virt_width, virt_height=virt_height)


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

    # TODO: As this and Row's are practically identical, we should probably abstract it.
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

        # Compute non-fill heights, count fill heights
        fills = 0
        non_fills = 0
        occupied = 0

        for child in children:
            if child.is_fill_height():
                fills += 1
                continue

            child.compute_dimensions(width, height)
            occupied += child.computed_height
            non_fills += 1

        # Compute gaps
        remaining = height - occupied

        if self.gap is None and fills != 0:
            gap = self.fallback_gap
        else:
            gap = _compute(self.gap, remaining // non_fills)

        fill_height, extra = divmod(
            remaining - gap * (fills + non_fills), max(fills, 1)
        )

        # Arrange children
        for child in children:
            if child.is_fill_height():
                child.compute_dimensions(width, fill_height + extra)
                extra = 0

            align_x = 0
            align_width = width - child.computed_width

            if x_alignment == "center":
                align_x = sum(divmod(align_width, 2))

            elif x_alignment == "end":
                align_x = align_width

            align_y = 0

            if y_alignment == "center":
                align_y = sum(divmod(gap, 2))

            elif y_alignment == "end":
                align_y = gap

            child.move_to(x + align_x, y + align_y)
            y += child.computed_height + gap

        self._outer_dimensions = (self.computed_width, y)


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

        # Compute non-fill widths, count fill widths
        fills = 0
        non_fills = 0
        occupied = 0

        for child in children:
            if child.is_fill_width():
                fills += 1
                continue

            child.compute_dimensions(width, height)
            occupied += child.computed_width
            non_fills += 1

        # Compute gaps
        remaining = width - occupied

        if self.gap is None and fills != 0:
            gap = self.fallback_gap
        else:
            gap = _compute(self.gap, remaining // non_fills)

        fill_width, extra = divmod(remaining - gap * (fills + non_fills), max(fills, 1))

        # Arrange children
        for child in children:
            if child.is_fill_width():
                child.compute_dimensions(fill_width + extra, height)
                extra = 0

            align_y = 0
            align_height = height - child.computed_height

            if y_alignment == "center":
                align_y = sum(divmod(align_height, 2))

            elif y_alignment == "end":
                align_y = align_height

            align_x = 0

            if x_alignment == "center":
                align_x = sum(divmod(gap, 2))

            elif x_alignment == "end":
                align_x = gap

            child.move_to(x + align_x, y + align_y)
            x += child.computed_width + gap

        self._outer_dimensions = (x, self.computed_height)
