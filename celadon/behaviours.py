import string

from functools import partial, lru_cache
from typing import Any, Callable, TypeVar

from slate import Key, Event, Span, terminal, Color
from zenith import zml_escape

from . import frames
from .enums import Alignment, Direction, Anchor, Overflow
from .widget import Widget, _apply_style, _compute

PRINTABLE_LIST = [*string.printable]

__all__ = [
    "button",
    "container",
    "cursor",
    "form_item",
    "matrix",
    "root",
    "row",
    "slider",
    "text",
    "text_field",
    "tower",
]


def _find_word_end(line: str, direction: int = 1) -> int:
    """Returns the distance from the next word boundary."""

    # Consistent with unix shell behaviour:
    # * Always delete first char, then remove any non-punctuation
    # Note that the exact behaviour isn't standardized:
    # * Python repl: until change in letter+digit & punctuation
    # * Unix shells: only removes letter+digit
    word_chars = string.ascii_letters + string.digits

    if direction == -1:
        strip_line = line.rstrip(word_chars)
    else:
        strip_line = line.lstrip(word_chars)

    return -direction * (len(strip_line) - len(line)) + direction


@Widget.from_behaviour()
def text(widget: Widget):
    widget.inert = True
    widget.height = -1
    widget.width = -1

    for state in widget.style_map.keys():
        if state == "*":
            continue
        widget.style_map[state]["content"] = "opaque"

    @widget.add_initializer
    def initialize(self, text: str) -> list[str]:
        self.text = text

    @widget.bind
    def get_contents(self) -> list[str]:
        return [self.text]


@Widget.from_behaviour()
def button(widget: Widget):
    widget.on_submit: Event[Widget] = Event("on submit")

    widget.add_rules(
        """
        width_offset=2,
        alignment=(center;start),
        frame=(double;frameless;double;frameless),

        ~frame=.primary-1,
        ~background=@.panel1-1,

        /selected/
            ~content=[],
            ~background=@white,
            ~frame=white,
        """
    )

    @widget.add_initializer
    def initialize(
        self, label: str, submit_callback: Callable[[Widget], bool | None] | None = None
    ) -> list[str]:
        self.label = label

        if submit_callback is not None:
            self.on_submit += submit_callback

    @widget.bind
    def get_contents(self):
        return [widget.label]

    @widget.on_key.append
    def submit(args):
        self, key = args

        if key in [" ", "return"]:
            self.on_submit(self)


