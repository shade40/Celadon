from gunmetal import Span

from celadon import Widget


class Checkbox(Widget):
    state_machine = Widget.state_machine.copy(
        add_transitions={
            "/": {
                "SUBSTATE_ENTER_CHECKED": "/checked",
            },
            "/checked": {
                "SUBSTATE_EXIT_CHECKED": "/",
            },
        }
    )

    style_map = Widget.style_map | {
        "/checked": {
            "accent": "red",
        }
    }

    def __init__(
        self, char: str, frame: str = "Frameless", width: int = 1, height: int = 1
    ) -> None:
        super().__init__(frame=frame, width=width, height=height)

        self.char = char

    def get_content(self) -> list[str]:
        if self.state.endswith("/checked"):
            return ["(" + self.char + ")"]

        return ["( )"]


class BigBoy(Widget):
    state_machine = Widget.state_machine.copy(
        add_transitions={
            "/": {
                "SUBSTATE_ENTER_COLORED": "/colored",
            },
            "/colored": {
                "SUBSTATE_EXIT_COLORED": "/",
            },
        }
    )

    style_map = Widget.style_map | {
        "/colored": {
            "content": "141 bold",
        }
    }

    def get_content(self) -> list[tuple[Span]]:
        lines = []

        for i in range(20):
            lines.append(f"{i}. This is too many characters[/]")

        return lines


if __name__ == "__main__":
    checkbox = Checkbox("X", width=10, height=5, frame="Light")

    checkbox.alignment = ("start", "start")

    for line in checkbox.build():
        print(*line, sep="")

    checkbox.state_machine.apply_action("SUBSTATE_ENTER_CHECKED")

    for line in checkbox.build():
        print(*line, sep="")

    import random
    import time

    from gunmetal import Terminal, getch

    with (term := Terminal()).alt_buffer():
        bigboy = BigBoy(width=20, height=10, frame="Light")
        bigboy.overflow = ("scroll", "scroll")

        scroll_x = 0
        scroll_y = 0

        while True:
            term.clear(" ")

            # bigboy.scroll = (scroll_x, scroll_y)
            bigboy.scroll = (random.randint(0, 20), random.randint(0, 10))

            term.write(bigboy.state + bigboy.styles["content"]("item"), cursor=(0, 30))

            for i, line in enumerate(bigboy.build()):
                term.write(line, cursor=(0, i))

            term.draw()
            time.sleep(0.016)
            continue
            if (key := getch()) == chr(3):
                break

            elif key == "c":
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_X")
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_Y")

                if bigboy.state.endswith("/colored"):
                    bigboy.state_machine.apply_action("SUBSTATE_EXIT_COLORED")
                else:
                    bigboy.state_machine.apply_action("SUBSTATE_ENTER_COLORED")

                continue

            if key == "down":
                scroll_y += 1
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_COLORED")
                bigboy.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_Y")

            elif key == "up":
                scroll_y -= 1
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_COLORED")
                bigboy.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_Y")

            elif key == "right":
                scroll_x += 1
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_COLORED")
                bigboy.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_X")

            elif key == "left":
                scroll_x -= 1
                bigboy.state_machine.apply_action("SUBSTATE_EXIT_COLORED")
                bigboy.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_X")

            scroll_x = min(bigboy._virtual_width, max(0, scroll_x))
            scroll_y = min(bigboy._virtual_height, max(0, scroll_y))

        # print(bigboy._virtual_width, bigboy._virtual_height)
