"""Convert pdf2html fixed-layout HTML into clean semantic HTML+CSS.

Placeholder module. Filled by a later feature.

Planned responsibility
-----------------------
Parse the pdf2html output (``.page`` divs, absolutely-positioned
``<div class="t cN">`` text runs whose position comes from
``transform:matrix(a,b,c,d,X,Y)``, pooled ``.cN`` font classes, and the coarse
``display:contents`` ``<table>`` markup) and reconstruct clean, semantic
HTML+CSS. Where the content is tabular, cluster runs into rows by their Y
coordinate and into columns by X bands, then emit real ``<table>`` markup.
"""

from __future__ import annotations


def convert(html: str) -> str:
    """Convert a pdf2html HTML string into clean semantic HTML+CSS.

    Not implemented yet - placeholder for a later feature.
    """
    raise NotImplementedError("converter.convert is implemented in a later feature")
