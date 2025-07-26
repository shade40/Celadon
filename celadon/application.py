from __future__ import annotations

from threading import Thread, Event as ThreadEvent, Lock

from slate import terminal, getch, getch_timeout, feed, Key

from .widget import Widget
from .enums import MouseAction


def _parse_mouse_input(key: Key) -> tuple[MouseAction, tuple[int, int]] | None:
    inp = str(key)

    if not inp.startswith("mouse:"):
        return None

    # TODO: This ignores stacked events and only handles the last one. Shouldn't be an
    # issue, but look out.
    inp = inp.rsplit("mouse:", maxsplit=1)[-1]

    action, position = inp.split("@")
    parts = position.split(";")

    if len(parts) != 2:
        return None

    return MouseAction(action), (int(parts[0]), int(parts[1]))


class Page:
    location: str
    root: Widget

    def __init__(self, location: str, root: Widget | None = None) -> None:
        self.location = location
        self.root = root

    def get_widgets(self, dirty_only: bool = False) -> list[Widget]:
        self.root.build()
        items = [self.root, *self.root.parts]

        if dirty_only:
            items = list(filter(lambda e: e.dirty, items))

        return items


class Application:
    title: str

    pages: dict[str, Page]
    page: Page | None

    def __init__(self, title: str = "", pages: list[Page] | None = None) -> None:
        self.pages = {}

        for page in pages or []:
            self.add(page)

        self._draw_thread = None
        self._is_running = False
        self._raised = None

        self._target = None

        # Threading for render abortion
        self._current_render_thread = None
        self._render_abort_event = ThreadEvent()
        self._render_lock = Lock()
        self._last_lines = []

    def process_input(self, inp: Key) -> None:
        mouse_event = _parse_mouse_input(inp)

        if mouse_event is None:
            if self._target is None:
                return

            self._target.handle_keyboard(inp)

    def run(self) -> None:
        def _calculate_animation_budget():
            active_animations = []

            for widget in self.page.get_widgets():
                active_animations.extend(widget.animations)

            if not active_animations:
                return 0

            max_duration = 0

            for anim in active_animations:
                if anim.loop:
                    max_duration = max(max_duration, 300)
                else:
                    max_duration = max(max_duration, anim.duration)

            return max_duration

        animation_budget = 0
        target_frametime = 1 / 60

        self._is_running = True

        with terminal.no_echo(), terminal.alt_buffer():
            self._start_render()

            while self._is_running:
                if animation_budget > 0:
                    # TODO: While animating we should run the renderer in a loop
                    #       with sleeps for target frametime, or a better solution.
                    #       This just doesn't work.
                    inp = getch_timeout(target_frametime)
                else:
                    inp = getch()

                if inp == "ctrl-c":
                    self.stop()
                    break

                if inp == "ctrl-l":
                    terminal.clear()
                    self._start_render()
                    continue

                try:
                    self.process_input(inp)

                except Exception as exc:
                    self._raised = exc
                    self.stop()
                    break

                current_budget = _calculate_animation_budget()
                animation_budget = max(animation_budget, current_budget)
                self._start_render()

                if animation_budget > 0:
                    animation_budget -= 1

        if self._raised is not None:
            raise self._raised

    def _start_render(self):
        def _run():
            abort_event = self._render_abort_event

            changes = 0
            lines = []

            if abort_event.is_set():
                return

            for widget in self.page.get_widgets():
                if abort_event.is_set():
                    return

                origin = widget.clipped_position
                widget_lines = []

                for i, line in enumerate(widget.build()):
                    widget_lines.append(((origin[0], origin[1] + i), line))

                lines.extend(widget_lines)

            if abort_event.is_set():
                return

            with self._render_lock:
                if lines != self._last_lines:
                    changes = terminal.write_bulk(lines)
                    self._last_lines = lines.copy()

                with terminal.batch():
                    terminal.draw()

        with self._render_lock:
            if self._current_render_thread and self._current_render_thread.is_alive():
                self._render_abort_event.set()

        self._render_abort_event = ThreadEvent()

        with self._render_lock:
            self._current_render_thread = Thread(target=_run, daemon=True)
            self._current_render_thread.start()

    def stop(self) -> None:
        feed(chr(3))
        self._is_running = False

    def add(self, page: Page) -> None:
        self.pages[page.location] = page

    def remove(self, page: Page) -> None:
        del self.pages[page.location]

    # Overwrite-able
    # No-op in default impl because pages must be defined before load,
    # but celx loads them
    def load(self, location: str) -> Page: ...

    def navigate(self, location: str) -> Page:
        page = None
        cache = True

        if cache:
            page = self.pages[location] or None

        if page is None:
            page = self.load(page)

        if page is None:
            raise ValueError()

        self.page = page
        self._target = page.root
        page.root.parent = self


if __name__ == "__main__":

    def jump_behaviour(widget: Widget):
        state = {"active": True}

        offset = 0
        original = None
        frames = 0

        from math import sin, pi

        def _jump(_):
            nonlocal offset, original, frames

            if not state["active"]:
                return

            offset = int(sin(frames / 60 * 2 * pi) * 10)
            widget.offset = 30, 12 + offset

            frames += 1
            widget.dirty = True

        widget.on_build_start += _jump

        def _pause(args):
            _, key = args

            if key != " ":
                return

            state["active"] = not state["active"]

        widget.on_key += _pause

    from celadon import (
        Slider,
        Tower,
        Row,
        Button,
        Text,
        frames,
        enums,
        Alignment,
        Anchor,
        Cursor,
        TextField,
        Overflow,
        Matrix,
    )

    root = Tower([Text("Hey!")])
    root.width = 1.0
    root.height = 1.0
    root.position = 0, 0
    root.frame = frames.Rounded()
    root.compute_dimensions(terminal.width, terminal.height)
    root.alignment = (Alignment.CENTER, Alignment.CENTER)
    root.overflow = (Overflow.AUTO, Overflow.AUTO)

    text = """\
One two
three four
five

six"""

    for i in range(3):
        anchored = Text("[@red]XXX")
        anchored.anchor = Anchor.PARENT
        anchored.offset = (-1, 5)

        child = Tower(
            [
                Text(f"Submenu #{i}"),
                Row([Button("Accept"), Button("Deny"), Button("Cancel")]),
                TextField(text),
                Matrix(20, 10),
                anchored,
            ]
        )

        for _ in range(i):
            child.append(Row([Button("One"), Button("Two"), Button("Three")]))

        # child.alignment = (Alignment.CENTER, Alignment.CENTER)
        child.frame = frames.Light()
        root.append(child)

    app = Application()

    app.add(Page("/", root))
    app.navigate("/")

    app.run()
    print(app.page.get_widgets())
