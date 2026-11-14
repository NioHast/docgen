"""Perhitungan kontras WCAG 2.2 untuk warna theme AutoOffice."""

import math

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _parse_color(color: str | tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(color, tuple):
        if len(color) != 3:
            raise ValueError("warna RGB wajib berisi tepat tiga kanal")
        channels: list[int] = []
        for value in color:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError("kanal RGB wajib bilangan bulat 0-255")
            channels.append(value)
        return (channels[0], channels[1], channels[2])
    text = color.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6 or any(char not in _HEX_DIGITS for char in text):
        raise ValueError(f"warna tidak valid: {color!r}; pakai heksadesimal RRGGBB")
    value = int(text, 16)
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def _linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return math.pow((channel + 0.055) / 1.055, 2.4)


def relative_luminance(color: str | tuple[int, int, int]) -> float:
    """Hitung relative luminance WCAG dari warna heksadesimal atau RGB."""
    red, green, blue = _parse_color(color)
    return (
        0.2126 * _linearize(red / 255)
        + 0.7152 * _linearize(green / 255)
        + 0.0722 * _linearize(blue / 255)
    )


def contrast_ratio(
    foreground: str | tuple[int, int, int],
    background: str | tuple[int, int, int],
) -> float:
    """Hitung rasio kontras WCAG antara dua warna, dari 1.0 sampai 21.0."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def meets_contrast(
    foreground: str | tuple[int, int, int],
    background: str | tuple[int, int, int],
    minimum: float,
) -> bool:
    """Periksa apakah rasio kontras mencapai ambang minimum."""
    return contrast_ratio(foreground, background) >= minimum
