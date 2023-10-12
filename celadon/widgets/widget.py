# pylint: disable=too-many-lines
from __future__ import annotations

import uuid
import re

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Generator, Type, Iterable, Literal, TYPE_CHECKING

from slate import Event, Span, Terminal, Key
from slate.span import EMPTY_SPAN
from zenith.markup import zml_pre_process, zml_get_spans, FULL_RESET

from ..enums import Alignment, Overflow, MouseAction, Positioning
from ..frames import Frame, get_frame
from ..style_map import StyleMap
from ..state_machine import StateMachine

if TYPE_CHECKING:
    from ..application import Application, Page

__all__ = ["Widget", "widget_types", "handle_mouse_on_children"]

RE_FULL_UNSETTER = re.compile(r"\/(?=\]| )")


@dataclass
class BoundStyle:
    """A callable object containing both style and fill markup."""

    style: str
    fill: str

    def __call__(self, item: str) -> str:
        return f"[{self.fill}{self.style}]{item}"


def _compute(spec: int | float | None, hint: int) -> int:
    if isinstance(spec, float):
        return int(spec * hint)

    # Auto (fill available)
    if spec is None:
        return hint

    # Static (int)
    return spec


def _build_scrollbar(
    rail: str, thumb: str, size: int, current: float, ratio: float
) -> Generator[str, None, None]:
    """Builds the characters for a scrollbar.

    Args:
        rail: The character used for the 'rail' of the scrollbar.
        thumb: The character used for the 'thumb' of the scrollbar.
        size: The total available size for the scrollbar to follow.
        current: The current value/position of the scrollbar, 0-1.
        ratio: The visible ('viewport') size divided by the total ('virtual') size.

    Yields:
        `rail` or `thumb`, depending on which character comes next, a total of `size`
        times.
    """

    thumb_length = int(size * ratio)
    move_area = size - thumb_length

    thumb_center = int(current * move_area)
    half_thumb, offset = divmod(thumb_length, 2)
    thumb_center += half_thumb

    thumb_start = thumb_center - half_thumb
    thumb_end = thumb_center + half_thumb + offset

    if thumb_end >= size - 1:
        thumb_end = size
        thumb_start = thumb_end - thumb_length - offset

    for i in range(size):
        if thumb_start <= i <= thumb_end:
            yield thumb
            continue

        yield rail


def _overflows(real: int, virt: int) -> bool:
    """Determines whether the given real and virtual dimensions overflow."""

    return real / max(virt, 1) <= 1.0


