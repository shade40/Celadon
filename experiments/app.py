from typing import Iterable
from celadon import Application, Widget, MouseAction, deep_merge

from gunmetal import Terminal, Event

terminal = Terminal()


class Counter(Widget):
    value: int = 0

    def increment(self) -> None:
        self.value += 1

    def on_left_click(self, _: tuple[int, int]) -> None:
        self.value += 1

    def on_right_click(self, _: tuple[int, int]) -> None:
        self.value -= 1

    def get_content(self) -> list[str]:
        style = "primary+3" if self.state == "active" else "primary"

        return [f"Value: [{style}]{self.value}"]


class Button(Widget):
    label: str

    on_submit: Event
    on_alt_submit: Event

    style_map = Widget.style_map | {
        "active": {
            "content": "bold text",
        }
    }

    def setup(self) -> None:
        self.on_submit = Event("Button submitted")
        self.on_alt_submit = Event("Button alternate submitted")

    def on_click(self, action: MouseAction, __: tuple[int, int]) -> None:
        if "right" in action.value and self.on_alt_submit:
            self.on_alt_submit()
            return

        self.on_submit()

    def get_content(self) -> list[str]:
        return [self.label]


def main() -> None:
    with Application("Counter") as app:
        counter = Counter(position=(5, 20), width=20, height=5, frame="Light")
        app += counter

        button = Button("Add 1", position=(30, 10), width=15, height=3)
        button.on_submit += counter.increment
        app += button

        app += Counter(position=(5, 23), width=20, height=5, frame="Padded")
        app += Counter(
            position=(terminal.width // 2 - 5, terminal.height // 2 - 3),
            width=30,
            height=10,
            frame="Padded",
        )


if __name__ == "__main__":
    main()
