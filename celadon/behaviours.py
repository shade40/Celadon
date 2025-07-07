from functools import partial
from typing import Any, Callable, TypeVar

from slate import Key, Event, Span, terminal

from . import frames
from .enums import Alignment, Direction, Anchor
from .widget import Widget

def text(widget: Widget):
    widget.inert = True
    widget.height = -1
    widget.width = -1

    for state in widget.style_map.keys():
        widget.style_map[state]["content"] = "opaque"

    @widget.add_initializer
    def initialize(self, text: str) -> list[str]:
        self.text = text

    @widget.bind
    def get_contents(self) -> list[str]:
        return [ self.text ]

Text = Widget.create_type("Text", behaviours=[ text ])

def button(widget: Widget):
    widget.on_submit: Event[Widget] = Event("on submit")

    @widget.add_initializer 
    def initialize(self, label: str, submit_callback: Callable[[Widget], bool | None] | None = None) -> list[str]:
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

    @widget.on_build_start.append
    def set_width(self):
        odd = len(self.label) % 2
        self.width = max(len(self.label) + 4, 14 - odd)

    for k in widget.style_map.keys():
        widget.style_map[k]["frame"] = ".primary-1"
        widget.style_map[k]["background"] = "@.panel1-1"

    widget.style_map["selected"]["content"] = "bold"
    widget.style_map["selected"]["background"] = "@.panel1+1"

    widget.frame = frames.Frame.compose([
        frames.Double,
        frames.Frameless,
        frames.Double,
        frames.Frameless,
    ])

    widget.width = -1
    widget.height = -1
    widget.alignment = [Alignment.CENTER, Alignment.START]

Button = Widget.create_type("Button", behaviours=[ button ])


