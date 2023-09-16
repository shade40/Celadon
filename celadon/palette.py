from slate import Color
from zenith import Palette

palette = Palette(Color.from_hex("#AFE1AF").darken(2))

palette.color_mapping = {
    "ui.text": Color((245, 245, 245)).darken(2),
    "ui.primary": palette.primary,
    "ui.secondary": palette.secondary,
    "ui.accent": palette.quaternary,
    "ui.panel1": palette.surface1.darken(5),
    "ui.panel2": palette.surface2.darken(5),
    "ui.panel3": palette.surface3.darken(5),
    "ui.panel4": palette.surface4.darken(5),
    "ui.success": palette.success,
    "ui.warning": palette.warning,
    "ui.error": palette.error,
}

palette.alias()
