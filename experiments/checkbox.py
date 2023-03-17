from celadon import Widget


class Checkbox(Widget):
    state_machine = Widget.state_machine.copy(
        add_transitions={
            ">": {
                "SUBSTATE_ENTER_CHECKED": ">checked",
            },
            ">checked": {
                "SUBSTATE_EXIT_CHECKED": ">",
            },
        }
    )

    style_map = Widget.style_map | {
        ">checked": {
            "accent": "red",
        }
    }

    def __init__(
        self, char: str, frame: str = "Frameless", width: int = 1, height: int = 1
    ) -> None:
        super().__init__(frame=frame, width=width, height=height)

        self.char = char

    def get_content(self) -> list[str]:
        if self.state.endswith(">checked"):
            return ["(" + self.char + ")"]

        return ["( )"]


class BigBoy(Widget):
    def get_content(self) -> list[str]:
        lines = []

        for i in range(20):
            lines.append(f"[bold 141]{i}. This is too many characters[/]")

        return lines


if __name__ == "__main__":
    checkbox = Checkbox("X", width=10, height=5, frame="Light")

    checkbox.alignment = ("start", "start")

    for line in checkbox.build():
        print(*line, sep="")

    checkbox.state_machine.apply_action("SUBSTATE_ENTER_CHECKED")

    for line in checkbox.build():
        print(*line, sep="")

    from gunmetal import Terminal, getch
    import time
    import random

    with (term := Terminal()).alt_buffer():
        bigboy = BigBoy(width=20, height=10, frame="Light")
        bigboy.overflow = ("scroll", "scroll")

        while True:
            term.clear("X")
            bigboy.scroll = (random.randint(0, 25), 0)
            # bigboy.scroll = (0, 0)

            for i, line in enumerate(bigboy.build()):
                term.write(line, cursor=(0, i))

            term.draw()
            # getch()

            time.sleep(0.016)

        # print(bigboy._virtual_width, bigboy._virtual_height)
