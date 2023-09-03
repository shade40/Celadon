from __future__ import annotations

from typing import Iterable
from .widget import Widget, _overflows, _compute
from ..enums import MouseAction, Direction, Alignment

__all__ = [
    "Container",
    "Tower",
    "Row",
]


def _align(alignment: Alignment, available: int) -> tuple[int, int]:
    """Returns offset & modulo result for alignment in the available space."""

    available = max(available, 0)

    if available == 1:
        return 0, 0

    if alignment == Alignment.CENTER:
        return divmod(available, 2)

    if alignment == Alignment.END:
        return available, 0

    return 0, 0


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

    _direction: Direction = Direction.VERTICAL

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

    @property
    def direction(self) -> Direction:
        """Returns and sets the current flow direction."""

        return self._direction

    @direction.setter
    def direction(self, new: Direction | str) -> None:
        """Sets the direction setting."""

        if isinstance(new, str):
            new = Direction(new)

        self._direction = new

    def __iadd__(self, other: object) -> Container:
        if not isinstance(other, Widget):
            raise TypeError(
                f"Can only append widgets to containers, not {type(other)!r}."
            )

        self.append(other)
        return self

    def _is_fill(self, widget: Widget, horizontal: bool) -> bool:
        """Determines whether the widget is fill on the flow axis.

        Args:
            widget: The widget to test.
            horizontal: If set, flow direction is horizontal and we return `widget.is_fill_width()`,
                instead of `is_fill_height`.
        """

        if horizontal:
            return widget.is_fill_width()

        return widget.is_fill_height()

    def _compute_alignment_offsets(
        self,
        child: Widget,
        available_width: int,
        available_height: int,
        horizontal: bool,
    ) -> tuple[int, int, int]:
        """Computes x & y offsets to align by, based on alignment policies and flow direction.

        Args:
            child: The widget we are aligning. Used to get `computed_width` and `computed_height`
                as needed.
            available_width: The width the widget can be aligned within.
            available_height: The height the widget can be aligned within.
            horizontal: Whether flow direction is horizontal (True) or vertical (False).

        Returns:
            The x offset, y offset and the modulo of the operation that got either x offset or y offset,
                based on `horizontal`.
        """

        if horizontal:
            y, _ = _align(self.alignment[1], available_height - child.computed_height)
            x, extra = _align(self.alignment[0], available_width)

        else:
            x, _ = _align(self.alignment[0], available_width - child.computed_width)
            y, extra = _align(self.alignment[1], available_height)

        return x, y, extra

    def _compute_gap(self, available: int, count: int) -> tuple[int, int]:
        """Computes a gap based on available // count."""

        per_widget, extra = divmod(available, count)

        return _compute(self.gap, per_widget), extra

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

    @property
    def selected(self) -> Widget | None:
        """Returns the currently selected widget."""

        if self._selected_index is None:
            return None

        return self.children[self._selected_index]

    def select_offset(self, offset: int) -> bool:
        """Selects the widget at the given offset to the current selection."""

        if offset == 0:
            return False

        if self._selected_index is None:
            self._selected_index = 0

        current_selected = self.selected
        children_length = len(self.children)
        direction = offset // abs(offset)

        offset += direction

        while 0 < abs(offset):
            if self.selected.select_offset(offset):
                self.state_machine.apply_action("SELECTED")
                return True

            offset += -direction

            if not 0 <= self._selected_index + direction < children_length:
                break

            self._selected_index += direction

        self.state_machine.apply_action("UNSELECTED")
        return False

    def select_widget(self, widget: Widget) -> bool:
        for i, child in enumerate(self.children):
            if child.select_widget(widget):
                self.select_offset(i)
                return True

        self.state_machine.apply_action("UNSELECTED")
        return False

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
        """Arranges the widget's children according to its flow.

        Args:
            x: The origin's horizontal coordinate.
            y: The origin's vertical coordinate.
        """

        children = self.visible_children

        width = self._framed_width - self.has_scrollbar(1)
        height = self._framed_height - self.has_scrollbar(0)
        count = len(children)

        horizontal = self.direction == Direction.HORIZONTAL
        available = width if horizontal else height

        fills = 0

        for child in children:
            if self._is_fill(child, horizontal):
                fills += 1
                continue

            child.compute_dimensions(width, height)

            if horizontal:
                available -= child.computed_width
            else:
                available -= child.computed_height

        if fills != 0:
            gap = self.fallback_gap
            gap_extra = 0

        else:
            # To avoid div by 0
            fills = 1

            gap, gap_extra = self._compute_gap(available, count)

            if gap * (count - 1) >= available:
                gap = self.fallback_gap
                gap_extra = 0

        available -= gap * (count - 1) + gap_extra

        fill_size, fill_extra = divmod(available, fills)

        for child in children:
            if self._is_fill(child, horizontal):
                this_fill = fill_size + (1 if fill_extra > 0 else 0)
                fill_extra -= 1

                if horizontal:
                    child.compute_dimensions(this_fill, height)

                else:
                    child.compute_dimensions(width, this_fill)

            this_gap = gap + (1 if gap_extra > 0 else 0)
            gap_extra -= 1

            if horizontal:
                align_x, align_y, align_extra = self._compute_alignment_offsets(
                    child, this_gap, height, horizontal
                )

            else:
                align_x, align_y, align_extra = self._compute_alignment_offsets(
                    child, width, this_gap, horizontal
                )

            child.move_to(x + align_x, y + align_y)

            if horizontal:
                x += child.computed_width + this_gap + align_extra
                child.move_by(align_extra, 0)
            else:
                y += child.computed_height + this_gap + align_extra
                child.move_by(0, align_extra)

        if horizontal:
            self._outer_dimensions = (x, self.computed_height - this_gap - align_extra)
        else:
            self._outer_dimensions = (self.computed_width - this_gap - align_extra, y)

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
            # self.scroll = self.scroll[0], self.scroll[1] - 1
            self.select_offset(-1)
            return True

        if key == "down":
            # self.scroll = self.scroll[0], self.scroll[1] + 1
            self.select_offset(1)
            return True

        if key == "left":
            # self.scroll = self.scroll[0] - 1, self.scroll[1]
            self.select_offset(-1)
            return True

        if key == "right":
            self.select_offset(1)
            # self.scroll = self.scroll[0] + 1, self.scroll[1]
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
                # self.select_widget(widget)
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

    direction = Direction.VERTICAL


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

    direction = Direction.HORIZONTAL
