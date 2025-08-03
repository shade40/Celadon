from __future__ import annotations

import re
import uuid
from copy import deepcopy
from functools import lru_cache
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Type

from slate import Event, Span, Key, terminal
from slate.span import EMPTY_SPAN
from zenith.markup import zml_get_spans, zml_pre_process, preserve_escapes, FULL_RESET

from .enums import Alignment, Anchor, Overflow
from .frames import Frame, Frameless, get_frame
from .state_machine import StateMachine

if TYPE_CHECKING:
    from .application import Application

__all__ = ["Animation", "Widget"]


def _compute(spec: int | float | None, hint: int) -> int:
    if isinstance(spec, float):
        return int(spec * hint)

    if spec is None:
        return hint

    if isinstance(spec, int):
        return spec

    raise ValueError(f"invalid dimension spec {spec!r} - must be float, int or None")


RE_FULL_UNSETTER = re.compile(r"(?<=\[)[^\]]*(\/) ")


def _keybind(
    target_key: str, action: Callable
) -> Callable[[tuple[Widget, Key]], bool | None]:
    def _inner(args):
        self, key = args

        if key != target_key:
            return False

        action(self)

    _inner.__name__ = f"on_key_{target_key}"
    return _inner


def _apply_style(line: str, style: Callable[[str], str]) -> tuple[Span, ...]:
    raw_style = style("")

    line = RE_FULL_UNSETTER.sub("/ " + raw_style, line)
    line = zml_pre_process(preserve_escapes(style(line)))

    return tuple(span for span in zml_get_spans(line) if span is not FULL_RESET)


def _get_rule_applicator(
    state_complex: str | None, key: str, value: str, style: bool
) -> Callable[[Widget], bool]:
    if not style:
        if isinstance(value, str) and value[0] == "(" and value[-1] == ")":
            value = value[1:-1].split(";")

        if not isinstance(value, list):
            value = [value]

        conversions = {
            "alignment": Alignment,
            "anchor": Anchor,
            "overflow": Overflow,
            "frame": get_frame,
        }

        if key in conversions:
            convert = conversions[key]
            value = [convert(val) for val in value]

        for i, part in enumerate(value):
            if part == "null":
                value[i] = None
                continue

            if isinstance(part, str) and part.lstrip("-").replace(".", "").isdigit():
                if "." in part:
                    value[i] = float(part)
                else:
                    value[i] = int(part)

        if key == "frame" and len(value) > 1:
            value = [Frame.compose(value)]

        if isinstance(value, list) and len(value) == 1:
            value = value[0]

            if key in ["alignment", "overflow"]:
                value = (value, value)

            elif key == "frame" and not isinstance(value, Frame):
                value = value()

    def _applicator(widget: Widget) -> bool:
        state = state_complex

        marked = False

        if state is not None:
            state_target = widget
            selector = ""

            if ":" in state:
                marked = True
                selector, state = state.split(":")

                if selector == "parent":
                    state_target = widget.parent

                else:
                    raise ValueError(f"Unknown state target selector {selector!r}.")

            if state_target is None:
                return True

            if state_target.state_machine() != state:
                if style:
                    state_styles = widget.style_map["*"]
                    if state_styles.get(key, None) == value:
                        del state_styles[key]

                return False

            if ":" in state_complex:
                state = "*"

        if style:
            state_styles = widget.style_map[state]
            current = state_styles.get(key, None)
            if current == value:
                return False

            state_styles[key] = value
            return True

        current = getattr(widget, key)
        if current == value:
            return False

        setattr(widget, key, value)
        return True

    return _applicator


