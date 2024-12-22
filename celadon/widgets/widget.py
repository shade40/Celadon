# pylint: disable=too-many-lines
from __future__ import annotations

import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Any, Callable, Generator, Iterable, Literal, Type

from slate import Event, Key, Span, Terminal
from slate.span import EMPTY_SPAN
from zenith.markup import FULL_RESET, zml_get_spans, zml_pre_process

from ..enums import Alignment, MouseAction, Overflow, Anchor
from ..frames import Frame, get_frame
from ..state_machine import StateMachine
from ..style_map import StyleMap

if TYPE_CHECKING:
    from ..application import Application, Page
    from .container import Container

__all__ = ["Widget", "widget_types", "handle_mouse_on_children"]

RE_FULL_UNSETTER = re.compile(r"\/(?=\]| )")


def _get_mouse_action_name_options(action: MouseAction) -> tuple[str, ...]:
    if action.value == "hover":
        return (action.value,)

    parts = action.value.split("_")

    full = action.value
    alt_key = "_".join(parts[-2:])
    event = parts[-1]

    if alt_key in ["left", "right"]:
        return (full, alt_key, event)

    return (full, event)


_MOUSE_ACTION_NAME_OPTIONS = {
    action: _get_mouse_action_name_options(action) for action in MouseAction
}


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


def _overflows(real: int, virt: int) -> bool:
    """Determines whether the given real and virtual dimensions overflow."""

    return real / max(virt, 1) <= 1.0


def to_widget_space(pos: tuple[int, int], widget: Widget) -> tuple[int, int]:
    """Computes a position as an offset from the widget's origin.

    This doesn't account for positions _outside_ of a widget.
    """

    x_offset = pos[0] - widget.position[0] - len(widget.frame.left) - 1
    y_offset = pos[1] - widget.position[1] - len(widget.frame.top) - 1

    x_offset += widget.scroll[0]
    y_offset += widget.scroll[1]

    return (x_offset, y_offset)


