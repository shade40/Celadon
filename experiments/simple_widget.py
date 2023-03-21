from gunmetal import Terminal, getch, set_echo

from celadon import Widget

LOREM = """\
[blue]Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec fringilla vel arcu sed
rutrum. [bold red]Etiam vel posuere odio. Suspendisse rutrum ante eget egestas rutrum.
Pellentesque tristique lacinia aliquam. Aenean consectetur mauris sed lacus pulvinar
volutpat non nec ex. Integer sodales laoreet odio volutpat vehicula. Nullam eget
ultricies dolor. Etiam magna ex, rhoncus vitae augue sed, mollis volutpat tortor. Sed
efficitur placerat felis, in molestie quam sollicitudin quis. Nam sagittis, ligula sed
eleifend bibendum, magna quam feugiat purus, eu auctor sapien ante eget dui. Quisque
interdum a ipsum a scelerisque. Proin neque sem, vehicula eu magna a, semper consequat
velit. Fusce laoreet arcu ac tincidunt finibus. Curabitur pretium arcu ut placerat
rutrum. Etiam dictum convallis risus sit amet luctus. Vestibulum non malesuada tortor.

[0]0[1]1[2]2[3]3[4]4[5]5[6]6[7]7[8]8[9]9[10]10[11]11[12]12[13]13[14]14[15]15

Sed eget fermentum enim. Donec non molestie lacus, id lobortis nulla. Suspendisse
lobortis ullamcorper tortor eget cursus. Nunc facilisis, dui vel tempor tempus, dui
mi finibus velit, ac sodales tortor tortor id justo. Vestibulum tincidunt, lorem
elementum gravida blandit, est leo tempus nibh, eu aliquam nulla sem eget felis.
Proin quis lacus id nulla egestas dapibus sed ut nisl. Duis sit amet consectetur
sapien, in feugiat est. Etiam nulla tortor, semper nec diam at, dignissim bibendum
massa. Quisque nec ornare urna. Ut libero sapien, blandit sit amet nibh a, viverra
accumsan metus.

Morbi ultrices arcu est, et elementum nunc aliquam vitae. Sed id velit malesuada,
vehicula dolor vitae, pretium dui. Sed dictum massa at libero dignissim malesuad.
Phasellus condimentum felis a magna lobortis, at tristique leo pharetra. Quisque
non auctor enim. Nunc pellentesque eleifend libero, consequat faucibus odio vehicula
eget. Suspendisse potenti. Quisque vitae eros porta, faucibus dolor tincidunt,
consectetur urna. Etiam ut pharetra ex. Sed ornare maximus sapien at malesuada.

In et ipsum ligula. Vivamus aliquet libero at ligula ornare, ac ullamcorper sapien
mattis. Curabitur vehicula pharetra finibus. Quisque tincidunt risus nec ante viverr,
non convallis diam maximus. Vestibulum et mattis risus. Maecenas pellentesque hendrerit
turpis ut ultricies. Duis ultrices, justo pulvinar aliquam imperdiet, tortor quam
mollis turpis, sed fermentum nulla nunc non nisl. Nulla vitae pharetra lorem. Curabitur
ut eros turpis.

Curabitur ullamcorper dignissim semper. Proin tortor ante, lacinia sit amet massa
nec, vehicula vulputate dui. Fusce dignissim purus enim. Maecenas semper sodales
sapien in sagittis. Vestibulum ante ipsum primis in faucibus orci luctus et ultrices
posuere cubilia curae; Ut id tempus ex, in pretium lacus. In velit urna, fringilla
id eros in, faucibus fringilla lorem. Aenean mi odio, posuere in sollicitudin ve,
mollis pharetra nisl. Cras condimentum mauris tincidunt est auctor aliquam."""


DIRECTIONS = {
    "scroll-up": (0, -3),
    "scroll-down": (0, 3),
    "scroll-right": (-3, 0),
    "scroll-left": (3, 0),
    "shift-scroll-up": (-3, 0),
    "shift-scroll-down": (3, 0),
}


class TextArea(Widget):
    content: str = "\n".join([LOREM] * 3)

    def get_content(self) -> list[str]:
        return list(self.content.splitlines())


def draw(widget: Widget, terminal: Terminal) -> None:
    terminal.clear()

    for i, line in enumerate(widget.build()):
        terminal.write(line, cursor=(0, i))

    terminal.draw()


def main() -> None:
    term = Terminal()

    txt = TextArea(term.width, term.height, frame="Padded")

    txt.overflow = ("auto", "auto")
    txt.alignment = ("start", "start")

    with term.no_echo(), term.report_mouse(), term.alt_buffer() as buff:
        draw(txt, term)

        while True:
            key = getch()

            if key in (chr(3), "q"):
                break

            if key in ["left", "h"]:
                txt.scroll = (txt.scroll[0] - 1, txt.scroll[1])

            elif key in ["right", "l"]:
                txt.scroll = (txt.scroll[0] + 1, txt.scroll[1])

            elif key in ["up", "k"]:
                txt.scroll = (txt.scroll[0], txt.scroll[1] - 1)

            elif key in ["down", "j"]:
                txt.scroll = (txt.scroll[0], txt.scroll[1] + 1)

            action = ""
            if key.startswith("mouse:"):
                action, coords = key.split("mouse:")[1].split("@")

            txt.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_X")
            txt.state_machine.apply_action("SUBSTATE_EXIT_SCROLLING_Y")

            if "scroll" in action:
                if action.startswith("shift"):
                    txt.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_X")

                else:
                    txt.state_machine.apply_action("SUBSTATE_ENTER_SCROLLING_Y")

                change_x, change_y = DIRECTIONS[action]

                txt.scroll = (txt.scroll[0] + change_x, txt.scroll[1] + change_y)

            draw(txt, term)


if __name__ == "__main__":
    main()