def _parse_rules(
    rules: list[str], into: dict | None = None
) -> dict[tuple, Callable[[Widget], bool]]:
    if into is None:
        into = {}

    for entry in rules:
        statements = []
        statement = ""

        state = ""
        in_state = False
        in_string = False

        for i, char in enumerate(entry):
            if char == "/":
                if not in_state:
                    state = ""

                in_state = not in_state
                continue

            if in_state:
                state += char
                continue

            if char == "[":
                in_string = True
                continue

            if char == "]":
                in_string = False
                continue

            if in_string:
                statement += char
                continue

            if char.strip() == "":
                continue

            if char == ",":
                if len(statement):
                    statements.append((state or "idle", statement))
                statement = ""
                continue

            statement += char

        if len(statement):
            statements.append((state or "idle", statement))

        for state, statement in statements:
            key, value = statement.split("=")
            style = False

            if key.startswith("~"):
                style = True
                key = key[1:]

                if value.startswith("[") and value.endswith("]"):
                    value = value[1:-1]

            hash_key = (state, key, value, style)

            if hash_key not in into:
                into[hash_key] = _get_rule_applicator(state, key, value, style)

    return into


@dataclass
class Animation:
    duration: int
    loop: bool

    frame: int = 0
    on_frame: Event[tuple["Animation", "Widget"]] = None

    total_duration: int = 0
    _queue_removal: bool = False

    def __post_init__(self) -> None:
        self.on_frame = Event("on animation frame")
        self.total_duration = self.duration

    def tick(self, widget: "Widget") -> bool:
        self.frame = self.total_duration - self.duration

        self.on_frame((self, widget))
        self.duration -= 1

        if self.duration <= 0:
            if not self.loop:
                return True

            self.duration = self.total_duration

        return False

    def remove(self) -> None:
        self._queue_removal = True