class Widget:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """This is a docstring."""

    width: int | float | None
    """The hint used by the widget to calculate it's width. See dimension hints."""

    height: int | float | None
    """The hint used by the widget to calculate it's height. See dimension hints."""

    computed_width: int
    """The current width of the widget, calculated from `width`'s hint."""

    computed_height: int
    """The current height of the widget, calculated from `height`'s hint."""

    scroll: tuple[int, int]
    """The widget's (horizontal, vertical) scrolling offset."""

    position: tuple[int, int]
    """The widget's (horizontal, vertical) position."""

    app: "Application"
    """The most recently run Application instance."""

    scroll_step: int = 1

    state_machine = StateMachine(
        states=("idle", "hover", "selected", "active"),
        transitions={
            "idle": {
                "HOVERED": "hover",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "hover": {
                "RELEASED": "idle",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "selected": {
                "UNSELECTED": "idle",
                "CLICKED": "active",
            },
            "active": {
                "RELEASED": "hover",
                "RELEASED_KEYBOARD": "selected",
            },
            "/": {
                "SUBSTATE_ENTER_SCROLLING_X": "/scrolling_x",
                "SUBSTATE_ENTER_SCROLLING_Y": "/scrolling_y",
            },
            "/scrolling_x": {
                "SUBSTATE_EXIT_SCROLLING_X": "/",
            },
            "/scrolling_y": {
                "SUBSTATE_EXIT_SCROLLING_Y": "/",
            },
        },
    )
    """The state machine keeps track of the current state of the widget.

    It has a tuple of possible states, and a mapping of:

        {current_state: {action: resulting_state, ...}

    ...that are used for state-transitions.
    """

    style_map = StyleMap(
        {
            "idle": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text-1",
                "scrollbar_x": "ui.panel1+3*0.2",
                "scrollbar_y": "ui.panel1+3*0.2",
            },
            "hover": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text-1",
                "scrollbar_x": "ui.panel1+3*0.2",
                "scrollbar_y": "ui.panel1+3*0.2",
            },
            "selected": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text+1",
                "scrollbar_x": "ui.panel1+3*0.2",
                "scrollbar_y": "ui.panel1+3*0.2",
            },
            "active": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text-1",
                "scrollbar_x": "ui.panel1+3*0.2",
                "scrollbar_y": "ui.panel1+3*0.2",
            },
            "/scrolling_x": {
                "scrollbar_x": "ui.primary",
            },
            "/scrolling_y": {
                "scrollbar_y": "ui.primary",
            },
        }
    )
    """The style map is the lookup table for the widget's styles at certain states."""

    rules = ""
    """YAML rules for this widget, applied only when added as part of an Application."""

    _frame: Frame

    def __init__(
        self,
        eid: str | None = None,
        group: str | None = None,
        groups: tuple[str, ...] = tuple(),
    ) -> None:
        """Initializes a Widget.

        Args:
            eid: The id for this widget. Defaults to a UUID.
            group: If set, `groups` is overwritten as `(group,)`.
            groups: The initial groups this widget will belong to.
        """

        self.eid = eid or str(uuid.uuid4())
        if group is not None:
            groups = (group,)
        self.groups = groups
        self.scroll = (0, 0)
        self.position = (0, 0)
        self.state_machine = deepcopy(self.state_machine)
        self.parent: Widget | "Page" | None = None

        self.width: int | float | None = None
        self.height: int | float | None = None
        # These conversions are handled in their properties
        self.frame = get_frame(None)  # type: ignore
        self.alignment = ("start", "start")  # type: ignore
        self.overflow = ("hide", "hide")  # type: ignore
        self.positioning = Positioning.DYNAMIC

        self._virtual_width = 0
        self._virtual_height = 0
        self._last_query: str | None = None
        self._selected_index: int | None = None

        self._clip_start: int | None = None
        self._clip_end: int | None = None
        self._bindings: dict[str, Event] = {}

        self.computed_width = 1
        self.computed_height = 1

        self.pre_content = Event("pre content")
        self.on_content = Event("post content")

        self.pre_build = Event("pre build")
        self.on_build = Event("post build")

        self.setup()

        widget_types[type(self).__name__] = type(self)

    @property
    def terminal(self) -> Terminal | None:
        """Returns the app's terminal."""

        if self.app is None:
            return None

        return self.app.terminal

    @property
    def state(self) -> str:
        """Returns the current state of the widget."""

        return self.state_machine()

    @property
    def styles(self) -> dict[str, BoundStyle]:
        """Returns a dictionary of current state's style keys to bound styles.

        Note that the `fill` style is inserted into every other style, and is
        stored under the `_fill` key for special circumstances where you may
        need to reference it.
        """

        styles = self.style_map[self.state.split("/")[0]].copy()

        if "/" in self.state:
            key = "/" + self.state.split("/")[-1]

            if key in self.style_map:
                styles |= self.style_map[key].items()

        output = {}
        fill = styles["fill"]

        if fill != "":
            fill += " "

        for key, style in styles.items():
            if key == "fill":
                key = "_fill"

            output[key] = BoundStyle(style, fill)

        return output

    @property
    def selected_index(self) -> int | None:
        """Returns the currently selected child's index."""

        return self._selected_index

    @property
    def selected(self) -> Widget | None:
        """Returns the currently selected widget."""

        if self.selected_index is None:
            return None

        return self

    @property
    def selectables(self) -> list[tuple[Widget, int]]:
        """Generates a list of tuples for selecting by the parent.

        See Container's selectables for more info.
        """

        return [(self, 0)]

    @property
    def selectable_count(self) -> int:
        """Returns the amount of selectable objects this widget has within."""

        return len(self.selectables)

    @property
    def frame(self) -> Frame:
        """Returns and sets the current frame."""

        return self._frame

    @frame.setter
    def frame(self, new: str | tuple[str, str, str, str] | Type[Frame]) -> None:
        """Sets the frame setting."""

        if isinstance(new, tuple):
            sides = tuple(get_frame(side) for side in new)
            self._frame = Frame.compose(sides)  # type: ignore
            return

        if isinstance(new, str) or new is None:
            new = get_frame(new)

        self._frame = new()

    @property
    def alignment(self) -> tuple[Alignment, Alignment]:
        """Returns and sets the current alignment settings.

        Args:
            new: A tuple of either two strings (start, center, end) or two alignment
                constants.
        """

        return self._alignment

    @alignment.setter
    def alignment(self, new: tuple[Alignment, Alignment] | tuple[str, str]) -> None:
        """Sets the alignment setting."""

        if not all(isinstance(item, Alignment) for item in new):
            new = Alignment(new[0]), Alignment(new[1])

        assert isinstance(new[0], Alignment) and isinstance(new[1], Alignment)
        self._alignment = new

    @property
    def overflow(self) -> tuple[Overflow, Overflow]:
        """Returns and sets the current overflow settings.

        Args:
            new: A tuple of either two strings (start, center, end) or two alignment
                constants.
        """

        return self._overflow

    @overflow.setter
    def overflow(self, new: tuple[Overflow, Overflow] | tuple[str, str]) -> None:
        """Sets the overflow setting."""

        if not all(isinstance(item, Overflow) for item in new):
            new = Overflow(new[0]), Overflow(new[1])

        assert isinstance(new[0], Overflow) and isinstance(new[1], Overflow)
        self._overflow = new

    @property
    def positioning(self) -> Positioning:
        """Returns and sets the positioning strategy."""

        return self._positioning

    @positioning.setter
    def positioning(self, new: str | Positioning) -> None:
        """Sets the positioning strategy."""

        if isinstance(new, str):
            new = Positioning(new)

        self._positioning = new

    @property
    def _framed_width(self) -> int:
        """Gets the widget's width excluding its frame."""

        return max(self.computed_width - self.frame.width, 0)

    @property
    def _framed_height(self) -> int:
        """Gets the widget's height excluding its frame."""

        return max(self.computed_height - self.frame.height, 0)

    @lru_cache(1024)
    def _parse_markup(self, markup: str) -> tuple[Span, ...]:
        """Parses some markup into a span of tuples.

        This also handles (ignores) zenith's FULL_RESET spans, and replaces `/`
        unsetters with `/ {fill_style} {content_style}`.
        """

        fill = self.styles["_fill"]

        if isinstance(self.parent, Widget) and fill.style == "":
            fill = self.parent.styles["_fill"]

        content_style = fill.style + " " + self.styles["content"].style

        # Replace full unsetters with full unsetter + content style
        markup = RE_FULL_UNSETTER.sub("/ " + content_style, markup)
        markup = zml_pre_process(markup)

        return tuple(span for span in zml_get_spans(markup) if span is not FULL_RESET)

    def _add_scrollbars(  # pylint: disable=too-many-arguments
        self,
        lines: list[tuple[Span, ...]],
        width: int,
        height: int,
        scrollbar_x: bool,
        scrollbar_y: bool,
    ) -> None:
        """Adds scrollbars to the given lines."""

        if scrollbar_x:
            buff = "".join(
                list(
                    _build_scrollbar(
                        *self.frame.scrollbars[0],
                        size=width - scrollbar_y,
                        current=self.scroll[0] / max(self._virtual_width - width, 1),
                        ratio=width / self._virtual_width,
                    )
                )
            )

            lines[-1] = self._parse_markup(
                self.styles["scrollbar_x"](buff + " " * scrollbar_y)
            )

        if scrollbar_y:
            chars = list(
                _build_scrollbar(
                    *self.frame.scrollbars[1],
                    size=height - scrollbar_x,
                    current=self.scroll[1] / max(self._virtual_height - height, 1),
                    ratio=height / self._virtual_height,
                )
            )

            for i, line in enumerate(lines):
                if i >= height - scrollbar_x:
                    break

                span = line[-1]

                lines[i] = (
                    *line[:-1],
                    span.mutate(text=span.text[:-1]),
                    *(self._parse_markup(self.styles["scrollbar_y"](chars[i]))),
                )

    def _apply_frame(  # pylint: disable=too-many-locals
        self, lines: list[tuple[Span, ...]], width: int
    ) -> None:
        """Adds frame characters around the given lines."""

        def _style(item, outer: bool = False) -> tuple[Span, ...]:
            style = deepcopy(self.styles["frame"])

            if outer:
                if self.parent is not None and hasattr(self.parent, "styles"):
                    style.style = self.parent.styles["frame"].fill + " " + style.style

            return self._parse_markup(style(item))

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        h_outer = self.frame.outer_horizontal
        v_outer = self.frame.outer_vertical
        c_outer = self.frame.outer_corner

        for i, line in enumerate(lines):
            lines[i] = (
                *_style(left, outer=v_outer),
                *line,
                *_style(right, outer=v_outer),
            )

        if left_top + top + right_top != "":
            lines.insert(
                0,
                (
                    *_style(left_top, outer=c_outer),
                    *_style(top * width, outer=h_outer),
                    *_style(right_top, outer=c_outer),
                ),
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (
                    *_style(left_bottom, outer=c_outer),
                    *_style(bottom * width, outer=h_outer),
                    *_style(right_bottom, outer=c_outer),
                )
            )

    def _horizontal_align(self, line: tuple[Span, ...], width: int) -> tuple[Span, ...]:
        """Aligns a tuple of spans horizontally, using `self.alignment[0]`."""

        alignment = self.alignment[0]

        width = max(width, self._virtual_width)
        length = sum(len(span.text) for span in line)
        diff = width - length

        style = self.styles["content"]

        if line in [tuple(), (Span(""),)]:
            return self._parse_markup(style(diff * " "))

        if alignment is Alignment.START:
            return (*line[:-1], line[-1].mutate(text=line[-1].text + diff * " "))

        if alignment is Alignment.CENTER:
            end, extra = divmod(diff, 2)
            start = end + extra

            # Return padding as a single span instead of (start, content, end)
            # when content is " " (filler lines)
            if "".join(span.text for span in line) == " ":
                return self._parse_markup(style((start + end) * " "))

            return (
                *self._parse_markup(style(start * " ")),
                line[0],
                *line[1:],
                *self._parse_markup(style(end * " ")),
            )

        if alignment is Alignment.END:
            span = line[0]

            return (span.mutate(text=diff * " " + span.text), *line[1:])

        raise NotImplementedError(f"Unknown alignment {alignment!r}.")

    def _vertical_align(self, lines: list[tuple[Span, ...]], height: int) -> None:
        """Aligns a list of tuples of spans vertically, using `self.alignment[1]`.

        Note that this mutates `lines`.
        """

        alignment = self.alignment[1]

        available = height - len(lines)
        filler = self._parse_markup(self.styles["content"](" "))

        if alignment is Alignment.START:
            lines.extend([filler] * available)
            return

        if alignment is Alignment.CENTER:
            top, extra = divmod(available, 2)
            bottom = top + extra

            for _ in range(top):
                lines.insert(0, filler)

            lines.extend([filler] * bottom)
            return

        for _ in range(available):
            lines.insert(0, filler)

    @lru_cache(1024)
    def _slice_line(
        self, line: tuple[Span, ...], start: int, end: int
    ) -> tuple[Span, ...]:
        """Slices a line into the given width."""

        if end is None:
            end = len(line) - 1

        width = end - start

        line_list = []
        before_start = 0
        occupied = 0

        for span in line:
            length = len(span)

            before_start += length
            if before_start < start:
                continue

            new = span[max(start - (before_start - length), 0) :]
            length = len(new)

            line_list.append(new)

            occupied += length

            if occupied > width:
                break

        width_diff = max(occupied - width, 0)

        if width_diff > 0 and len(line_list) > 0:
            for i, span in enumerate(reversed(line_list)):
                new = span[:-width_diff]
                width_diff -= len(span) - len(new)

                line_list[-i - 1] = new

                if width_diff <= 0:
                    break

        if not line_list:
            line_list.extend(self._parse_markup(self.styles["content"](" ")))

        occupied = sum(len(span) for span in line_list)

        if occupied < width:
            suffix = line_list[-1]

            line_list[-1] = suffix.mutate(text=suffix.text + (width - occupied) * " ")

        return tuple(line_list)

    def _apply_mouse_state(self, action: MouseAction) -> None:
        """Applies a state change action based on mouse input."""

        value = action.value

        if "click" in value:
            self.state_machine.apply_action("CLICKED")
            self.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_X")
            self.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_Y")
            return

        if "release" in value:
            self.state_machine.apply_action("RELEASED")
            self.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_X")
            self.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_Y")

            if self.selected_index is not None:
                self.state_machine.apply_action("SELECTED")

            return

        if "hover" in value:
            self.state_machine.apply_action("HOVERED")
            return

    def setup(self) -> None:
        """Use this to do simple setup actions without overriding __init__."""

    def serialize(self) -> dict[str, Any]:
        """Returns a dictionary to represent the dynamic value of the widget."""

        return {}

    def update(
        self,
        attrs: dict[str, Any],
        style_map: dict[str, str],
    ) -> None:
        """Updates a widget with new setttings.

        Args:
            attrs: A dictionary of the widget's fields to values. Fields starting with
                `_` are disallowed, as are fields the widget doesn't already have.
            style_map: A dictionary of style keys to markup that gets merged onto our
                `style_map`'s current state, i.e.:

                    `self.style_map | {self.state: style_map}`
        """

        keys = dir(self)

        for key, value in attrs.items():
            if key.startswith("_"):
                raise ValueError(f"cannot set non-public attr {key!r}")

            if key not in keys:
                raise ValueError(f"cannot set non-existant attr {key!r}")

            setattr(self, key, value)

        self.style_map = self.style_map | {self.state: style_map}

    def as_query(self, state: bool = False) -> str:
        """Returns the widget as the most specific selectable query.

        Args:
            state: Include state suffix onto the query.
        """

        query = type(self).__name__

        if self.eid is not None:
            query += f"#{self.eid}"

        for variant in self.groups:
            query += f".{variant}"

        if state:
            query += f"/{self.state}"

        return query

    def query_changed(self) -> bool:
        """Returns whether the result of `as_query` has changed since last call."""

        query = self.as_query(state=True)
        value = query != self._last_query

        self._last_query = query
        return value

    def is_static(self) -> bool:
        """Shorthand for `positioning is Positioning.STATIC`."""

        return self.positioning is Positioning.STATIC

    def is_dynamic(self) -> bool:
        """Shorthand for `positioning is Positioning.DYNAMIC`."""

        return self.positioning is Positioning.DYNAMIC

    def is_fill_width(self) -> bool:
        """Shorthand for `width is None`."""

        return self.width is None

    def is_fill_height(self) -> bool:
        """Shorthand for `height is None`."""

        return self.height is None

    def scroll_to(self, x: int | None = None, y: int | None = None) -> None:
        """Scrolls the widget.

        Both arguments may be given in one of four forms:

        - `0`: scroll to the start of the widget on the given axis
        - `-1`: scroll to the end of the widget on the given axis
        - `0<` : scroll to the offset on the given axis
        - `None`: do nothing for the given axis.

        Args:
            x: The x scroll value.
            y: The y scroll value.
        """

        new_x = x if x is not None else self.scroll[0]

        if new_x == -1:
            new_x = self._virtual_width

        new_y = y if y is not None else self.scroll[1]

        if new_y == -1:
            new_y = self._virtual_height

        self.scroll = (new_x, new_y)

    def has_scrollbar(self, index: Literal[0, 1]) -> bool:
        """Returns whether the given dimension should display a scrollbar.

        Args:
            index: The axis to check. 0 for horizontal scrolling, 1 for vertical.
        """

        real, virt = [
            (self._framed_width, self._virtual_width),
            (self._framed_height, self._virtual_height),
        ][index]

        return self.overflow[index] is Overflow.SCROLL or (
            self.overflow[index] is Overflow.AUTO and _overflows(real, virt)
        )

    def drawables(self) -> Iterable[Widget]:
        """Yields all contained widgets that should be drawn."""

        yield self

    def clip_height(self, start: int | None, end: int | None) -> None:
        """Sets the clipping rectangle's coordinates."""

        self._clip_start = start
        self._clip_end = end

    def add_group(self, target: str) -> None:
        """Adds a group to the widget's groups."""

        self.groups = tuple(list(self.groups) + [target])

    def remove_group(self, target: str) -> None:
        """Removes a group from the widget's groups."""

        self.groups = tuple(group for group in self.groups if group != target)

    def toggle_group(self, target: str) -> bool:
        """Toggles a group in the widget's groups."""

        if target in self.groups:
            self.remove_group(target)
            return False

        self.add_group(target)
        return True

    def select(self, index: int | None = None) -> None:
        """Selects a part of this Widget.

        Args:
            index: The index to select.

        Raises:
            TypeError: This widget has no selectables, i.e. widget.is_selectable == False.
        """

        if index is not None:
            index = min(max(0, index), self.selectable_count - 1)

        self._selected_index = index
        self.state_machine.apply_action(("UN" if index is None else "") + "SELECTED")

    def hide(self) -> None:
        """Adds the `hidden` group onto the widget."""

        self.add_group("hidden")

    def show(self) -> None:
        """Remove the `hidden` group from the widget."""

        self.remove_group("hidden")

    def contains(self, position: tuple[int, int]) -> bool:
        """Determines whether this widget contains the given position."""

        rect = self.position, (
            self.position[0] + self.computed_width - self.has_scrollbar(1),
            self.position[1] + self.computed_height - self.has_scrollbar(0),
        )

        (left, top), (right, bottom) = rect

        return left < position[0] <= right and top < position[1] <= bottom

    def move_to(self, x: int, y: int) -> None:
        """Moves the widget to the given position."""

        self.position = x, y

    def move_by(self, x: int, y: int) -> None:
        """Moves the widget by the given changes."""

        self.move_to(self.position[0] + x, self.position[1] + y)

    def bind(self, key: str, callback: Callable[[], Any]) -> Event:
        """Binds a key to the given callback.

        If a binding already exists, the given callback is added to the Event.
        """

        if key not in self._bindings:
            self._bindings[key] = Event(f"on key {key}")

        event = self._bindings[key]
        event += callback

        return event

    def unbind(self, key: str) -> Event:
        """Removes all bindings for a given key."""

        if key not in self._bindings:
            raise ValueError(f"can't remove non-existant binding for key {key!r}.")

        event = self._bindings[key]
        del self._bindings[key]

        return event

    def handle_keyboard(self, key: Key) -> bool:
        """Handles a keyboard event.

        Returns:
            Whether the event should continue to bubble upwards. Return `True` if the
            event was already handled.
        """

        result = False

        for value in key:
            if value in self._bindings:
                if self._bindings[value](self):
                    result |= True

            if result:
                break

        return result

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        """Handles a mouse event.

        Returns:
            Whether the event should continue to bubble upwards. Return `True` if the
            event was already handled.
        """

        self._apply_mouse_state(action)

        if "scroll" in action.value:
            can_scroll_x, can_scroll_y = self.has_scrollbar(0), self.has_scrollbar(1)
            if (
                can_scroll_x
                and action is MouseAction.SCROLL_LEFT
                or action is MouseAction.SHIFT_SCROLL_UP
            ):
                self.scroll = (self.scroll[0] - self.scroll_step, self.scroll[1])

            elif (
                can_scroll_x
                and action is MouseAction.SCROLL_RIGHT
                or action is MouseAction.SHIFT_SCROLL_DOWN
            ):
                self.scroll = (self.scroll[0] + self.scroll_step, self.scroll[1])

            elif can_scroll_y and action is MouseAction.SCROLL_UP:
                self.scroll = (self.scroll[0], self.scroll[1] - self.scroll_step)

            elif can_scroll_y and action is MouseAction.SCROLL_DOWN:
                self.scroll = (self.scroll[0], self.scroll[1] + self.scroll_step)

        def _get_names(action: MouseAction) -> tuple[str, ...]:
            if action.value == "hover":
                return (action.value,)

            parts = action.value.split("_")

            full = action.value
            alt_key = "_".join(parts[-2:])
            event = parts[-1]

            if alt_key in ["left", "right"]:
                return (full, alt_key, event)

            return (full, event)

        possible_names = _get_names(action)

        for name in possible_names:
            if hasattr(self, f"on_{name}"):
                handle = getattr(self, f"on_{name}")

                return handle(action, position)

        return False

    def compute_dimensions(self, available_width: int, available_height: int) -> None:
        """Computes width & height based on our specifications and the given space."""

        self.computed_width = _compute(self.width, available_width)
        self.computed_height = _compute(self.height, available_height)

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(
        self, *, virt_width: int | None = None, virt_height: int | None = None
    ) -> list[tuple[Span, ...]]:
        """Builds the strings that represent the widget."""

        self.pre_build()

        width = self._framed_width
        height = self._framed_height

        def _clamp_scrolls() -> tuple[int, int]:
            x_bar = _overflows(width, self._virtual_width)
            y_bar = _overflows(height, self._virtual_height)

            return (
                max(min(self.scroll[0], self._virtual_width - width + x_bar), 0),
                max(min(self.scroll[1], self._virtual_height - height + y_bar), 0),
            )

        self.scroll = _clamp_scrolls()

        content_style = self.styles["content"]

        self.pre_content()

        lines: list[tuple[Span, ...]] = [
            self._parse_markup(content_style(line)) for line in self.get_content()
        ]

        self.on_content()

        self._virtual_height = virt_height or len(lines)
        self._virtual_width = virt_width or max(
            sum(len(span) for span in line) for line in lines
        )

        # Clip into vertical size
        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]

            if len(lines) < height:
                lines.extend([(EMPTY_SPAN,)] * (height - len(lines)))

        # Handle alignment
        self._vertical_align(lines, height)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width)

        # Clip into horizontal size
        lines = [
            self._slice_line(line, self.scroll[0], self.scroll[0] + width)
            for line in lines
        ]

        # Composite together frame + content + scrollbar
        horiz_bar = self.has_scrollbar(0)
        vert_bar = self.has_scrollbar(1)

        if horiz_bar or vert_bar:
            self._add_scrollbars(lines, width, height, horiz_bar, vert_bar)

        self._apply_frame(lines, width)

        if len(lines) > self.computed_height:
            lines = lines[: self.computed_height]

        lines = lines[self._clip_start : self._clip_end]

        self.on_build()

        return lines


