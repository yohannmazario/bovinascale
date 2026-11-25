# -*- coding: utf-8 -*-
"""QR Code em SVG via segno (puro Python)."""

import io

import segno


def to_svg(text):
    qr = segno.make(text, error="m", micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=8, border=2, xmldecl=False)
    return buf.getvalue().decode("utf-8")
