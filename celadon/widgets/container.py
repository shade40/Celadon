from __future__ import annotations

from typing import Any, Iterable, Iterator

from slate import Key, Span

from ..enums import Alignment, Direction, MouseAction
from .widget import Widget, _compute, handle_mouse_on_children

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


class Container(Widget):  # pylint: disable=too-many-public-methods
    """A widget that displays others based on some arrangement algorithm.

    See `Tower` and `Splitter` for the implementations you should use.
    """

    style_map = Widget.style_map | {
        "idle": {"scrollbar_y": ".secondary"},
        "hover": {"fill": Widget.style_map["idle"]["fill"]},
    }

    gap: int | float | None = None
    fallback_gap: int = 0

    def __init__(self, *children: Widget, **widget_args: Any) -> None:
        """Initializes a container.

        Args:
            *children: The children this widget should start with.
        """

        self.children: list[Widget] = []
        self.extend(children)

        super().__init__(**widget_args)

        self._should_layout = True
        self._mouse_target: Widget | None = None
        self._hover_target: Widget | None = None
        self._outer_dimensions = (1, 1)

    @property
    def visible_children(self) -> list[Widget]:
        """Returns all children without the 'hidden' group set."""

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

    @property
    def selectable_count(self) -> int:
        if self.disabled:
            return 0

        return sum(child.selectable_count for child in self.children)

    def __iadd__(self, other: object) -> Container:
        """Adds a widget to the Container.

        Analogous to `.append(other)`.
        """

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
            horizontal: If set, flow direction is horizontal and we return
                `widget.is_fill_width()`, instead of `is_fill_height`.
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
        """Computes x & y offsets to align by, based on alignment and flow direction.

        Args:
            child: The widget we are aligning. Used to get `computed_width` and
                `computed_height` as needed.
            available_width: The width the widget can be aligned within.
            available_height: The height the widget can be aligned within.
            horizontal: Whether flow direction is horizontal (True) or vertical (False).

        Returns:
            The x offset, y offset and the modulo of the operation that got either x
                offset or y offset, based on `horizontal`.
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

        per_widget, extra = divmod(available, count or 1)

        return _compute(self.gap, per_widget), extra

    def _compute_shrink_width(self) -> int:
        if self.direction is Direction.VERTICAL:
            return max([child.computed_width for child in self.children], default=0)

        gap = 0

        if isinstance(self.gap, int):
            gap = self.gap

        # TODO: This isn't accurate - fallback gap and all. Revisit with better layout.
        return sum(child.computed_width + gap for child in self.children) - gap

    def _compute_shrink_height(self) -> int:
        if self.direction is Direction.HORIZONTAL:
            return max([child.computed_height for child in self.children], default=0)

        # TODO: This isn't accurate - fallback gap and all. Revisit with better layout.
        gap = 0

        if isinstance(self.gap, int):
            gap = self.gap

        return sum(child.computed_height + gap for child in self.children) - gap

    @property
    def selected(self) -> Widget | None:
        return self._selected

    def select(self, index: int | None = None) -> int | None:
        if index == 0 or self.selectable_count == 0:
            return index

        possible_index = index

        if index is None:
            if self._selected is not None:
                self._selected.select(None)

            self._selected_index = None
            return None

        if self._selected is not None:
            self._selected.select(None)

        for widget in self.children:
            val = widget.select(index)
            index = val

            if index <= 0:
                self._selected = widget
                self._selected_index = possible_index
                self.state_machine.apply_action("SELECTED")
                break

        else:
            # We did not contain index, so we can unselect
            self._selected_index = None
            self.state_machine.apply_action("UNSELECTED")

        return max(index, 0)

    def serialize(self) -> dict[str, str]:
        data: dict[str, str] = {}

        for child in self.children:
            data.update(**child.serialize())

        return data

    def insert(self, index: int, widget: Widget) -> None:
        """Inserts a widget.

        Analogous to `list.insert`.
        """

        self.children.insert(index, widget)
        widget.parent = self
        self._should_layout = True

    def append(self, widget: Widget) -> None:
        """Adds a new widget setting its parent attribute to self.

        Analogous to `list.append`.
        """

        self.insert(len(self.children), widget)

    def extend(self, widgets: Iterable[Widget]) -> None:
        """Extends our children by the given iterable.

        Analogous to `list.extend`.
        """

        for widget in widgets:
            self.append(widget)

    def remove(self, widget: Widget) -> None:
        """Removes a widget from self, resetting its parent attribute to None.

        Analogous to `list.remove`.
        """

        self.children.remove(widget)

        widget.parent = None
        self._should_layout = True

        if self._mouse_target is widget:
            self._mouse_target = None

    def pop(self, index: int = -1) -> Widget:
        """Pops a widget from our children.

        Analogous to `list.pop`.

        Returns:
            The widget that was just removed.
        """

        widget = self.children[index]
        self.remove(widget)

        return widget

    def clear(self) -> None:
        """Removes all widgets.

        Analogous to `list.clear`.
        """

        for widget in self.children.copy():
            self.remove(widget)

    def update_children(self, widgets: Iterable[Widget]) -> None:
        """Updates our children to the given iterable.

        Analogous to `list.update`, doesn't use `update` because it is already a widget
        method.
        """

        self.clear()
        self.extend(widgets)

    def replace(self, current: Widget, new: Widget, *, offset: int = 0) -> None:
        """Replaces `current` in children to `new`."""

        index = self.children.index(current)

        self.children[index + offset] = new
        new.parent = self

    def move_by(self, x: int, y: int) -> None:
        """Moves the widget (and all its children) to the given position."""

        super().move_by(x, y)

        for child in self.children:
            child.move_by(x, y)

    def arrange(  # pylint: disable=too-many-locals,too-many-statements,too-many-branches
        self, x: int, y: int
    ) -> None:
        """Arranges the widget's children according to its flow.

        Args:
            x: The origin's horizontal coordinate.
            y: The origin's vertical coordinate.
        """

        origin = x, y

        children = self.visible_children

        width = self._framed_width - self.has_scrollbar(1)
        height = self._framed_height - self.has_scrollbar(0)
        count = len(children) - len([child for child in children if child.is_static()])

        horizontal = self.direction == Direction.HORIZONTAL
        available = width if horizontal else height

        fills = 0

        for child in children:
            if self._is_fill(child, horizontal):
                fills += 1
                continue

            child.compute_dimensions(width, height)

            if child.is_static():
                continue

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

        this_gap = 0
        align_extra = 0

        for child in children:
            if self._is_fill(child, horizontal):
                this_fill = fill_size + (1 if fill_extra > 0 else 0)
                fill_extra -= 1

                if horizontal:
                    child.compute_dimensions(this_fill, height)

                else:
                    child.compute_dimensions(width, this_fill)

            if child.is_static():
                continue

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
            self._outer_dimensions = (
                self.computed_width - this_gap - align_extra,
                y - origin[1],
            )

    def get_content(self) -> list[str]:
        """Calls our `arrange` method and returns a single empty line."""

        # layout_state = self._as_layout_state()

        # if layout_state != self._layout_state:
        start_x = self.position[0] + (self.frame.left != "")
        start_y = self.position[1] + (self.frame.top != "") + (self._clip_start or 0)

        if self._should_layout:
            self.arrange(start_x - self.scroll[0], start_y - self.scroll[1])
        # self._layout_state = layout_state

        return [""]

    def handle_keyboard(self, key: Key) -> bool:
        if self.selected is not None and self.selected.handle_keyboard(key):
            return True

        idx = self._selected_index or 0

        if key in ("left", "up", "shift-tab"):
            self.select(idx - 1)

        if key in ("right", "down", "tab"):
            self.select(idx + 1)

        return super().handle_keyboard(key)

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        result, mouse_target, hover_target = handle_mouse_on_children(
            action,
            position,
            self._mouse_target,
            self._hover_target,
            self.visible_children,
        )

        self._mouse_target = mouse_target
        self._hover_target = hover_target

        if result:
            index = 0

            for child in self.children:
                if child is mouse_target:
                    index += child.selected_index or 1
                    self.select(index)

                    return True

                index += child.selectable_count

            return True

        # There was a click, but it didn't get handled; likely clicked on a
        # non-selectable, or empty space.
        if "click" in action.value:
            self.select(None)

        return super().handle_mouse(action, position)

    def drawables(self) -> Iterator[Widget]:
        # TODO: Implement child-clipping

        yield self

        for widget in sorted(self.children, key=lambda w: w.layer):
            yield from widget.drawables()

    def build(
        self, *, virt_width: int | None = None, virt_height: int | None = None
    ) -> list[tuple[Span, ...]]:
        my_virt_width, my_virt_height = self._outer_dimensions

        return super().build(virt_width=my_virt_width, virt_height=my_virt_height)


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

    _direction = Direction.VERTICAL


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

    _direction = Direction.HORIZONTAL
