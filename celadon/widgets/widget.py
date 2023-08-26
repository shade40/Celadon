from __future__ import annotations

import uuid
import re

from copy import deepcopy
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Generator,
    Type,
    Iterable,
    Literal,
    Union,
    Protocol,
    TypedDict,
    TYPE_CHECKING,
)

from slate import Event, Span
from zenith.markup import zml_pre_process, zml_get_spans, FULL_RESET

from ..enums import Alignment, Overflow, MouseAction
from ..frames import Frame, get_frame
from ..style_map import StyleMap
from ..state_machine import StateMachine

if TYPE_CHECKING:
    from ..application import Application

__all__ = ["Widget", "widget_types"]

RE_FULL_UNSETTER = re.compile(r"\/(?=\]| )")


class Sized(Protocol):
    """An object that has size attributes."""

    width_hint: int
    height_hint: int


@dataclass
class BoundStyle:
    style: str
    fill: str

    def __call__(self, item: str) -> str:
        return f"[{self.fill}{self.style}]{item}"


DimensionSpec = Union[int, float, None]
AlignmentSetting = Literal["start", "center", "end"]
OverflowSetting = Literal["hide", "auto", "scroll"]


class Config(TypedDict):
    width: int | float | None
    height: int | float | None

    frame: str

    alignment: tuple[AlignmentSetting, AlignmentSetting]
    overflow: tuple[OverflowSetting, OverflowSetting]


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