def container(direction: Direction, widget: Widget) -> dict[str, Any]:
    widget.direction = direction
    widget.width = -1
    widget.height = -1

    for state in widget.style_map.keys():
        if state == "*":
            continue

        widget.style_map[state]["content"] = ""

    @widget.add_initializer
    def initialize(
        self, children: list[Widget] | None = None, gap: int = 1
    ) -> list[str]:
        self.children = []
        self.active_children = []

        self.selected_index = 0
        self.selected = None

        self.gap = gap

        for child in children or []:
            self.append(child)

    @widget.bind
    def append(self, el: Widget) -> None:
        self.children.append(el)
        el.parent = self
        # Build once to assign correct shrink sizing
        el.build()

    @widget.bind
    def remove(self, el: Widget) -> None:
        start = len(self.children)
        self.children.remove(el)
        handle_selection((self, "esc"))

    @widget.on_build_start.append
    def set_active_children(self):
        self.active_children = [child for child in self.children if not child.inert]
        self.inert = all(child.inert for child in self.active_children)

    @widget.on_build_start.append
    def arrange(self):
        def _align(alignment, available):
            available = max(available, 0)
            if available == 1:
                return 0, 0
            if alignment == Alignment.CENTER:
                return divmod(available, 2)
            if alignment == Alignment.END:
                return available, 0
            return 0, 0

        def _is_fill(widget_child, horizontal):
            if horizontal:
                return widget_child.width is None or (
                    isinstance(widget_child.width, float) and widget_child.width > 0
                )
            return widget_child.height is None or (
                isinstance(widget_child.height, float) and widget_child.height > 0
            )

        def _compute_offset(offset, negative):
            if isinstance(offset, float):
                return int(negative * max(offset, 0))

            if offset < 0:
                return negative + offset

            return offset

        x, y = self.position
        x -= self.scroll[0]
        y -= self.scroll[1]
        parent_anchor = x, y

        x += 1 if self.frame.left else 0
        y += 1 if self.frame.top else 0

        children = self.children

        if not children:
            self.parts = []
            return

        available_width = max(
            self._framed_width, self._virtual_width
        ) - self.has_scrollbar(1)
        available_height = max(
            self._framed_height, self._virtual_height
        ) - self.has_scrollbar(0)

        direction = self.direction
        is_horizontal = direction == Direction.HORIZONTAL

        # First pass: process content and compute dimensions for non-fill children
        fill_children = []
        non_fill_children = []

        for child in children:
            if child.anchor in [Anchor.SCREEN, Anchor.PARENT]:
                child.compute_dimensions(terminal.width, terminal.height)

                if child.anchor is Anchor.SCREEN:
                    context = terminal.size
                    origin = (0, 0)

                elif child.anchor is Anchor.PARENT:
                    context = self.computed_width, self.computed_height
                    origin = parent_anchor

                else:
                    raise NotImplementedError(
                        f"not sure how to handle anchor: {child.anchor}"
                    )

                x_offset = _compute_offset(
                    child.offset[0], context[0] - child.computed_width
                )
                y_offset = _compute_offset(
                    child.offset[1], context[1] - child.computed_height
                )

                child.position = (
                    origin[0] + x_offset,
                    origin[1] + y_offset,
                )
                continue

            if _is_fill(child, is_horizontal):
                fill_children.append(child)

            else:
                child.compute_dimensions(available_width, available_height)
                non_fill_children.append(child)

        if is_horizontal:
            used_space = sum(child.computed_width for child in non_fill_children)
            gap = _compute(self.gap, available_width - used_space)
            used_space += gap * max(len(children) - 1, 0)
            remaining_space = max(available_width - used_space, 0)
        else:
            used_space = sum(child.computed_height for child in non_fill_children)
            gap = _compute(self.gap, available_height - used_space)
            used_space += gap * max(len(children) - 1, 0)
            remaining_space = max(available_height - used_space, 0)

        # Distribute remaining space among fill children
        if fill_children:
            fill_size, fill_remainder = divmod(remaining_space, len(fill_children))
            for i, child in enumerate(fill_children):
                extra = 1 if i < fill_remainder else 0
                if is_horizontal:
                    child.compute_dimensions(fill_size + extra, available_height)
                else:
                    child.compute_dimensions(available_width, fill_size + extra)

        # Second pass: position all children
        all_children = []
        current_x, current_y = x, y

        # Calculate total content size for alignment
        if is_horizontal:
            total_content_width = sum(
                child.computed_width for child in children
            ) + gap * max(len(children) - 1, 0)
            content_align_x, content_align_x_extra = _align(
                self.alignment[0], available_width - total_content_width
            )
            current_x += content_align_x + content_align_x_extra
        else:
            total_content_height = sum(
                child.computed_height for child in children
            ) + gap * max(len(children) - 1, 0)
            content_align_y, content_align_y_extra = _align(
                self.alignment[1], available_height - total_content_height
            )
            current_y += content_align_y + content_align_y_extra

        s_start, s_end = [list(val) for val in self.inner_rect]

        for child in children:
            all_children.extend([child, *child.parts])

            if child.anchor is not Anchor.NONE:
                continue

            if is_horizontal:
                align_y, align_y_extra = _align(
                    self.alignment[1], available_height - child.computed_height
                )

                child.position = (current_x, current_y + align_y + align_y_extra)
                current_x += child.computed_width + gap
            else:
                align_x, align_x_extra = _align(
                    self.alignment[0], available_width - child.computed_width
                )

                child.position = (current_x + align_x + align_x_extra, current_y)
                current_y += child.computed_height + gap

            clip_start, clip_end = [0, 0], [0, 0]

            c_start, c_end = child.outer_rect

            if c_start[0] < s_start[0]:
                clip_start[0] = s_start[0] - c_start[0]

            if c_start[1] < s_start[1]:
                clip_start[1] = s_start[1] - c_start[1]

            if s_end[0] < c_end[0]:
                clip_end[0] = c_end[0] - s_end[0]

            if s_end[1] < c_end[1]:
                clip_end[1] = c_end[1] - s_end[1]

            child.clip(clip_start, clip_end)

        self.parts = [*all_children]

        bar_x, bar_y = self.scrollbars

        if self.has_scrollbar(0):
            self.parts.append(bar_x)

        if self.has_scrollbar(1):
            self.parts.append(bar_y)

        # Update virtual dimensions based on children
        non_anchored = [child for child in children if child.anchor is Anchor.NONE]

        if is_horizontal:
            total_width = sum(
                child.computed_width for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            max_height = max(
                (child.computed_height for child in non_anchored), default=1
            )
            self._virtual_width = total_width
            self._virtual_height = max_height
        else:
            max_width = max((child.computed_width for child in non_anchored), default=1)
            total_height = sum(
                child.computed_height for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            self._virtual_width = max_width
            self._virtual_height = total_height

    @widget.bind
    def get_contents(self) -> list[str]:
        return [self._virtual_width * " "] * self._virtual_height

    @widget.bind
    def build(self) -> list[Span]:
        return Widget.build(self, fillchar=" ")

    @widget.state_machine.on_action.append
    def cascade_selected_state(action: str):
        if "SELECTED" not in action:
            return

        if widget.selected is None:
            widget.selected = widget.active_children[widget.selected_index]

        widget.selected.state_machine.apply_action(action)

    def autoscroll():
        if widget.selected is None:
            return

        sel = widget.selected
        w, h = sel.computed_width, sel.computed_height
        clips = sel.viewport_offsets
        csx, csy = clips[0]
        cex, cey = clips[1]

        sx, sy = widget.scroll
        if cey > csy:
            widget.scroll = (sx + cex, sy + cey)
        elif csy > cey:
            widget.scroll = (sx - csx, sy - csy)

    @widget.on_key.append
    def handle_selection(args):
        self, key = args

        if key in ["tab", "shift-tab"]:
            original = self.selected

            if self.selected is not None:
                self.selected.state_machine.apply_action("UNSELECTED")

                self.selected_index = min(
                    max(self.selected_index + (-1 if "shift" in str(key) else 1), 0),
                    len(widget.active_children) - 1,
                )

            self.selected = self.active_children[self.selected_index]
            self.state_machine.apply_action("SELECTED")
            autoscroll()
            return True

        if key == "esc":
            self.state_machine.apply_action("UNSELECTED")
            self.selected_index = 0
            self.selected = None
            return True

        is_horizontal = direction == Direction.HORIZONTAL
        up, down = [
            ["arrow-up", "arrow-left"][is_horizontal],
            ["arrow-down", "arrow-right"][is_horizontal],
        ]

        if key not in [up, down]:
            return self.selected is not None and self.selected.handle_keyboard(key)

        original = self.selected_index

        if self.selected is not None:
            if self.selected.handle_keyboard(key):
                return True

            # Only change selected index if we already have a selected -
            # i.e. don't jump from unselected to selected==1
            self.selected_index = min(
                max(self.selected_index + (1 if key == down else -1), 0),
                len(self.active_children) - 1,
            )

        if self.selected_index == original and not self.is_root():
            return False

        if self.selected is not None:
            self.selected.state_machine.apply_action("UNSELECTED")

        self.selected = widget.active_children[self.selected_index]
        self.state_machine.apply_action("SELECTED")
        autoscroll()

        return True

    @widget.bind
    def serialize(self) -> dict[str, Any]:
        output = {}

        for w in self.children:
            if not hasattr(w, "serialize"):
                continue

            output = {**output, **w.serialize()}

        return output


tower = Widget.create_type("Tower", behaviours=[partial(container, Direction.VERTICAL)])
row = Widget.create_type("Row", behaviours=[partial(container, Direction.HORIZONTAL)])


@Widget.from_behaviour()
def form_item(widget: Widget):
    ValueType = TypeVar("ValueType")

    @widget.add_initializer
    def initialize(self, value: ValueType, name: str = "") -> None:
        self.name = name
        self.value = value
        self.on_change: Event[Widget] = Event("on value change")

    @widget.bind
    def serialize(self) -> dict[str, ValueType]:
        if self.name == "":
            return {}

        return {self.name: self.value}


def drag_event(widget: Widget):
    widget.on_drag = Event("on drag")


@Widget.from_behaviour(include=[drag_event])
def slider(widget: Widget):
    @widget.add_initializer
    def initialize(
        self,
        value: float = 0.5,
        thumb_size: int = 1,
        resolution: float = 0.1,
        chars: tuple[str, str] = ("─", "█"),
        vertical: bool = False,
    ) -> None:
        self.value = value
        self.resolution = resolution
        self.thumb_size = thumb_size
        self.vertical = vertical
        self.rail, self.thumb = chars

        if vertical:
            widget.width = 1
            widget.height = None
            widget.frame = frames.Frame.compose(
                (frames.Frameless, frames.Light, frames.Frameless, frames.Light)
            )
        else:
            widget.width = None
            widget.height = 1
            widget.frame = frames.Frame.compose(
                (frames.Light, frames.Frameless, frames.Light, frames.Frameless)
            )

    @widget.on_key.append
    def handle_cursor(args) -> bool:
        self, key = args

        up, down = [["arrow-left", "arrow-up"], ["arrow-down", "arrow-right"]]

        if key not in [*up, *down]:
            return False

        if key in up:
            self.value -= self.resolution
        else:
            self.value += self.resolution

        original = self.value
        self.value = max(0, self.value)
        self.value = min(self.value, 1)
        self.value = round(self.value, 1)
        changed = round(original, 1) == round(self.value, 1)

        if changed:
            self.on_change(self)

        return changed

    @widget.bind
    def get_contents(self):
        thumb_char = self.thumb.replace("\\", "")

        if self.vertical:
            size = self._framed_height - self.thumb_size
        else:
            size = self._framed_width - self.thumb_size

        start = int(size * self.value)
        styles = self.get_styles()

        line = [
            *[styles["content"](self.rail) for _ in range(start)],
            *[styles["frame"](thumb_char) for _ in range(self.thumb_size)],
            *[styles["content"](self.rail) for _ in range(size - start)],
        ]

        if self.vertical:
            return line

        return ["".join(line)]

    widget.style_map["idle"]["content"] = ".panel1-2"
    widget.style_map["selected"]["content"] = ".panel1+1"
    widget.style_map["idle"]["frame"] = ".primary-1"
    widget.style_map["selected"]["frame"] = ".primary"


@Widget.from_behaviour(include=[form_item])
def cursor(widget: Widget):
    @widget.add_initializer
    def initialize(self, value: tuple[int, int] = (0, 0)):
        self._capturing = False
        self._last: Key | None = None
        self.value = value

    @widget.bind
    def get_contents(self) -> list[str]:
        styles = self.get_styles()

        def _style(char, key):
            if self._last == key:
                return styles["content"](char)

            return styles["frame"](char)

        center = _style("o", None) if self._capturing else _style(".", None)
        up = _style("ʌ", "up")
        left = _style("<", "left")
        right = _style(">", "right")
        down = _style("v", "down")

        return [
            f"   {up}  ",
            f"[opaque] {left} {center} {right} ",
            f"   {down}  ",
        ]

    @widget.on_key.append
    def handle(args):
        self, key = args

        if key == " ":
            self._capturing = not self._capturing
            return True

        if not self._capturing:
            self._last = None
            return False

        if key not in ("arrow-left", "arrow-right", "arrow-up", "arrow-down"):
            return False

        x = self.value[0]
        y = self.value[1]

        if "left" in key:
            x -= 0.1
        elif "right" in key:
            x += 0.1
        elif "up" in key:
            y -= 0.1
        elif "down" in key:
            y += 0.1

        self._last = key

        original = (x, y)
        self.value = (max(min(x, 1), 0), max(min(y, 1), 0))

        self.on_change(self)

        return True

    widget.width = -1
    widget.height = -1

    widget.style_map["idle"]["content"] = ".panel1-1"
    widget.style_map["selected"]["content"] = ".primary bold"


@Widget.from_behaviour(include=[form_item])
def text_field(widget: Widget):
    widget.frame = frames.Frame.compose(
        (frames.Double, frames.Frameless, frames.Frameless, frames.Frameless)
    )
    widget.width = 1.0
    widget.overflow = (Overflow.AUTO, Overflow.HIDE)

    for state in widget.state_machine:
        if state == "selected":
            widget.style_map[state]["cursor"] = "@white"
        else:
            widget.style_map[state]["cursor"] = ""

    @widget.add_initializer
    def initialize(self, value: str = "", name: str = "", placeholder: str = ""):
        self.value = value
        self.name = name
        self.placeholder = placeholder
        self.cursor = (0, 0)
        self._cursor_column_hint = 0

        self.cursor_line = ("", "", "")
        self._lines = []
        self._eval_lines()
        self.multiline = True

    @widget.bind
    def _eval_lines(self) -> None:
        self._lines = self.value.split("\n")

        x, y = self.cursor
        line = self._lines[y]

        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""
        self.cursor_line = left, cursor, right

    @widget.bind
    def move_cursor(
        self, dx: int = 0, dy: int = 0, absolute: bool = False, smart: bool = False
    ) -> bool:
        cx, cy = self.cursor
        reset_hint = False

        if absolute:
            x, y = dx, dy

        else:
            if smart:
                if dx < 0 and cx == 0 and 0 < cy <= len(self._lines):
                    cx = 0
                    dx = len(self._lines[cy - 1])
                    dy -= 1

                    reset_hint = True

                elif (
                    0 < dx
                    and cx == len(self._lines[cy])
                    and dy == 0
                    and cy < len(self._lines) - 1
                ):
                    cx = 0
                    dx = 0
                    dy += 1

                    self._cursor_column_hint = 0
                    reset_hint = True

            x = max(cx + dx, self._cursor_column_hint)
            y = cy + dy

        y = max(0, min(len(self._lines) - 1, y))

        line = self._lines[y]

        x = max(0, min(len(line), x))

        if reset_hint:
            self._cursor_column_hint = 0
        else:
            self._cursor_column_hint = max(self._cursor_column_hint, x)

        self.cursor = (x, y)
        self._eval_lines()

        return self.cursor != (cx, cy)

    @widget.bind
    def set_line(self, y: int, line: str) -> None:
        self.value = "\n".join(
            [
                *self._lines[:y],
                line,
                *self._lines[y + 1 :],
            ]
        )

        self._eval_lines()

    @widget.bind
    def delete_trailing_newline(self) -> None:
        """Deletes a newline from the end of the current line.

        No-op when y == 0.
        """

        x, y = self.cursor

        if y == 0:
            return

        line = self._lines[y - 1]
        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""

        self._lines[y - 1] += self._lines[y]
        self._lines.pop(y)

        self.value = "\n".join(self._lines)

        self.scroll = (self.scroll[0], self.scroll[1] - 1)
        self.move_cursor(dy=-1, dx=len(left + cursor + right))
        self._eval_lines()

    @widget.on_key.append
    def handle_input(args) -> bool:
        self, key = args

        if key == "left":
            self._cursor_column_hint = 0
            return self.move_cursor(dx=-1, smart=True)

        if key == "right":
            self._cursor_column_hint = 0
            return self.move_cursor(dx=1, smart=True)

        if key == "up":
            return self.move_cursor(dy=-1, smart=True)

        if key == "down":
            return self.move_cursor(dy=1, smart=True)

        if key == "ctrl-up":
            return self.move_cursor(dx=self.cursor[0], dy=0, absolute=True)

        if key == "ctrl-down":
            return self.move_cursor(
                dx=self.cursor[0], dy=len(self._lines) - 1, absolute=True
            )

        x, y = self.cursor
        left, cursor, right = self.cursor_line

        if key == "alt-left":
            return self.move_cursor(dx=_find_word_end(left, direction=-1))

        if key == "alt-right":
            return self.move_cursor(dx=_find_word_end(right + " "))

        if key == "ctrl-left":
            return self.move_cursor(0, y, absolute=True)

        if key == "ctrl-right":
            return self.move_cursor(len(left + cursor + right), y, absolute=True)

        if key == "backspace":
            if x == 0:
                self.delete_trailing_newline()
                self.rebuild_ancestry()
                return True

            self.set_line(y, left[: -max(1, len(cursor))] + cursor + right)

            self._cursor_column_hint = 0
            self.move_cursor(dx=-1)
            return True

        if key == "ctrl-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            self.set_line(y, cursor + right)
            change = len(left)

            self._cursor_column_hint = 0
            self.move_cursor(dx=-change)
            return True

        if key == "alt-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            distance = _find_word_end(left, direction=-1)

            self.set_line(y, left[:distance] + cursor + right)
            self._cursor_column_hint = 0
            self.move_cursor(dx=distance)

            return True

        if key == "return":
            if not self.multiline:
                return True

            lines = self._lines

            if cursor != "":
                right = cursor + right

            lines[y] = left

            if len(lines) > y + 1:
                lines.insert(y + 1, right)
            else:
                lines.append(right)

            self.value = "\n".join(lines)
            self._cursor_column_hint = 0
            self.move_cursor(dx=-self.cursor[0], dy=1)

            self.rebuild_ancestry()
            return True

        if key in PRINTABLE_LIST:
            self.set_line(y, left + str(key) + cursor + right)
            self.move_cursor(dx=1)
            return True

    @widget.bind
    def get_contents(self) -> list[str]:
        value = self.value or self.placeholder
        styles = self.get_styles()
        frame_style = styles["frame"]
        content_style = styles["content"]
        cursor_style = styles["cursor"]

        if not value:
            return [content_style(" ") + cursor_style(" ") + "[/]" + content_style(" ")]

        if self.value == "":
            content_style = frame_style

        left, cursor, right = (
            zml_escape(part.replace("\\", "⧵")) for part in self.cursor_line
        )

        if cursor == "":
            cursor = " "

        lines = [zml_escape(line) for line in self._lines]
        y = self.cursor[1]

        styled_cursor_line = (
            " "
            + content_style(left)
            + cursor_style(cursor)
            + "[/]"
            + content_style(right)
            + " "
        )

        return [
            *(f" {line} " for line in lines[:y]),
            styled_cursor_line,
            *(f" {line} " for line in lines[y + 1 :]),
        ]


@Widget.from_behaviour()
def matrix(widget: Widget):
    @widget.add_initializer
    def initialize(self, cols: int = 10, rows: int = 10, dense: bool = True):
        self.cols = cols
        self.rows = rows
        self.dense = dense
        self.cursor = (0, 0)
        self._checkerboard = []
        self._data: list[list[Color]] = []

        for y in range(self.rows):
            line = []

            for x in range(self.cols):
                line.append("main.panel1-3" if (x + y % 2) % 2 else "main.panel1-1")

            self._checkerboard.append(line)
            self._data.append([None] * self.cols)

    @lru_cache
    def _color_from_style(style: str | Callable) -> Color:
        if not callable(style):
            raw = style
            style = lambda x: f"[{raw}]{x}[/]"

        span = _apply_style(" ", style)[0]

        return span.foreground or span.background

    @widget.on_key.append
    def move_cursor(args) -> bool:
        self, key = args

        cx, cy = self.cursor

        if key == "arrow-up":
            cy -= 1
        elif key == "arrow-down":
            cy += 1
        elif key == "arrow-left":
            cx -= 1
        elif key == "arrow-right":
            cx += 1
        elif key == "return":
            current = self._data[cy][cx]
            self._data[cy][cx] = None if current else "white"
        else:
            return False

        og = self.cursor
        self.cursor = (
            max(0, min(cx, self.cols - 1)),
            max(0, min(cy, self.rows - 1)),
        )

        return self.cursor != og

    @widget.bind
    def get_contents(self) -> list[str]:
        styles = self.get_styles()

        lines = []

        for y in range(self.rows):
            line = []
            for x in range(self.cols):
                if self.cursor == (x, y) and self.state_machine() == "selected":
                    color = Color.white().darken(5)
                else:
                    color = _color_from_style(
                        self._data[y][x] or self._checkerboard[y][x]
                    )

                line.append(color.hex)

            if not self.dense:
                lines.append("".join(f"[@{bg}] [/]" for bg in line))
                continue

            if y % 2:
                lines.append("".join(f"[@{bg} {fg}]▄[/]" for fg, bg in zip(line, last)))

            else:
                last = line

        return lines


@Widget.from_behaviour(base=tower)
def root(widget: Widget):
    widget.add_rules("anchor=screen, position=(0;0), alignment=center, overflow=auto")
    widget.width = 1.0
    widget.height = 1.0
    widget.layer = -1

    @terminal.on_resize.append
    def _resize(size):
        widget.scroll = (0, 0)
        widget.compute_dimensions(*size)

    _resize((terminal.width, terminal.height))