widget_annotations = Widget.__annotations__
widget_types: dict[str, Type[Widget]] = {"Widget": Widget}


def handle_mouse_on_children(
    action: MouseAction,
    position: tuple[int, int],
    mouse_target: Widget | None,
    hover_target: Widget | None,
    children: Iterable[Widget],
) -> tuple[bool, int | None, Widget | None, Widget | None]:
    """Handles the given mouse event on an iterable of widgets.

    This can be used by 'container' type widgets (like `Container`), or meta-level
    management objects (like `Application`) for consistent mouse handling behaviour.

    Args:
        action: The action associated with the event.
        position: The position associated with the event.
        mouse_target: The caller's current mouse target.
        hover_target: The caller's current hover target.
        children: The widgets to execute upon.

    Returns:
        A tuple of:

            (success, selection_index, mouse_target, hover_target)

        Since this function doesn't have access to the caller, the caller has to set
        its mouse & hover targets to the returned values. `selection_index` is only set
        when a new widget handled the event & is selectable, so should be ignored when
        set to None.
    """

    if action is MouseAction.LEFT_RELEASE:
        if mouse_target is not None:
            mouse_target.handle_mouse(action, position)
            mouse_target = None

        if hover_target is not None:
            hover_target.handle_mouse(action, position)
            hover_target = None

        return True, None, mouse_target, hover_target

    is_hover = action is MouseAction.HOVER
    release = MouseAction.LEFT_RELEASE, position

    if (
        mouse_target is not None
        and "click" not in action.value  # Clicks cannot be done outside of the widget
        and mouse_target.handle_mouse(action, position)
    ):
        return True, None, mouse_target, hover_target

    if is_hover and hover_target is not None and not hover_target.contains(position):
        hover_target.handle_mouse(*release)
        hover_target = None

    selection = 0

    for child in children:
        selection += child.selectable_count

        if not child.contains(position):
            continue

        if is_hover:
            if hover_target is not None and hover_target is not child:
                hover_target.handle_mouse(*release)

            hover_target = child

        if child.handle_mouse(action, position):
            selection -= child.selectable_count - (child.selected_index or 0)

            if mouse_target is not None and mouse_target is not child:
                mouse_target.handle_mouse(*release)

            mouse_target = child

            return True, selection, mouse_target, hover_target

        break

    return False, None, mouse_target, hover_target
