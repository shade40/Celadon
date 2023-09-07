from typing import Any

from zenith.markup import RE_MARKUP

from .widget import Widget


class Text(Widget):
    """A widget that displays some static text."""

    rules = """
    Text:
        height: 1
    """

    def __init__(self, content: str, **widget_args: Any) -> None:
        super().__init__(**widget_args)

        self.content = content
        self.width = len(RE_MARKUP.sub(self.content, "")) + 4

    @property
    def selectables(self) -> list[tuple[Widget, int]]:
        return []

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