class Widget:
    position: tuple[int, int]
    width: int | float | None
    height: int | float | None
    computed_width: int
    computed_height: int
    layer: int
    parent: "Container" | None
    app: "Application"
    state_machine: StateMachine
    parts: list[Widget]
    palette: str
    inert: bool
    animations: list[Animation]

    @classmethod
    def create_type(
        cls,
        name: str,
        behaviours: list[Callable[Widget]],
        source: Type[Widget] | None = None,
    ) -> Callable[[Any, ...], Widget]:
        if source is not None:
            behaviours = [*source.behaviours, *behaviours]

        def _construct(*args, eid: str | None = None, **kwargs) -> Widget:
            w = Widget(
                eid=eid,
                type_name=name,
                rules=kwargs.get("rules"),
                binds=kwargs.get("binds"),
            )

            if len(args) and len(w.initializers):
                raise ValueError(
                    "please only use keyword arguments in multi-initializer widget construction"
                    + " to avoid inconsistent behaviour."
                )

            for setup in behaviours:
                setup(w)

            for init in w.initializers:
                code = init.__code__
                arg_names = [
                    arg for arg in code.co_varnames[: code.co_argcount] if arg != "self"
                ]

                if len(args):
                    for k, v in zip(arg_names, args):
                        kwargs[k] = v

                init(**{k: v for k, v in kwargs.items() if k in arg_names})

            w.on_init(w)
            return w

        _construct.behaviours = behaviours
        return _construct

    @classmethod
    def from_behaviour(
        cls, base: Type[Widget] | None = None, include: list[Callable[[Widget], None]] | None = None
    ) -> Callable[[Any, ...], Widget]:
        def _wrap(behaviour: Callable[[Widget], None]) -> Callable[[Any, ...], Widget]:
            return cls.create_type(
                behaviour.__name__, behaviours=[behaviour, *(include or [])], source=base
            )

        return _wrap

    def __init__(
        self,
        *,
        rules: list[str] | None = None,
        eid: str | None = None,
        type_name: str = "Widget",
        binds: dict | None = None,
    ) -> None:
        self.eid = eid or str(uuid.uuid4())
        self.type_name = type_name

        self.position = (0, 0)
        self.width = -1
        self.min_width = -1
        self.max_width = -1
        self.height = -1
        self.min_height = 0
        self.max_height = -1
        self.width_offset = 0
        self.height_offset = 0
        self.computed_width = 1
        self.computed_height = 1
        self.layer = 0
        self.parent = None
        self.dirty = True
        self.inert = False
        self.parts = []
        self.animations = []
        self.frame = get_frame(None)()
        self.alignment = (Alignment.START, Alignment.START)
        self.overflow = (Overflow.AUTO, Overflow.AUTO)

        self._rule_calls = _parse_rules(rules or [])

        self._cached_styles = [None, None]

        self._virtual_width = 0
        self._virtual_height = 0
        self._clip_start = (0, 0)
        self._clip_end = (0, 0)
        self.viewport_offsets = self._clip_start, self._clip_end
        self._scrollbars = tuple()
        self._repeat_scroll_count = 0
        self._repeat_scroll_direction = -1

        self._last_content = None
        self._last_build = None
        self._last_state = None

        self._scroll = (0, 0)

        self.anchor = Anchor.NONE
        self.offset = (0, 0)

        self.palette = "main"

        self.initializers = []

        self.state_machine = StateMachine(
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
                    "RELEASED": "idle",
                    "RELEASED_KEYBOARD": "selected",
                },
                "disabled": {
                    "ENABLED": "idle",
                },
            },
        )

        self.style_map = {
            "idle": {
                "background": "",
                "frame": ".panel1-2",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "selected": {
                "background": "",
                "frame": ".panel1+2",
                "content": ".text bold",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "hover": {
                "background": "",
                "frame": ".panel1+1",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "active": {
                "background": "",
                "frame": ".panel1+2",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "disabled": {
                "background": "",
                "frame": ".panel1-1",
                "content": ".text-1",
                "scrollbar_x": "@.panel1-3",
                "scrollbar_y": "@.panel1-3",
            },
            "*": {},
        }

        self.on_init: Event[Widget] = Event("on init")

        self.on_content_start: Event[Widget] = Event("pre content")
        self.on_content: Event[Widget] = Event("post content")
        self.on_build_start: Event[Widget] = Event("pre build")
        self.on_build: Event[Widget] = Event("post build")

        self.on_key: Event[Widget, Key] = Event("on key pressed")
        self.on_mouse: Event[Widget, MouseAction, tuple[int, int]] = Event(
            "on mouse action"
        )

        self.state_machine.on_change += lambda *_: self.set_dirty()

        if binds is not None:
            for key, action in binds.items():
                self.on_key.append(_keybind(key, action))

        @terminal.on_resize.append
        def _clear_cache(_):
            self._virtual_width = 0
            self._virtual_height = 0

    def __str__(self) -> str:
        return self.type_name

    def __repr__(self) -> str:
        return f"{self.type_name}"

    @property
    def _framed_width(self) -> int:
        return max(self.computed_width - self.frame.width, 0)

    @property
    def _framed_height(self) -> int:
        return max(self.computed_height - self.frame.height, 0)

    def _parse_markup(self, markup: str) -> tuple[Span, ...]:
        markup = zml_pre_process(preserve_escapes(markup))
        return tuple(zml_get_spans(markup))

    @property
    def clipped_position(self) -> tuple[int, int]:
        return (
            self.position[0] + self._clip_start[0],
            self.position[1] + self._clip_start[1],
        )

    @property
    def clipped_width(self) -> int:
        return self.computed_width - self._clip_start[0] - self._clip_end[0]

    @property
    def clipped_height(self) -> int:
        return self.computed_height - self._clip_start[1] - self._clip_end[1]

    @property
    def inner_rect(self) -> tuple[tuple[int, int], tuple[int, int]]:
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
        return self.position, (
            self.position[0] + self.computed_width,
            self.position[1] + self.computed_height,
        )

    @property
    def scrollbars(self) -> tuple[Widget, Widget]:
        if not self._scrollbars:
            from .behaviours import slider

            x = slider(value=0.5, chars=(" ", "▅"))
            x.frame = Frameless()
            x.style_map["idle"]["frame"] = ".panel1-1"
            x.parent = self
            y = slider(value=0.5, chars=(" ", "█"), vertical=True)
            y.style_map["idle"]["frame"] = ".panel1-1"
            y.frame = Frameless()
            y.parent = self

            self._scrollbars = (x, y)

        return self._scrollbars

    @property
    def scroll(self) -> tuple[int, int]:
        return self._scroll

    @scroll.setter
    def scroll(self, new: tuple[int, int]) -> None:
        x_bar = self._framed_width < self._virtual_width
        y_bar = self._framed_height < self._virtual_height

        old = self._scroll

        self._scroll = (
            max(min(new[0], self._virtual_width - self._framed_width), 0),
            max(min(new[1], self._virtual_height - self._framed_height), 0),
        )

    def add_rules(self, *rules: str) -> None:
        _parse_rules(rules, into=self._rule_calls)

    def remove_rules(self, *rules: str) -> None:
        for key in _parse_rules(rules).keys():
            del self._rule_calls[key]

    def remove_self(self) -> None:
        if self.parent is None:
            return

        self.parent.remove(self)

    def bind(self, function: Callable) -> Callable:
        bound = function.__get__(self, self.__class__)
        setattr(self, function.__name__, bound)

        return bound

    def add_initializer(self, function: Callable) -> Callable:
        self.initializers.append(self.bind(function))

        return function

    def add_behaviour(self, behaviour: Callable[[Widget], dict[str, Any]]) -> None:
        behaviour(self)

    def get_styles(self, raw: bool = False) -> dict[str, Callable[[str], str] | str]:
        # if self._cached_styles[raw] is not None:
        #    return self._cached_styles[raw]

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

        values = {**self.style_map[self.state_machine()], **self.style_map["*"]}

        if values == {}:
            return {}

        background = values.get("background", "")
        parent = self.parent

        while background == "" and isinstance(parent, Widget):
            background = parent.get_styles(raw=True)["background"]
            parent = parent.parent

        background = _fill_palette(background)
        styles = {
            "background": background
            if raw
            else lambda text, bg=background: f"[{bg}]{text}[/bg]"
        }

        for name, style in values.items():
            if name == "background":
                continue

            style = background + " " + _fill_palette(style)

            if raw:
                styles[name] = style
            else:
                styles[name] = lambda text, style=style: f"[{style}]{text}[/fg]"

        self._cached_styles[raw] = styles

        return styles

    def has_scrollbar(self, index: Literal[0, 1]) -> bool:
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

    def _vertical_truncate(
        self, lines: list[tuple[Span, ...]], height: int
    ) -> list[tuple[Span, ...]]:
        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]
            if len(lines) < height:
                lines.extend([(EMPTY_SPAN,)] * (height - len(lines)))
        return lines

    def _vertical_align(
        self, lines: list[tuple[Span, ...]], height: int, fillchar: str
    ) -> None:
        alignment = self.alignment[1]
        available = height - len(lines)

        styles = self.get_styles()
        filler = _apply_style(fillchar, styles["content"])

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

    def _horizontal_align(
        self, line: tuple[Span, ...], width: int, fillchar: str
    ) -> tuple[Span, ...]:
        alignment = self.alignment[0]
        width = max(width, self._virtual_width)
        length = sum(len(span) for span in line)
        diff = width - length

        style = self.get_styles()["content"]

        if line in [tuple(), (Span(""),)]:
            return _apply_style(diff * fillchar, style)

        if alignment is Alignment.START:
            return (*line[:-1], line[-1].mutate(text=line[-1].text + diff * fillchar))

        if alignment is Alignment.CENTER:
            end, extra = divmod(diff, 2)
            start = end + extra

            if "".join(span.text for span in line) == " ":
                return _apply_style((start + end) * fillchar, style)

            return (
                *_apply_style(start * fillchar, style),
                line[0],
                *line[1:],
                *_apply_style(end * fillchar, style),
            )

        if alignment is Alignment.END:
            span = line[0]
            return (span.mutate(text=diff * fillchar + span.text), *line[1:])

        raise NotImplementedError(f"Unknown alignment {alignment!r}.")

    @lru_cache(1024)
    def _horizontal_truncate(
        self, line: tuple[Span, ...], start: int, end: int
    ) -> tuple[Span, ...]:
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

            if length == 0:
                continue

            line_list.append(new)
            occupied += length

            if occupied > width:
                break

        width_diff = max(occupied - width, 0)
        empty = []

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

        for offset, i in enumerate(empty):
            line_list.pop(i - offset)

        if not line_list:
            line_list.extend([Span(" ")])

        occupied = sum(len(span) for span in line_list)

        if occupied < width:
            suffix = line_list[-1]
            line_list[-1] = suffix.mutate(text=suffix.text + (width - occupied) * " ")

        return tuple(line_list)

    def _apply_frame(self, lines: list[tuple[Span, ...]], width: int) -> None:
        frame_style = self.get_styles()["frame"]

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        for i, line in enumerate(lines):
            lines[i] = (
                *_apply_style(left, frame_style),
                *line,
                *_apply_style(right, frame_style),
            )

        if left_top + top + right_top != "":
            lines.insert(
                0,
                (
                    *_apply_style(left_top or (left != "") * top, frame_style),
                    *_apply_style(top * width, frame_style),
                    *_apply_style(right_top or (right != "") * top, frame_style),
                ),
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (
                    *_apply_style(left_bottom or (left != "") * bottom, frame_style),
                    *_apply_style(bottom * width, frame_style),
                    *_apply_style(right_bottom or (right != "") * bottom, frame_style),
                )
            )

    def _apply_clip(self, lines: list[tuple[Span, ...]]) -> list[tuple[Span, ...]]:
        lines = [
            self._horizontal_truncate(
                line, self._clip_start[0], self.computed_width - self._clip_end[0]
            )
            for line in lines
        ]

        lines = lines[self._clip_start[1] :]

        if self._clip_end[1] > 0:
            lines = lines[: -self._clip_end[1]]

        return lines

    def _update_scrollbars(self, width: int, height: int) -> None:
        def _get_size(computed: int, virtual: int, framed: int) -> int:
            divisor = virtual or framed

            if divisor == 0:
                return 0

            return max(int(computed * (framed / divisor)), 1)

        if not self.has_scrollbar(0) and not self.has_scrollbar(1):
            return

        x, y = self.scrollbars

        if self._virtual_width == 0:
            x.value = 0
        else:
            x.value = self.scroll[0] / max(1, self._virtual_width - self._framed_width)

        if self._virtual_height == 0:
            y.value = 0
        else:
            y.value = self.scroll[1] / max(
                1, self._virtual_height - self._framed_height
            )

        x.compute_dimensions(width, 1)
        y.compute_dimensions(1, height)

        frame_left = self.frame.left != ""
        frame_top = self.frame.top != ""
        frame_right = self.frame.right != ""
        frame_bottom = self.frame.bottom != ""

        if self.anchor is Anchor.SCREEN:
            start_x, start_y = self.position
            end_x, end_y = terminal.width - 1, terminal.height - 1
            clip_start = (0, 0)
            clip_end = (0, 0)

        else:
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

        x.position = (start_x, end_y)
        x.clip((clip_start[0], max(0, clip_start[1] - height)), clip_end)

        y.position = (end_x, start_y)
        y.clip((max(0, clip_start[0] - width), clip_start[1]), clip_end)

        x.thumb_size = _get_size(self.computed_width, self._virtual_width, width)
        y.thumb_size = _get_size(self.computed_height, self._virtual_height, height)

    def set_dirty(self, value: bool = True):
        self.dirty = value

        if value:
            self._cached_styles = [None, None]

    def rebuild_ancestry(self) -> None:
        """Rebuild entire ancestry.

        Use for shrink-size changes that don't get propagated properly. Should/will
        be removed eventually.
        """

        w = self
        while isinstance(w, Widget):
            w.build()
            w = w.parent

    def handle_keyboard(self, key: Key) -> bool:
        self.set_dirty(True)

        if any("shift-arrow" in val for val in key.possible_values):
            """
            keys = ["shift-left", "shift-up", "shift-right", "shift-down"]
            if self._repeat_scroll_direction not in [-1, keys.index(str(key))]:
                self._repeat_scroll_direction = -1
                self._repeat_scroll_count = 0

            self._repeat_scroll_direction = keys.index(str(key))
            scroll_step = max(1, int(12 * self._repeat_scroll_count / 8))
            """
            scroll_step = 2
            scroll = list(self.scroll)
            scroll_horizontal, scroll_vertical = (
                self.has_scrollbar(0),
                self.has_scrollbar(1),
            )

            if key == "shift-up" and scroll_vertical:
                scroll[1] -= scroll_step
            elif key == "shift-down" and scroll_vertical:
                scroll[1] += scroll_step
            elif key == "shift-left" and scroll_horizontal:
                scroll[0] -= scroll_step * 2
            elif key == "shift-right" and scroll_horizontal:
                scroll[0] += scroll_step * 2
            elif key == "ctrl-shift-up" and scroll_vertical:
                scroll[1] = 0
            elif key == "ctrl-shift-down" and scroll_vertical:
                scroll[1] = self._virtual_height

            original = self.scroll
            self.scroll = tuple(scroll)

            if original != self.scroll:
                self._repeat_scroll_count += 1
                return True

        self._repeat_scroll_count = 1
        return self.on_key((self, key))

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        self.on_mouse((self, action, position))

    def get_contents(self) -> list[str]:
        return []

    def is_root(self) -> bool:
        return self.parent is not None and not isinstance(self.parent, Widget)

    def build(self, fillchar: str = " ") -> list[str]:
        change = False
        for callback in self._rule_calls.values():
            change |= callback(self)

        self.parts = []

        bar_x, bar_y = self.scrollbars

        if self.has_scrollbar(0):
            self.parts.append(bar_x)

        if self.has_scrollbar(1):
            self.parts.append(bar_y)

        self.on_build_start(self)

        width = self._framed_width
        height = self._framed_height

        self.on_content_start(self)
        content = self.get_contents()
        self.on_content(self)

        self.animations = [
            anim
            for anim in self.animations
            if not anim.tick(self) and not anim._queue_removal
        ]

        self._update_scrollbars(width, height)

        styles = self.get_styles()

        state = (
            width,
            height,
            self._clip_start,
            self._clip_end,
            self.get_styles(raw=True),
        )

        if state == self._last_state and content == self._last_content:
            return self._last_build

        self._last_state = state
        self._last_content = content

        lines: list[tuple[Span, ...]] = [
            _apply_style(line, styles["content"]) for line in content
        ]

        self._virtual_height = len(lines) or 1
        self._virtual_width = max(
            (sum(len(span) for span in line) for line in lines), default=1
        )

        lines = self._vertical_truncate(lines, height)
        self._vertical_align(lines, height, fillchar)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width, fillchar)

        lines = [
            self._horizontal_truncate(line, self.scroll[0], self.scroll[0] + width)
            for line in lines
        ]

        self._apply_frame(lines, width)

        if len(lines) > self.computed_height:
            lines = lines[: self.computed_height]

        lines = self._apply_clip(lines)

        self.on_build(self)

        self._last_build = lines

        if (
            self._clip_start[0] + self._clip_end[0] >= self.computed_width
            or self._clip_start[1] + self._clip_end[1] >= self.computed_height
        ):
            self._last_build = []

            return []

        self._last_build = lines

        return lines

    def compute_dimensions(self, available_width: int, available_height: int) -> None:
        shrink_width = (
            self._virtual_width
            + self.frame.width
            + _compute(self.width_offset, available_width)
        )

        if self.width == -1:
            self.computed_width = shrink_width + self.has_scrollbar(1)
        else:
            self.computed_width = _compute(self.width, available_width)

        self.computed_width = max(
            shrink_width if self.min_width == -1 else self.min_width,
            self.computed_width,
        )

        if self.max_width != -1:
            self.computed_width = min(self.computed_width, self.max_width)

        shrink_height = (
            self._virtual_height
            + self.frame.height
            + _compute(self.height_offset, available_height)
        )
        if self.height == -1:
            self.computed_height = shrink_height + self.has_scrollbar(0)
        else:
            self.computed_height = _compute(self.height, available_height)

        self.computed_height = max(
            shrink_height if self.min_height == -1 else self.min_height,
            self.computed_height,
        )

        if self.max_height != -1:
            self.computed_height = min(self.computed_height, self.max_height)

    def clip(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self.viewport_offsets = (start, end)

        self._clip_start = (
            max(0, min(start[0], self.computed_width)),
            max(0, min(start[1], self.computed_height)),
        )
        self._clip_end = (
            max(0, min(end[0], self.computed_width)),
            max(0, min(end[1], self.computed_height)),
        )
