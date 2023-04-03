from typing import Iterable
from celadon import Application, Widget, MouseAction, deep_merge, Overflow
from celadon.frames import Frame

from celadon.widgets.text import Text
from celadon.widgets.button import Button
from celadon.widgets.checkbox import Checkbox

from gunmetal import Terminal, Event, Span

terminal = Terminal()


class Counter(Widget):
    value: int = 0
    label: str = "Value: "

    def increment(self) -> None:
        self.value += 1

    def on_left_click(self, _: tuple[int, int]) -> None:
        self.value += 1

    def on_right_click(self, _: tuple[int, int]) -> None:
        self.value -= 1

    def get_content(self) -> list[str]:
        style = "primary+3" if self.state == "active" else "primary"

        return [f"Value: [{style}]{self.value}"]


class NotButton(Widget):
    label: str

    on_submit: Event
    on_alt_submit: Event

    style_map = Widget.style_map | {
        "active": {
            "content": "bold text",
        }
    }

    def setup(self) -> None:
        self.on_submit = Event("Button Submitted")
        self.on_alt_submit = Event("Button Alternate Submitted")

    def on_click(self, action: MouseAction, __: tuple[int, int]) -> None:
        if "right" in action.value and self.on_alt_submit:
            self.on_alt_submit()
            return

        self.on_submit()

    def get_content(self) -> list[str]:
        return [self.label]


class Container(Widget):
    children: list[Widget]

    _mouse_target: Widget | None = None
    _actual_frame: Frame | None = None

    style_map = Widget.style_map | {"idle": {"scrollbar_y": "secondary"}}

    def handle_keyboard(self, key: str) -> bool:
        if key == "up":
            self.scroll = self.scroll[0], self.scroll[1] - 1
            return True

        if key == "down":
            self.scroll = self.scroll[0], self.scroll[1] + 1
            return True

        if key == "left":
            self.scroll = self.scroll[0] - 1, self.scroll[1]
            return True

        if key == "right":
            self.scroll = self.scroll[0] + 1, self.scroll[1]
            return True

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        for widget in self.children:
            if not widget.contains(position):
                continue

            if widget.handle_mouse(action, position):
                if self._mouse_target not in [widget, None]:
                    self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

                self._mouse_target = widget
                return True

        return super().handle_mouse(action, position)

    # def clip(self, start: tuple[int, int], end: tuple[int, int]) -> None:

    def drawables(self) -> Iterable[Widget]:
        yield self

        for child in self.children:
            yield from child.drawables()

    def arrange(self, x: int, y: int, start_x: int, start_y: int) -> None:
        raise NotImplementedError

    def get_content(self) -> list[str]:
        start_x = self.position[0] + self.frame.width // 2
        start_y = self.position[1] + self.frame.height // 2
        end_y = start_y + (self.height - self.frame.height)

        self.arrange(
            start_x - self.scroll[0], start_y - self.scroll[1], start_x, start_y
        )

        for widget in self.children:
            for child in widget.drawables():
                x, y = child.position

                clip_start = (0, 0)
                clip_end = (None, None)

                offset = start_y - y

                if start_y > y:
                    child.position = (
                        child.position[0],
                        child.position[1] + offset,
                    )
                    clip_start = (0, offset)

                bottom = y + child.height

                if bottom > end_y:
                    clip_end = (0, end_y - bottom)

                child.clip(clip_start, clip_end)

        return [""]

    def build(self) -> list[tuple[Span, ...]]:
        return super().build(
            virt_width=max(widget.width for widget in self.children),
            virt_height=sum(widget.height for widget in self.children),
        )


class Tower(Container):
    def arrange(self, x: int, y: int, start_x: int, start_y: int) -> None:
        height = self.height - self.frame.height

        for widget in self.children:
            widget.position = x, y
            widget.width = (
                self.width
                - self.frame.width
                - (self.height / max(self._virtual_height, 1) <= 1.0)
            )

            # if isinstance(widget, Text) and widget.content != " ":
            #     widget.height = 5
            # else:
            #     widget.height = 1

            y += widget.height


class Splitter(Container):
    def arrange(self, x: int, y: int, start_x: int, start_y: int) -> None:
        height = self.height - self.frame.height

        width, extra = divmod(self.width - self.frame.width, len(self.children))
        for widget in self.children:
            widget.height = height
            widget.width = width

            extra = 0
            widget.position = x, y

            x += widget.width


def main() -> None:
    with Application("Containers") as app:
        app += Tower(
            children=[
                Checkbox("Checkbox 1"),
                Checkbox("Checkbox 2"),
                Checkbox("Checkbox 3"),
                Checkbox("Checkbox 4"),
                Button("Test"),
                Splitter(
                    children=[
                        Button("Left"),
                        Button("Right"),
                    ],
                    frame="Light",
                    height=5,
                ),
                Checkbox("Test"),
                Splitter(
                    children=[
                        Button("Left"),
                        Button("Right"),
                    ]
                ),
            ],
            width=40,
            height=5,
            frame="Light",
        )
    return

    with Application("Tower") as app:
        app += Tower(
            children=[
                Text("[bold secondary]This is a tower\n1\n2\n3\n4\n5"),
                Button("This doesn't do anything"),
                Text(
                    "This is the first UI made with [primary bold]Celadon[/]!"
                    + "\nFun fact 1: We can do multline text!"
                    + "\nFun fact 2: We can do multline text!"
                    + "\nFun fact 3: We can do multline text!"
                    + "\nFun fact 4: We can do multline text!"
                    + "\nFun fact 5: We can do multline text!",
                    frame="Light",
                ),
                Text(" "),
                Checkbox("Checkbox 1"),
                Checkbox("Checkbox 2"),
                Checkbox("Checkbox 3"),
            ],
            frame="Padded",
            width=50,
            height=10,
            position=((terminal.width - 50) // 2, (terminal.height - 20) // 2),
        )

        app += Splitter(
            children=[Checkbox("Checkbox 1"), Checkbox("Checkbox 2")],
            frame="Padded",
            width=30,
            height=5,
            position=(10, 30),
        )

    return

    with Application("Counter") as app:
        x, y = (10, 5)

        counter = Counter(0, label="Amount of times you clicked the button: ")
        button = Button("Add to counter", alignment=("center", "center"))
        button.on_submit += counter.increment

        widgets = [
            Text(
                "This is the first UI made with [primary bold]Celadon[/]!"
                + "\nFun fact: We can do multline text!"
                + "\nFun fact: We can do multline text!"
                + "\nFun fact: We can do multline text!"
                + "\nFun fact: We can do multline text!"
                + "\nFun fact: We can do multline text!"
            ),
            Text(" "),
            counter,
            button,
            Text(" "),
            Checkbox("Checkbox 1"),
            Checkbox("Checkbox 2"),
            Checkbox("Checkbox 3"),
            Splitter(
                children=[
                    Checkbox("Checkbox 1"),
                    Checkbox("Checkbox 2"),
                ],
                height=5,
            ),
            Container(
                children=[
                    Button("Test"),
                    Button("Test"),
                ]
            ),
        ]

        for widget in widgets:
            widget.build()

            if not isinstance(widget, Text):
                widget.height = widget._virtual_height
                widget.overflow = ("hide", "hide")
            else:
                widget.height = 3

            widget.width = 50
            widget.position = (x, y)

            y += widget.height
            app += widget


if __name__ == "__main__":
    main()