class Widget:  # pylint: disable=too-many-instance-attributes
    """This is a docstring."""

    on_state_change: Event
    """Called when the widget's state changes.

    Args:
        state: The new state.
    """

    parent: Sized | None
    """The parent of this widget.

    An application instance if the widget is at the root, another widget otherwise.
    """

    app: Application | None = None
    """A reference to the current (latest-started) application instance."""

    # TODO: Update these!
    width_hint: int
    """The hint the widget uses to calculate its width. See dimension hint"""
    # TODO: Add dimension hint docs

    height_hint: int
    """The hint the widget uses to calculate its height. See dimension hint"""

    scroll: tuple[int, int]
    """The widget's (horizontal, vertical) scrolling offset."""

    position: tuple[int, int]
    """The widget's (horizontal, vertical) position."""

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
                "scrollbar_x": "ui.panel1-1",
                "scrollbar_y": "ui.panel1-1",
            },
            "hover": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text-1",
                "scrollbar_x": "ui.panel1-1",
                "scrollbar_y": "ui.panel1-1",
            },
            "selected": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text+1",
                "scrollbar_x": "ui.panel1-1",
                "scrollbar_y": "ui.panel1-1",
            },
            "active": {
                "fill": "@ui.panel1-3",
                "frame": "ui.panel1+1",
                "content": "ui.text-1",
                "scrollbar_x": "ui.panel1-1",
                "scrollbar_y": "ui.panel1-1",
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

    def __init__(
        self,
        eid: str | None = None,
        group: str | None = None,
        groups: tuple[str] = tuple(),
    ) -> None:
        """Initializes a Widget.

        Args:
            eid: The id for this widget. Defaults to a UUID.
            group: If set, `groups` is overwritten as `(group,)`.
            groups: The initial groups this widget will belong to.
            width: The width hint.
            height: The height hint.
            frame: The frame this widget will be put into.
            alignment: How our content gets aligned, (horizontal, vertical) axes.
            overflow: The strategy to use for content that extends beyond our size.
        """

        self.eid = eid or str(uuid.uuid4())
        if group is not None:
            groups = (group,)
        self.groups = groups
        self.scroll = (0, 0)
        self.position = (0, 0)
        self.state_machine = deepcopy(self.state_machine)
        self.parent = None

        self.width = None
        self.height = None
        # These conversions are handled in their properties
        self.frame = "Frameless"  # type: ignore
        self.alignment = ("start", "start")  # type: ignore
        self.overflow = ("hide", "hide")  # type: ignore

        self._virtual_width = 0
        self._virtual_height = 0
        self._last_query = None
        self._selected_index: int | None = None

        self._clip_start: int | None = None
        self._clip_end: int | None = None

        self.computed_width = 1
        self.computed_height = 1

        self.setup()

        widget_types[type(self).__name__] = type(self)

    @property
    def state(self) -> str:
        """Returns the current state of the widget."""

        return self.state_machine()

    @property
    def styles(self) -> dict[str, Callable[[str], str]]:
        """Returns a dictionary of style keys to markup callables."""

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
                continue

            output[key] = BoundStyle(style, fill)

        return output

    @property
    def selected(self) -> Widget | None:
        """Returns the currently selected widget."""

        if self._selected_index is None:
            return None

        return self

    @property
    def frame(self) -> Frame:
        """Returns and sets the current frame."""

        return self._frame

    @frame.setter
    def frame(self, new: str | Type[Frame]) -> None:
        if isinstance(new, str):
            new = get_frame(new)

        assert not isinstance(new, str)
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
    def _framed_width(self) -> int:
        """Gets the widget's width excluding its frame."""

        return max(self.computed_width - self.frame.width, 0)

    @property
    def _framed_height(self) -> int:
        """Gets the widget's height excluding its frame."""

        return max(self.computed_height - self.frame.height, 0)

    def _parse_markup(self, markup: str) -> tuple[Span, ...]:
        """Parses some markup into a span of tuples.

        This also handles (ignores) zenith's FULL_RESET spans.
        """

        content_style = self.styles["content"]("")[1:-1]

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

                lines[i] = (  # type: ignore
                    *line[:-1],
                    span.mutate(text=span.text[:-1]),
                    *(self._parse_markup(self.styles["scrollbar_y"](chars[i]))),
                )

    def _apply_frame(self, lines: list[tuple[Span, ...]], width: int) -> None:
        """Adds frame characters around the given lines."""

        def _style(item) -> tuple[Span, ...]:
            return self._parse_markup(self.styles["frame"](item))

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        for i, line in enumerate(lines):
            lines[i] = (*_style(left), *line, *_style(right))

        if left_top + top + right_top != "":
            lines.insert(
                0, (*_style(left_top), *_style(top * width), *_style(right_top))
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (*_style(left_bottom), *_style(bottom * width), *_style(right_bottom))
            )

    def _horizontal_align(self, line: tuple[Span, ...], width: int) -> tuple[Span, ...]:
        """Aligns a tuple of spans horizontally, using `self.alignment[0]`."""

        width = max(width, self._virtual_width)
        length = sum(len(span.text) for span in line)
        diff = width - length

        style = self.styles["content"]

        if line in [tuple(), (Span(""),)]:
            return self._parse_markup(style(diff * " "))

        alignment = self.alignment[0]

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

        available = height - len(lines)
        alignment = self.alignment[1]
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
            end = line_list[-1]

            line_list[-1] = end.mutate(text=end.text + (width - occupied) * " ")

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
            return

        if "hover" in value:  # and any("click" in attr for attr in dir(self)):
            self.state_machine.apply_action("HOVERED")
            return

    def setup(self) -> None:
        """Use this to do simple setup actions without overriding __init__."""

    def as_config(self) -> Config:
        return Config(
            width=self.width,
            height=self.height,
            frame=self.frame.name,
            alignment_x=self.alignment[0],
            alignment_y=self.alignment[1],
            overflow_x=self.overflow[0],
            overflow_y=self.overflow[1],
        )

    def update(
        self,
        attrs: dict[str, DimensionSpec | AlignmentSetting | OverflowSetting],
        style_map: dict[str, str],
    ) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)

        self.style_map = self.style_map | {self.state: style_map}

    def as_query(self, state: bool = False) -> str:
        query = type(self).__name__

        if self.eid is not None:
            query += f"#{self.eid}"

        for variant in self.groups:
            query += f".{variant}"

        if state:
            query += f"/{self.state}"

        return query

    def query_changed(self) -> bool:
        query = self.as_query(state=True)
        value = query != self._last_query

        self._last_query = query
        return value

    def is_fill_width(self) -> bool:
        return self.width is None

    def is_fill_height(self) -> bool:
        return self.height is None

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
        self._clip_start = start
        self._clip_end = end

    def add_group(self, target: str) -> None:
        self.groups = tuple(list(self.groups) + [target])

    def remove_group(self, target: str) -> None:
        self.groups = tuple(group for group in self.groups if group != target)

    def toggle_group(self, target: str) -> bool:
        if group in self.groups:
            self.remove_group(target)
            return False

        self.add_group(target)
        return True

    def select_offset(self, offset: int) -> bool:
        """Selects the widget at the given offset to the current selection."""

        if offset == 0:
            return False

        if self._selected_index is None:
            self._selected_index = 0
            self.state_machine.apply_action("SELECTED")
            return True

        self._selected_index = None
        self.state_machine.apply_action("UNSELECTED")
        return False

    def select_widget(self, widget: Widget) -> bool:
        if widget is not self:
            return False

        self.select_offset(1)
        return True

    def hide(self) -> None:
        self.add_group("hidden")

    def show(self) -> None:
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

    def handle_keyboard(self, key: str) -> bool:
        ...

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        self._apply_mouse_state(action)

        if "scroll" in action.value:
            can_scroll_x, can_scroll_y = self.has_scrollbar(0), self.has_scrollbar(1)
            if (
                can_scroll_x
                and action is MouseAction.SCROLL_LEFT
                or action is MouseAction.SHIFT_SCROLL_UP
            ):
                self.scroll = (self.scroll[0] - 1, self.scroll[1])

            elif (
                can_scroll_x
                and action is MouseAction.SCROLL_RIGHT
                or action is MouseAction.SHIFT_SCROLL_DOWN
            ):
                self.scroll = (self.scroll[0] + 1, self.scroll[1])

            elif can_scroll_y and action is MouseAction.SCROLL_UP:
                self.scroll = (self.scroll[0], self.scroll[1] - 1)

            elif can_scroll_y and action is MouseAction.SCROLL_DOWN:
                self.scroll = (self.scroll[0], self.scroll[1] + 1)

        def _get_names(action: MouseAction) -> tuple[str, ...]:
            if action.value in ["hover", "release"]:
                return (action.value,)

            parts = action.value.split("_")

            # left click & right click or drag
            if parts[0] in ["left", "right"]:
                return (action.value, parts[1])

            if parts[0] == "shift":
                return (action.value, f"shift_{parts[1]}", parts[1])

            if parts[0] == "ctrl":
                return (action.value, f"ctrl_{parts[1]}", parts[1])

            # scrolling
            return (action.value, parts[0])

        possible_names = _get_names(action)

        for name in possible_names:
            if hasattr(self, f"on_{name}"):
                handle = getattr(self, f"on_{name}")

                if name.count("_") > 0:
                    handle(position)
                    return True

                handle(action, position)
                return True

        # Always return True for hover, even if no specific handler is found
        return action is MouseAction.HOVER

    def compute_dimensions(self, available_width: int, available_height: int) -> None:
        """Computes width & height based on our specifications and the parent's hint."""

        self.computed_width = _compute(self.width, available_width)
        self.computed_height = _compute(self.height, available_height)

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(
        self, *, virt_width: int | None = None, virt_height: int | None = None
    ) -> list[tuple[Span, ...]]:
        """Builds the strings that represent the widget."""

        width = self._framed_width
        height = self._framed_height

        def _clamp_scrolls() -> int:
            x_bar = _overflows(width, self._virtual_width)
            y_bar = _overflows(height, self._virtual_height)

            return (
                max(min(self.scroll[0], self._virtual_width - width + x_bar), 0),
                max(min(self.scroll[1], self._virtual_height - height + y_bar), 0),
            )

        self.scroll = _clamp_scrolls()

        content_style = self.styles["content"]

        lines: list[tuple[Span, ...]] = [
            self._parse_markup(content_style(line)) for line in self.get_content()
        ]

        self._virtual_height = virt_height or len(lines)
        self._virtual_width = virt_width or max(
            sum(len(span) for span in line) for line in lines
        )

        # Clip into vertical size
        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]

            if len(lines) < height:
                lines.extend([(Span(""),)] * (height - len(lines)))

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
        self._add_scrollbars(
            lines,
            width,
            height,
            self.has_scrollbar(0),
            self.has_scrollbar(1),
        )

        self._apply_frame(lines, width)

        if len(lines) > self.computed_height:
            lines = lines[: self.computed_height]

        lines = lines[self._clip_start : self._clip_end]

        return lines


widget_annotations = Widget.__annotations__
widget_types: dict[str, Type[Widget]] = {"Widget": Widget}
