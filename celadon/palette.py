from dataclasses import dataclass

from zenith import Color, Palette

palette = Palette(Color.from_hex("#AFE1AF").darken(2))

palette.color_mapping = {
    "text": Color((245, 245, 245)).darken(2),
    "primary": palette.primary,
    "secondary": palette.secondary,
    "accent": palette.quaternary,
    "panel1": palette.surface1.darken(3),
    "panel2": palette.surface2.darken(3),
    "panel3": palette.surface4.darken(3),
}

palette.alias()
