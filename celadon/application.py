from __future__ import annotations

from threading import Thread
from time import perf_counter, sleep

from slate import terminal, getch, feed, Key

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

        for page in (pages or []):
            self.add(page)

        self.fps = 0
        self.frametime = 0

        self._draw_thread = None
        self._is_running = False
        self._raised = None

        self._target = None

    def process_input(self, inp: Key) -> None:
        mouse_event = _parse_mouse_input(inp)

        if mouse_event is None:
            if self._target is None:
                return

            self._target.handle_keyboard(inp)

    def run(self) -> None:
        def _draw_loop() -> None:
            framecount = 0
            framerates = []
            fps_sample = 5
            target_frametime = 1 / 60

            last_lines = []

            with terminal.no_echo(), terminal.alt_buffer():
                while self._is_running:
                    framecount += 1

                    start = perf_counter()

                    changes = 0
                    lines = []

                    for widget in self.page.get_widgets():
                        origin = widget.clipped_position

                        widget_lines = []
                        for i, line in enumerate(widget.build()):
                            widget_lines.append(((origin[0], origin[1] + i), line))

                        lines.extend(widget_lines)

                    changes = 0

                    if lines != last_lines:
                        changes = terminal.write_bulk(lines) 

                    last_lines = lines

                    terminal.write(f"FPS / Frametime: {self.fps} / {self.frametime}", (0, 0))
                    terminal.write(f"Changes (excl. debug info): {changes}    ", (0, 1))

                    with terminal.batch():
                        terminal.draw()

                    # FPS management
                    elapsed = perf_counter() - start
                    self.frametime = round(elapsed, 5)
                    framerates.append(1 / elapsed)

                    if elapsed < target_frametime:
                        sleep((target_frametime - elapsed) * 0.9)

                    fps_framecount = len(framerates)
                    if fps_framecount > fps_sample:
                        framerates.pop(0)

                    self.fps = round(sum(framerates) / min(fps_framecount, fps_sample))

        self._is_running = True

        self._draw_thread = Thread(target=_draw_loop)
        self._draw_thread.start()

        while self._is_running:
            inp = getch()

            if inp == "ctrl-c":
                self.stop()
                break

            if inp == "ctrl-l":
                terminal.clear()
                continue

            try:
                self.process_input(inp)

            except Exception as exc:
                self._raised = exc
                self.stop()
                break

        self._draw_thread.join()

        if self._raised is not None:
            raise self._raised

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
    def load(self, location: str) -> Page:
        ...

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
        state = {
            "active": True
        }

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


    from celadon import Slider, Tower, Row, Button, Text, frames, enums, Alignment, Anchor, Cursor, TextField, Overflow, Matrix

    root = Tower([Text("Hey!")])
    root.width = 1.0
    root.height = 1.0
    root.position = 0, 2
    root.frame = frames.Rounded()
    root.compute_dimensions(terminal.width, terminal.height - 2)
    root.alignment = (Alignment.CENTER, Alignment.CENTER)
    root.overflow = (Overflow.AUTO, Overflow.AUTO)

    text = """\
One two
three four
five

six"""

    for i in range(3):
        child = Tower([
            Text(f"Submenu #{i}"),
            Row([Button("Accept"), Button("Deny"), Button("Cancel")]),
            TextField(text),
            Matrix(20, 10)
        ])
        child.alignment = (Alignment.CENTER, Alignment.CENTER)
        child.frame = frames.Light()
        root.append(child)

    app = Application()

    app.add(Page("/", root))
    app.navigate("/")

    app.run()
    print(app.page.get_widgets())