def wrap_callback(callback: Callable[[], Any]) -> Callable[[Widget], bool]:
    """Creates a wrapper for empty widget callbacks.

    This lets us maintain the callback's __name__, as opposed to doing
    `lambda _: callback()`
    """

    @wraps(callback)
    def _inner(_: Widget) -> bool:
        value = callback()

        if isinstance(value, bool):
            return value

        return True

    return _inner


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
    consumes_mouse: bool = False

    state_machine = StateMachine(
        states=("idle", "hover", "selected", "active", "disabled"),
        transitions={
            "idle": {
                "DISABLED": "disabled",
                "HOVERED": "hover",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "hover": {
                "DISABLED": "disabled",
                "RELEASED": "idle",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "selected": {
                "DISABLED": "disabled",
                "UNSELECTED": "idle",
                "CLICKED": "active",
            },
            "active": {
                "DISABLED": "disabled",
                "RELEASED": "hover",
                "RELEASED_KEYBOARD": "selected",
            },
            "disabled": {
                "ENABLED": "idle",
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
                "fill": "@.panel1-3",
                "frame": ".panel1+1",
                "content": ".text-1",
                "scrollbar_x": ".panel1+3*0.2",
                "scrollbar_y": ".panel1+3*0.2",
            },
            "hover": {
                "fill": "@.panel1-3",
                "frame": ".panel1+1",
                "content": ".text-1",
                "scrollbar_x": ".panel1+3*0.2",
                "scrollbar_y": ".panel1+3*0.2",
            },
            "selected": {
                "fill": "@.panel1-3",
                "frame": ".panel1+1",
                "content": ".text+1",
                "scrollbar_x": ".panel1+3*0.2",
                "scrollbar_y": ".panel1+3*0.2",
            },
            "active": {
                "fill": "@.panel1-3",
                "frame": ".panel1+1",
                "content": ".text-1",
                "scrollbar_x": ".panel1+3*0.2",
                "scrollbar_y": ".panel1+3*0.2",
            },
            "disabled": {
                "fill": "",
                "frame": ".panel1",
                "content": ".panel1+2",
                "scrollbar_x": ".panel1",
                "scrollbar_y": ".panel1",
            },
            "/scrolling_x": {
                "scrollbar_x": ".primary",
            },
            "/scrolling_y": {
                "scrollbar_y": ".primary",
            },
        }
    )
    """The style map is the lookup table for the widget's styles at certain states."""

    rules = ""
    """YAML rules for this widget, applied only when added as part of an Application."""

    _frame: Frame
    layer: int = 0

    def __init__(
        self,
        eid: str | None = None,
        group: str | None = None,
        groups: tuple[str, ...] = tuple(),
        disabled: bool = False,
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
        self.groups = tuple(groups)
        self.position = (0, 0)
        self.state_machine = deepcopy(self.state_machine)
        self.parent: "Container" | "Page" | None = None
        self.disabled = disabled

        self.width: int | float | None = None
        self.height: int | float | None = None
        self.offset: tuple[int, int] = (0, 0)

        # These conversions are handled in their properties
        self.frame = get_frame(None)  # type: ignore
        self.alignment = ("start", "start")  # type: ignore
        self.overflow = ("hide", "hide")  # type: ignore
        self.anchor = Anchor.NONE
        self.palette: str = "main"

        self._virtual_width = 0
        self._virtual_height = 0
        self._last_query: str | None = None
        self._selected_index: int | None = None
        self._selected: Widget | None = None

        self._clip_start: tuple[int, int] = (0, 0)
        self._clip_end: tuple[int, int] = (0, 0)
        self._bindings: dict[str, Event] = {}

        self.computed_width = 1
        self.computed_height = 1
        # Used for width: shrink/fill
        self.width_offset = 0
        # Used for height: shrink/fill
        self.height_offset = 0

        self.pre_content: Event[Widget] = Event("pre content")
        self.on_content: Event[Widget] = Event("post content")

        self.pre_build: Event[Widget] = Event("pre build")
        self.on_build: Event[Widget] = Event("post build")

        self._scrollbar_x = None
        self._scrollbar_y = None

        self._scrolling_x = False
        self._scrolling_y = False

        self._scrollbar_corner_fill = None
        self._scroll = (0, 0)

        self._mouse_target: Widget | None = None
        self._hover_target: Widget | None = None

        self.setup()

        widget_types[type(self).__name__] = type(self)

    def __str__(self) -> str:
        return self.as_query()

    @property
    def terminal(self) -> Terminal | None:
        """Returns the app's terminal."""

        if self.app is None:
            return None

        return self.app.terminal

    @property
    def scrollbar_x(self) -> "Slider":
        from .slider import Slider

        if self._scrollbar_x is None:
            self._scrollbar_x = Slider(groups=("-scroll", "-scroll-x"))

            self._scrollbar_x.parent = self
            self._scrollbar_x.on_change += (
                lambda val: self.scroll_to(x=int(val * self._virtual_width)) or True
            )

        return self._scrollbar_x

    @property
    def scrollbar_y(self) -> "Slider":
        from .slider import VerticalSlider

        if self._scrollbar_y is None:
            self._scrollbar_y = VerticalSlider(groups=("-scroll", "-scroll-y"))

            self._scrollbar_y.parent = self
            self._scrollbar_y.on_change += (
                lambda val: self.scroll_to(y=int(val * self._virtual_height)) or True
            )

        return self._scrollbar_y

    @property
    def scrollbar_corner_fill(self) -> Widget:
        if self._scrollbar_corner_fill is None:
            from .text import Text

            self._scrollbar_corner_fill = Text(" ")
            self._scrollbar_corner_fill.parent = self

        return self._scrollbar_corner_fill

    @property
    def scroll(self) -> tuple[int, int]:
        return self._scroll

    @scroll.setter
    def scroll(self, new: tuple[int, int]) -> None:
        self._scroll = new

        if self._virtual_width > 0:
            self.scrollbar_x.value = new[0] / self._virtual_width
            self.scrollbar_y.value = new[1] / self._virtual_height

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

        palette = self.palette

        def _fill_palette(style: str) -> str:
            words = []

            for word in style.split(" "):
                if not (word.startswith(".") or word.startswith("@.")):
                    words.append(word)
                    continue

                alpha = ""

                if "*" in word:
                    word, alpha = word.split("*")
                    alpha = "*" + alpha

                words.append(word.replace(".", palette + ".", 1) + alpha)

            return " ".join(words)

        styles = self.style_map[self.state.split("/")[0]].copy()

        if "/" in self.state:
            key = "/" + self.state.split("/")[-1]

            if key in self.style_map:
                styles |= self.style_map[key].items()

        output = {}

        fill = _fill_palette(styles["fill"])

        if fill != "":
            fill += " "

        for key, style in styles.items():
            if key == "fill":
                key = "_fill"

            style = _fill_palette(style)

            output[key] = BoundStyle(style, fill)

        return output

    @property
    def selected(self) -> Widget | None:
        """Returns the currently selected widget."""

        if self._selected_index is None:
            return None

        return self

    @property
    def selected_index(self) -> int | None:
        return self._selected_index

    @property
    def selectable_count(self) -> int:
        return 1 - self.disabled

    @property
    def frame(self) -> Frame:
        """Returns and sets the current frame."""

        return self._frame

    @frame.setter
    def frame(self, new: str | tuple[str, str, str, str] | Type[Frame]) -> None:
        """Sets the frame setting."""

        current = getattr(self, "_frame", None)

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
    def anchor(self) -> Anchor:
        """Returns and sets the widget's anchor."""

        return self._anchor

    @anchor.setter
    def anchor(self, new: str | Anchor) -> None:
        """Sets the widget's anchor."""

        if isinstance(new, str):
            new = Anchor(new)

        self._anchor = new

    @property
    def _framed_width(self) -> int:
        """Gets the widget's width excluding its frame."""

        return max(self.computed_width - self.frame.width, 0)

    @property
    def _framed_height(self) -> int:
        """Gets the widget's height excluding its frame."""

        return max(self.computed_height - self.frame.height, 0)

    @property
    def disabled(self) -> bool:
        """Returns the widget's disabled state."""

        return self._disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        """Sets the widget's disabled state."""

        self._disabled = value

        if value:
            self.state_machine.apply_action("DISABLED")
        else:
            self.state_machine.apply_action("ENABLED")

    @property
    def clipped_position(self) -> tuple[int, int]:
        """Returns the current position offset by the current clip start position."""

        return (
            self.position[0] + self._clip_start[0],
            self.position[1] + self._clip_start[1],
        )

    @property
    def inner_rect(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Returns the inner rect of this widget."""

        frame = self.frame
        frame_bottom_raw = self.frame.bottom != ""
        frame_right_raw = self.frame.right != ""

        frame_left = (frame.left != "") * (self._clip_start[0] == 0)
        frame_right = frame_right_raw * (self._clip_end[0] == 0)
        frame_top = (frame.top != "") * (self._clip_start[1] == 0)
        frame_bottom = frame_bottom_raw * (self._clip_end[1] == 0)

        # Only add space for bars if they are clipped
        right_bar = self.has_scrollbar(1)
        if self._clip_end[1] > frame_right_raw:
            right_bar = 0

        bottom_bar = self.has_scrollbar(0)
        if self._clip_end[1] > frame_bottom_raw:
            bottom_bar = 0

        return (
            (
                self.position[0] + self._clip_start[0] + frame_left,
                self.position[1] + self._clip_start[1] + frame_top,
            ),
            (
                (
                    self.position[0]
                    + self.computed_width
                    - frame_right
                    - self._clip_end[0]
                    - right_bar
                ),
                (
                    self.position[1]
                    + self.computed_height
                    - frame_bottom
                    - self._clip_end[1]
                    - bottom_bar
                ),
            ),
        )

    @property
    def outer_rect(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Returns the outer rect of this widget."""

        return self.position, (
            self.position[0] + self.computed_width,
            self.position[1] + self.computed_height,
        )

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

    def _update_scrollbars(self, width: int, height: int) -> None:
        def _get_size(computed: int, virtual: int, framed: int) -> int:
            return int(computed * (framed / (virtual or framed)))

        self.scrollbar_x.compute_dimensions(width, 1)
        self.scrollbar_y.compute_dimensions(1, height)

        frame_left = self.frame.left != ""
        frame_top = self.frame.top != ""
        frame_right = self.frame.right != ""
        frame_bottom = self.frame.bottom != ""

        clip_start = list(self._clip_start)
        clip_end = list(self._clip_end)

        [start_x, start_y], [end_x, end_y] = self.outer_rect

        clip_start[0] = max(0, clip_start[0] - frame_left)
        clip_start[1] = max(0, clip_start[1] - frame_top)

        start_x += self.frame.left != ""
        start_y += self.frame.top != ""

        clip_end[0] = max(0, clip_end[0] - frame_right)
        clip_end[1] = max(0, clip_end[1] - frame_bottom)

        end_x -= frame_right + 1
        end_y -= frame_bottom + 1

        self.scrollbar_x.position = (start_x, end_y)
        self.scrollbar_x.clip(
            (clip_start[0], max(0, clip_start[1] - height)),
            clip_end
        )

        self.scrollbar_y.position = (end_x, start_y)
        self.scrollbar_y.clip(
            (max(0, clip_start[0] - width), clip_start[1]),
            clip_end
        )

        self.scrollbar_corner_fill.position = (end_x, end_y)
        self.scrollbar_corner_fill.clip(clip_start, clip_end)

        self.scrollbar_x.cursor_size = _get_size(
            self.computed_width, self._virtual_width, width
        )
        self.scrollbar_y.cursor_size = _get_size(
            self.computed_height, self._virtual_height, height
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
                    *_style(left_top or (left != "") * top, outer=c_outer),
                    *_style(top * width, outer=h_outer),
                    *_style(right_top or (right != "") * top, outer=c_outer),
                ),
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (
                    *_style(left_bottom or (left != "") * bottom, outer=c_outer),
                    *_style(bottom * width, outer=h_outer),
                    *_style(right_bottom or (right != "") * bottom, outer=c_outer),
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

        # Slice to start
        for span in line:
            length = len(span)

            before_start += length
            if before_start < start:
                continue

            new = span[max(start - (before_start - length), 0) :]
            length = len(new)

            if length == 0:
                continue

            line_list.append(new)

            occupied += length

            if occupied > width:
                break

        width_diff = max(occupied - width, 0)
        empty = []

        # Slice from end
        if width_diff > 0 and len(line_list) > 0:
            for i, span in enumerate(reversed(line_list)):
                new = span[:-width_diff]
                width_diff -= len(span) - len(new)

                if len(new) == 0:
                    empty.append(-i - 1)
                else:
                    line_list[-i - 1] = new

                if width_diff <= 0:
                    break

        # Remove 0 length spans
        for offset, i in enumerate(empty):
            line_list.pop(i - offset)

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
            return

        if "release" in value:
            self.state_machine.apply_action("RELEASED")

            if self._selected_index is not None:
                self.state_machine.apply_action("SELECTED")

            return

        if "hover" in value:
            self.state_machine.apply_action("HOVERED")
            return

    def _compute_shrink_width(self) -> int:
        """Computes the minimum width this widget's content takes up.

        Used for `width = -1`.
        """

        raise NotImplementedError(f"widget {self!r} does not implement shrink width.")

    def _compute_shrink_height(self) -> int:
        """Computes the minimum height this widget's content takes up.

        Used for `height = -1`.
        """

        raise NotImplementedError(f"widget {self!r} does not implement shrink height.")

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

        def _parse_offset(number: str) -> int | float:
            if number == "":
                return 0

            if number.lstrip("-+").replace(".", "", 1).isdigit():
                num = float(number)

                if num.is_integer():
                    return int(num)

                return num

            raise ValueError(
                f"can't parse {key} offset {number!r} "
                + str(value.lstrip("-+").replace(".", "", 1))
            )

        keys = dir(self)

        for key, value in attrs.items():
            if key.startswith("_"):
                raise ValueError(f"cannot set non-public attr {key!r}")

            if key not in keys:
                raise ValueError(f"cannot set non-existant attr {key!r}")

            if key in ["width", "height"] and isinstance(value, str):
                if value.startswith("fill"):
                    offset = _parse_offset(value[len("fill") :])
                    value = 1.0

                    setattr(self, f"{key}_offset", offset)

                elif value.startswith("shrink"):
                    offset = _parse_offset(value[len("shrink") :])
                    value = -1

                    setattr(self, f"{key}_offset", offset)

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

        overflow = self.overflow[index]

        if overflow is Overflow.SCROLL:
            return True

        if overflow is Overflow.HIDE:
            return False

        real, virt = [
            (self._framed_width, self._virtual_width),
            (self._framed_height, self._virtual_height),
        ][index]

        return virt > real

    def drawables(self) -> Iterable[Widget]:
        """Yields all contained widgets that should be drawn."""

        yield self

        x_bar = self.has_scrollbar(0)
        y_bar = self.has_scrollbar(1)

        if x_bar:
            yield self.scrollbar_x

        if y_bar:
            yield self.scrollbar_y

        if x_bar and y_bar:
            yield self.scrollbar_corner_fill

    def clip(self, start: tuple[int, int], end: tuple[int, int]) -> None:
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

    def select(self, index: int | None = None) -> int | None:
        if index == 0 or self.selectable_count == 0:
            return index

        if index is None:
            self._selected_index = None
            self.state_machine.apply_action("UNSELECTED")
            return index

        index -= 1

        if index == 0:
            self._selected_index = index
            self.state_machine.apply_action("SELECTED")

        else:
            self._selected_index = None
            self.state_machine.apply_action("UNSELECTED")

        return index

    def hide(self) -> None:
        """Adds the `hidden` group onto the widget."""

        self.add_group("hidden")

    def show(self) -> None:
        """Remove the `hidden` group from the widget."""

        self.remove_group("hidden")

    def contains(self, position: tuple[int, int]) -> bool:
        """Determines whether this widget contains the given position."""

        rect = self.position, (
            self.position[0] + self.computed_width,
            self.position[1] + self.computed_height,
        )

        (left, top), (right, bottom) = rect

        return left <= position[0] <= right and top <= position[1] <= bottom

    def move_to(self, x: int, y: int) -> None:
        """Moves the widget to the given position."""

        self.position = x, y

    def move_by(self, x: int, y: int) -> None:
        """Moves the widget by the given changes."""

        self.move_to(self.position[0] + x, self.position[1] + y)

    def remove_from_parent(self) -> None:
        """Removes this widget from its parent."""

        if self.parent is None:
            return

        self.parent.remove(self)

    def bind(self, key: str, callback: Callable[[Widget], Any]) -> Event:
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

        if self.disabled:
            return False

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

        if self.disabled:
            return False

        self._apply_mouse_state(action)

        bars = []

        if self.has_scrollbar(0):
            bars.append(self.scrollbar_x)

        if self.has_scrollbar(1):
            bars.append(self.scrollbar_y)

        result, mouse_target, hover_target = handle_mouse_on_children(
            action,
            position,
            self._mouse_target,
            self._hover_target,
            # TODO: We might be able to get away with just providing both regardless.
            bars,
        )

        self._mouse_target = mouse_target
        self._hover_target = hover_target

        if result:
            return True

        if "scroll" in action.value:
            can_scroll_x, can_scroll_y = self.has_scrollbar(0), self.has_scrollbar(1)

            if can_scroll_x:
                forward = [MouseAction.SCROLL_LEFT, MouseAction.SHIFT_SCROLL_UP]
                backward = [MouseAction.SCROLL_RIGHT, MouseAction.SHIFT_SCROLL_DOWN]

                if action in forward and self.scroll[0] > 0:
                    self.scroll = (self.scroll[0] - self.scroll_step, self.scroll[1])
                    return True

                if action in backward and self.scroll[0] + self.computed_width - can_scroll_y <= self._virtual_width:
                    self.scroll = (self.scroll[0] + self.scroll_step, self.scroll[1])
                    return True

            if can_scroll_y:
                if action is MouseAction.SCROLL_UP and self.scroll[1] > 0:
                    self.scroll = (self.scroll[0], self.scroll[1] - self.scroll_step)
                    return True

                if action is MouseAction.SCROLL_DOWN and self.scroll[1] + self.computed_height - can_scroll_x < self._virtual_height:
                    self.scroll = (self.scroll[0], self.scroll[1] + self.scroll_step)
                    return True

        for name in _MOUSE_ACTION_NAME_OPTIONS[action]:
            if (handle := getattr(self, f"on_{name}", None)) is not None:
                return handle(action, position)

        # TODO: Scroll propagation algorithm:
        #
        #       on start scroll:
        #           is scrollable? return True
        #           return False
        #
        #       while continuously scrolling:
        #           return True

        return False

    def compute_dimensions(self, available_width: int, available_height: int) -> None:
        """Computes width & height based on our specifications and the given space."""

        width_offset = _compute(self.width_offset, available_width)

        if self.width == -1:
            self.computed_width = self._compute_shrink_width() + self.frame.width
        else:
            self.computed_width = _compute(self.width, available_width)

        height_offset = _compute(self.height_offset, available_height)

        if self.height == -1:
            self.computed_height = self._compute_shrink_height() + self.frame.height
        else:
            self.computed_height = _compute(self.height, available_height)

        self.computed_width += self.width_offset
        self.computed_height += self.height_offset

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(
        self, *, virt_width: int | None = None, virt_height: int | None = None
    ) -> list[tuple[Span, ...]]:
        """Builds the strings that represent the widget."""

        self.pre_build(self)

        width = self._framed_width
        height = self._framed_height

        def _clamp_scrolls() -> tuple[int, int]:
            x_bar = width < self._virtual_width
            y_bar = height < self._virtual_height

            return (
                max(min(self.scroll[0], self._virtual_width - width + x_bar), 0),
                max(min(self.scroll[1], self._virtual_height - height + y_bar), 0),
            )

        self.scroll = _clamp_scrolls()

        self.pre_content(self)

        content_style = self.styles["content"]
        lines: list[tuple[Span, ...]] = [
            self._parse_markup(content_style(line)) for line in self.get_content()
        ]

        self.on_content(self)

        self._virtual_height = virt_height or len(lines) or 1
        self._virtual_width = virt_width or max(
            (sum(len(span) for span in line) for line in lines), default=1
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
            self._slice_line(line,
                self.scroll[0],
                self.scroll[0] + width
            )
            for line in lines
        ]

        self._apply_frame(lines, width)

        if len(lines) > self.computed_height:
            lines = lines[: self.computed_height]

        # TODO: This double-slice could be done in one:
        #
        #         slice scroll + clip (offset by frame?)
        #         remove frame if clipped?

        lines = [
            self._slice_line(line,
                self._clip_start[0],
                self.computed_width - self._clip_end[0]
            )
            for line in lines
        ]

        lines = lines[self._clip_start[1] :]

        if self._clip_end[1] > 0:
            lines = lines[: -self._clip_end[1]]

        both = self.has_scrollbar(0) and self.has_scrollbar(1)
        self._update_scrollbars(width - both, height - both)

        self.on_build(self)

        if (
            self._clip_start[0] + self._clip_end[0] >= self.computed_width
            or self._clip_start[1] + self._clip_end[1] >= self.computed_height
        ):
            return []

        return lines


widget_annotations = Widget.__annotations__
widget_types: dict[str, Type[Widget]] = {"Widget": Widget}


def handle_mouse_on_children(
    action: MouseAction,
    position: tuple[int, int],
    mouse_target: Widget | None,
    hover_target: Widget | None,
    children: Iterable[Widget],
) -> tuple[bool, Widget | None, Widget | None]:
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

            (success, mouse_target, hover_target)

        The input state changes based on the following rules:

        - Success is False _only_ if no child contains the given position.
        - Mouse target is...
            - Set to None on release events, or
            - Untouched if the event was not a form of "click" and the current mouse
              target could handle it, or
            - Untouched if the event was captured by another child but it could not
              handle it, or
            - Set to the first child that contained & handled the event.
        - Hover target is...
            - Set to None on release events, or
            - Set to None if a hover event is done outside the current hover target, or
            - Set to the first child that contained & handled a hover event,
            - Untouched otherwise.
    """

    if action is MouseAction.LEFT_RELEASE:
        if mouse_target is not None:
            mouse_target.handle_mouse(action, position)
            mouse_target = None

        if hover_target is not None:
            hover_target.handle_mouse(action, position)
            hover_target = None

        return True, mouse_target, hover_target

    is_hover = action is MouseAction.HOVER
    release = MouseAction.LEFT_RELEASE, position

    if (
        mouse_target is not None
        and "click" not in action.value  # Clicks cannot be done outside of the widget
        and mouse_target.handle_mouse(action, position)
    ):
        return True, mouse_target, hover_target

    scroll_actions = [MouseAction.SCROLL_UP, MouseAction.SCROLL_DOWN, MouseAction.SCROLL_LEFT, MouseAction.SCROLL_RIGHT]

    if hover_target is not None:
        if action in scroll_actions and hover_target.handle_mouse(action, position):
            return True, mouse_target, hover_target

        if is_hover and not hover_target.contains(position):
            hover_target.handle_mouse(*release)
            hover_target = None

    for child in children:
        if not child.contains(position):
            continue

        if is_hover:
            if hover_target is not None and hover_target is not child:
                hover_target.handle_mouse(*release)

            hover_target = child

        if (handled := child.handle_mouse(action, position)) or child.consumes_mouse:
            if mouse_target is not None and mouse_target is not child:
                mouse_target.handle_mouse(*release)

            if child.consumes_mouse and not handled:
                return True, mouse_target, hover_target

            return True, child, hover_target

        break

    return False, mouse_target, hover_target