def container(direction: Direction, widget: Widget) -> dict[str, Any]:
    widget.direction = direction

    for state in widget.style_map.keys():
        widget.style_map[state]["content"] = ""

    @widget.add_initializer
    def initialize(
        self,
        children: list[Widget] | None = None,
        gap: int = 1
    ) -> list[str]:
        self.children = []
        self.active_children = []

        self.selected_index = 0
        self.selected = None
        
        self.gap = gap
        self.width = -1
        self.height = -1

        for child in children:
            self.append(child)

    @widget.bind
    def append(self, el: Widget) -> None:
        self.children.append(el)
        el.parent = self
        # Build once to assign correct shrink sizing
        el.build()

    @widget.bind
    def remove(self, el: Widget) -> None:
        self.children.remove(el)

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
                return widget_child.width is None or (isinstance(widget_child.width, float) and widget_child.width > 0)
            return widget_child.height is None or (isinstance(widget_child.height, float) and widget_child.height > 0)

        x, y = self.position
        frame_offset_x = 1 if hasattr(self.frame, 'left') and self.frame.left else 0
        frame_offset_y = 1 if hasattr(self.frame, 'top') and self.frame.top else 0
        x += frame_offset_x
        y += frame_offset_y
        
        children = self.children
        
        if not children:
            self.parts = []
            return
        
        available_width = max(self.computed_width - 2 * frame_offset_x, 1)
        available_height = max(self.computed_height - 2 * frame_offset_y, 1)
        
        direction = self.direction
        is_horizontal = direction == Direction.HORIZONTAL
        
        gap = self.gap
        
        # First pass: process content and compute dimensions for non-fill children
        fill_children = []
        non_fill_children = []
  
        for child in children:
            if child.anchor is Anchor.SCREEN:
                child.compute_dimensions(terminal.width, terminal.height)
                child.position = (
                    terminal.origin[0] + child.offset[0],
                    terminal.origin[1] + child.offset[1]
                )
                continue

            if _is_fill(child, is_horizontal):
                fill_children.append(child)

            else:
                child.compute_dimensions(available_width, available_height)
                non_fill_children.append(child)
        
        # Calculate remaining space for fill children
        if is_horizontal:
            used_space = sum(child.computed_width for child in non_fill_children)
            used_space += gap * max(len(children) - 1, 0)
            remaining_space = max(available_width - used_space, 0)
        else:
            used_space = sum(child.computed_height for child in non_fill_children)
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
            total_content_width = sum(child.computed_width for child in children) + gap * max(len(children) - 1, 0)
            content_align_x, content_align_x_extra = _align(self.alignment[0], available_width - total_content_width)
            current_x += content_align_x + content_align_x_extra
        else:
            total_content_height = sum(child.computed_height for child in children) + gap * max(len(children) - 1, 0)
            content_align_y, content_align_y_extra = _align(self.alignment[1], available_height - total_content_height)
            current_y += content_align_y + content_align_y_extra

        for child in children:
            all_children.extend([child, *child.parts])

            if child.anchor is not Anchor.NONE:
                continue

            if is_horizontal:
                align_y, align_y_extra = _align(self.alignment[1], available_height - child.computed_height)
                
                child.position = (current_x, current_y + align_y + align_y_extra)
                current_x += child.computed_width + gap
            else:
                align_x, align_x_extra = _align(self.alignment[0], available_width - child.computed_width)
                
                child.position = (current_x + align_x + align_x_extra, current_y)
                current_y += child.computed_height + gap
        
        self.parts = all_children
        
        # Update virtual dimensions based on children
        non_anchored = [child for child in children if child.anchor is Anchor.NONE]

        if is_horizontal:
            total_width = sum(child.computed_width for child in non_anchored) + gap * max(len(non_anchored) - 1, 0)
            max_height = max((child.computed_height for child in non_anchored), default=1)
            self._virtual_width = total_width
            self._virtual_height = max_height
        else:
            max_width = max((child.computed_width for child in non_anchored), default=1)
            total_height = sum(child.computed_height for child in non_anchored) + gap * max(len(non_anchored) - 1, 0)
            self._virtual_width = max_width
            self._virtual_height = total_height

    @widget.bind
    def get_contents(self) -> list[str]:
        # return []
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
 
    @widget.on_key.append
    def handle_selection(args):
        self, key = args
        up, down = [["arrow-up", "arrow-left"], ["arrow-down", "arrow-right"]]

        if key in ["tab", "shift-tab"]:
            self.selected.state_machine.apply_action("UNSELECTED")
            self.selected_index = min(
                max(self.selected_index + (-1 if "shift" in key else 1), 0),
                len(widget.active_children) - 1
            )
            self.selected = self.active_children[self.selected_index]
            self.state_machine.apply_action("SELECTED")
            return True

        if key not in [*up, *down]:
            return self.selected is not None and self.selected.handle_keyboard(key)

        original = self.selected_index

        if self.selected is not None:
            if self.selected.handle_keyboard(key):
                return True

            self.selected.state_machine.apply_action("UNSELECTED")

            self.selected_index = min(
                max(self.selected_index + (1 if key in down else -1), 0),
                len(widget.active_children) - 1
            )

        if self.selected_index == original and not self.is_root():
            return False

        self.selected = widget.active_children[self.selected_index]
        self.state_machine.apply_action("SELECTED")

        return True

    @widget.bind
    def serialize(self) -> dict[str, Any]:
        output = {}

        for w in self.children:
            if not hasattr(w, "serialize"):
                continue


            output = {**output, **w.serialize()}

        return output
        
Tower = Widget.create_type("Tower", behaviours=[ partial(container, Direction.VERTICAL) ])
Row = Widget.create_type("Row", behaviours=[ partial(container, Direction.HORIZONTAL) ])

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

        return { self.name: self.value }

def drag_event(widget: Widget):
    widget.on_drag = Event("on drag")

def slider(widget: Widget):
    @widget.add_initializer
    def initialize(
        self,
        value: float = 0.5,
        thumb_size: int = 1,
        resolution: float = 0.1,
        chars: tuple[str, str] = ("─", "█"),
        vertical: bool = False
    ) -> None:
        self.value = value
        self.resolution = resolution
        self.thumb_size = thumb_size
        self.vertical = vertical
        self.rail, self.thumb = chars

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
        thumb = self.thumb_size * [thumb_char]

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

    widget.height = -1
    widget.frame = frames.Frame.compose((frames.Light, frames.Frameless, frames.Light, frames.Frameless))

    widget.style_map["idle"]["content"] = ".panel1-2"
    widget.style_map["selected"]["content"] = ".panel1+1"
    widget.style_map["idle"]["frame"] = ".primary-1"
    widget.style_map["selected"]["frame"] = ".primary"

Slider = Widget.create_type("Slider", behaviours=[ form_item, drag_event, slider ])

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


Cursor = Widget.create_type("Cursor", behaviours=[ form_item, cursor ])
