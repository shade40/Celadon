from slate import Color
from zenith import Palette, zml_alias

palette = Palette("celadon", namespace="ui.")
palette.alias()

zml_alias(**{"ui.text": Color((245, 245, 245)).darken(2).hex})
