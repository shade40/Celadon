from __future__ import annotations

from threading import Thread
from time import perf_counter, sleep

from gunmetal import Terminal, getch

from .enums import MouseAction
from .widgets import Widget

terminal = Terminal()


def _parse_mouse_input(inp: str) -> tuple[MouseAction, tuple[int, int]] | None:
    if not inp.startswith("mouse:"):
        return None

    # TODO: This ignores stacked events and only handles the last one. Shouldn't be an
    # issue, but look out.
    inp = inp.split("mouse:")[-1]

    action, position = inp.split("@")
    parts = position.split(";")

    if len(parts) != 2:
        return None

    return MouseAction(action), (int(parts[0]), int(parts[1]))


class Application:
    def __init__(self, name: str, target_frames: int = 60) -> None:
        self._name = name
        self._target_frames = 60
        self._widgets: list[Widget] = []
        self._mouse_target: Widget | None = None

        self._is_active = False

    def __enter__(self) -> Application:
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is not None:
            raise exc

        self.run()

    def __iadd__(self, other: object) -> None:
        if not isinstance(other, Widget):
            raise TypeError(f"Can only add widgets to apps, not {type(other)!r}.")

        self.add(other)

        return self

    def _draw_loop(self) -> None:
        frametime = 1 / self._target_frames

        while self._is_active:
            start = perf_counter()
            terminal.clear()

            for widget in self._widgets:
                origin = widget.position

                for i, line in enumerate(widget.build()):
                    terminal.write(line, cursor=(origin[0], origin[1] + i))

            elapsed = perf_counter() - start
            terminal.draw()

            if elapsed < frametime:
                sleep(frametime)

    def process_input(self, inp: str) -> bool:
        if (event := _parse_mouse_input(inp)) is not None:
            action, position = event

            for widget in reversed(self._widgets):
                if not widget.contains(position):
                    continue

                if widget.handle_mouse(action, position):
                    if self._mouse_target not in [None, widget]:
                        self._mouse_target.handle_mouse(
                            MouseAction.LEFT_RELEASE, position
                        )

                    self._mouse_target = widget
                    return True

            if self._mouse_target is not None:
                self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

            return False

        if len(self._widgets) == 0:
            return False

        return self._widgets[0].handle_keyboard(inp)

    def add(self, widget: Widget) -> None:
        self._widgets.append(widget)

    def run(self) -> None:
        self._is_active = True

        with terminal.alt_buffer(), terminal.report_mouse(), terminal.no_echo():
            thread = Thread(name=f"{self._name}_draw", target=self._draw_loop)
            thread.start()

            while True:
                inp = getch()

                if inp == chr(3):
                    self._is_active = False
                    break

                self.process_input(inp)
