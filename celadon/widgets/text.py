from __future__ import annotations

import re
from typing import Any

from .widget import Widget
from ..enums import MouseAction

RE_HYPERLINK_MARKUP = re.compile(r"~([^ \]\[]+)")


class Text(Widget):
    """A widget that displays some static text."""

    rules = """
    Text:
        height: 1
    """

    def __init__(self, content: str, **widget_args: Any) -> None:
        super().__init__(**widget_args)

        self.content = content

        self.width = max(
            (len(span) for span in self._parse_markup(content.splitlines()[0])),
            default=0,
        )

    @classmethod
    def lorem(cls, **widget_args: Any) -> Text:
        """Returns a Text object filled with Lorem Ipsum."""

        return Text(
            **widget_args,
            groups=("fill-height", "overflow-auto"),
            content="""\
            Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum in metus
            suscipit, luctus augue vel, fringilla erat. Nulla at turpis volutpat,
            porttitor lectus eu, malesuada eros. Phasellus at tortor libero. Class
            aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos
            himenaeos. Nam pellentesque dolor a scelerisque feugiat. Duis nec ante mi.
            Integer in tortor elementum, imperdiet nunc sed, tincidunt erat. Sed non mi
            accumsan, aliquet ante convallis, vulputate velit. Nullam malesuada nisl
            ligula, ut fermentum risus tincidunt at. Vivamus sollicitudin condimentum
            maximus. Etiam eu metus rhoncus, placerat orci ut, rutrum lorem.

            Aliquam at laoreet ipsum. In vitae ante eu eros consectetur porta.
            Curabitur euismod, massa in tempor convallis, neque quam elementum sem, eu
            ultrices ex odio sed tellus. Curabitur ac ligula dignissim, lobortis lectus
            vel, condimentum risus. Praesent quis accumsan tortor, vitae aliquam neque.
            Maecenas id fermentum ex. Etiam enim purus, viverra et elementum vitae,
            egestas et libero. Etiam vel lacus imperdiet, viverra purus quis, posuere
            justo. Duis eu ex suscipit nisi hendrerit varius auctor id metus. Nullam
            quis sollicitudin nibh. Nam eleifend pellentesque sodales. Vestibulum
            ullamcorper vulputate euismod.

            Curabitur ultrices commodo metus, suscipit varius velit. Nam sem tortor,
            volutpat id sagittis at, cursus in purus. Fusce pretium, tellus non ultrices
            feugiat, mauris purus condimentum lacus, id vestibulum eros velit vel orci.
            Praesent gravida turpis et feugiat placerat. Sed at tellus congue, semper
            diam aliquam, elementum ipsum. Nam eu libero lobortis, consectetur erat ege,
            viverra est. Donec ultricies velit at dui egestas ultricies. Suspendisse
            gravida velit non interdum sodales. Donec finibus ac velit non facilisis.
            Praesent ipsum neque, malesuada ut laoreet sit amet, eleifend aliquet quam.
            Fusce ex nibh, fringilla a augue eget, tristique lacinia ligula. Ut eu
            tortor non dolor ultrices hendrerit eget non lectus. Mauris pharetra dolor
            sit amet ante pellentesque sagittis. Praesent in ultricies odio, eu laoreet
            felis.

            In a augue sollicitudin felis commodo sollicitudin nec vel nibh. Nunc
            euismod semper massa, in finibus enim lacinia consectetur. Ut tristique
            risus augue, in mollis elit sodales at. Donec sed ipsum ligula. Praesent
            suscipit neque ut faucibus euismod. Duis pellentesque ac enim eu ornare.
            Curabitur blandit, velit ut luctus semper, erat sapien fermentum velit, a
            sodales leo arcu nec est.

            Morbi rutrum in est vitae placerat. Orci varius natoque penatibus et magnis
            dis parturient montes, nascetur ridiculus mus. Nullam congue non mi at
            malesuada. Nulla velit dui, iaculis in viverra id, facilisis at nibh. In
            quis metus a erat lacinia porttitor sed vitae elit. Vivamus scelerisque
            sagittis ex, quis scelerisque leo consectetur eget. Nunc sed sodales mi.
            Nunc viverra dui eget erat accumsan, id placerat ligula consectetur. Sed
            elementum dictum tortor ultrices aliquet. Proin ullamcorper euismod congue.
            Nullam eleifend lacus euismod ante mattis sagittis. Phasellus eu erat mauri.

            Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum in metus
            suscipit, luctus augue vel, fringilla erat. Nulla at turpis volutpat,
            porttitor lectus eu, malesuada eros. Phasellus at tortor libero. Class
            aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos
            himenaeos. Nam pellentesque dolor a scelerisque feugiat. Duis nec ante mi.
            Integer in tortor elementum, imperdiet nunc sed, tincidunt erat. Sed non mi
            accumsan, aliquet ante convallis, vulputate velit. Nullam malesuada nisl
            ligula, ut fermentum risus tincidunt at. Vivamus sollicitudin condimentum
            maximus. Etiam eu metus rhoncus, placerat orci ut, rutrum lorem.

            Aliquam at laoreet ipsum. In vitae ante eu eros consectetur porta.
            Curabitur euismod, massa in tempor convallis, neque quam elementum sem, eu
            ultrices ex odio sed tellus. Curabitur ac ligula dignissim, lobortis lectus
            vel, condimentum risus. Praesent quis accumsan tortor, vitae aliquam neque.
            Maecenas id fermentum ex. Etiam enim purus, viverra et elementum vitae,
            egestas et libero. Etiam vel lacus imperdiet, viverra purus quis, posuere
            justo. Duis eu ex suscipit nisi hendrerit varius auctor id metus. Nullam
            quis sollicitudin nibh. Nam eleifend pellentesque sodales. Vestibulum
            ullamcorper vulputate euismod.

            Curabitur ultrices commodo metus, suscipit varius velit. Nam sem tortor,
            volutpat id sagittis at, cursus in purus. Fusce pretium, tellus non ultrices
            feugiat, mauris purus condimentum lacus, id vestibulum eros velit vel orci.
            Praesent gravida turpis et feugiat placerat. Sed at tellus congue, semper
            diam aliquam, elementum ipsum. Nam eu libero lobortis, consectetur erat ege,
            viverra est. Donec ultricies velit at dui egestas ultricies. Suspendisse
            gravida velit non interdum sodales. Donec finibus ac velit non facilisis.
            Praesent ipsum neque, malesuada ut laoreet sit amet, eleifend aliquet quam.
            Fusce ex nibh, fringilla a augue eget, tristique lacinia ligula. Ut eu
            tortor non dolor ultrices hendrerit eget non lectus. Mauris pharetra dolor
            sit amet ante pellentesque sagittis. Praesent in ultricies odio, eu laoreet
            felis.

            In a augue sollicitudin felis commodo sollicitudin nec vel nibh. Nunc
            euismod semper massa, in finibus enim lacinia consectetur. Ut tristique
            risus augue, in mollis elit sodales at. Donec sed ipsum ligula. Praesent
            suscipit neque ut faucibus euismod. Duis pellentesque ac enim eu ornare.
            Curabitur blandit, velit ut luctus semper, erat sapien fermentum velit, a
            sodales leo arcu nec est.

            Morbi rutrum in est vitae placerat. Orci varius natoque penatibus et magnis
            dis parturient montes, nascetur ridiculus mus. Nullam congue non mi at
            malesuada. Nulla velit dui, iaculis in viverra id, facilisis at nibh. In
            quis metus a erat lacinia porttitor sed vitae elit. Vivamus scelerisque
            sagittis ex, quis scelerisque leo consectetur eget. Nunc sed sodales mi.
            Nunc viverra dui eget erat accumsan, id placerat ligula consectetur. Sed
            elementum dictum tortor ultrices aliquet. Proin ullamcorper euismod congue.
            Nullam eleifend lacus euismod ante mattis sagittis. Phasellus eu erat mauri.
            """,
        )

    @property
    def selectables(self) -> list[tuple[Widget, int]]:
        return []

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Clicks the first hyperlink within the text's content."""

        if self.app is None:
            return False

        if (mtch := RE_HYPERLINK_MARKUP.search(self.content)) is not None:
            value = mtch[1]

            self.app.route(value)

        # Never return True, as we don't want the parent to select a widget
        return False

    def get_content(self) -> list[str]:
        return self.content.splitlines()

    # Proper linebreaking prototype
    #
    # lines = []
    # usable_width = self.width - self.frame.width - 1
    #
    # for line in self.content.splitlines():
    #     length = 0
    #     buff = ""
    #
    #     for char in line:
    #         if char == "[":
    #             in_tag = True
    #
    #         elif char == "]":
    #             in_tag = False
    #
    #         if length < usable_width and char not in ["\n", "\r"]:
    #             if char != "]" and not in_tag:
    #                 length += 1
    #
    #             buff += char
    #             continue
    #
    #         lines.append(buff)
    #         length = 0
    #         buff = ""
    #
    #     lines.append(buff)
    #
    # return lines
