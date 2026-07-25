"""Minimal, dependency-free OOXML (.docx) writer — SDD_Pro zero-dep policy.

Rationale (audit reverse-quality 2026-07-24)
--------------------------------------------
The framework declares ``dependencies = []`` in ``pyproject.toml`` on purpose
(forward-only ``pip install sdd-pro-tools`` must stay lean; reverse/DB deps are
opt-in extras). The "cahier des charges" generator needs to emit a real Word
document, but pulling ``python-docx`` would break that contract for every user.

A ``.docx`` is just a ZIP container of WordprocessingML (OOXML) XML parts. This
module builds a valid, Word-openable document with the Python standard library
only (``zipfile`` + ``xml.sax.saxutils.escape``). It is intentionally small: it
supports the handful of block types a specification document needs — title,
headings (H1..H4), body paragraphs with inline bold/italic, bullet & numbered
lists, tables, callout paragraphs, and page breaks. It is NOT a general Word
library.

Determinism
-----------
No timestamps, no random ids are embedded in the payload (ZIP entries are
written with a fixed date), so regenerating from identical input yields a
byte-identical file — this matters for the "regenerate on every new FEAT"
idempotence contract and for git-friendly diffs of the sibling ``.md`` mirror.

Usage
-----
    from sdd_lib.docx_writer import DocxBuilder
    doc = DocxBuilder()
    doc.title("Cahier des charges", subtitle="Projet Foo")
    doc.heading("Contexte", level=1)
    doc.paragraph("Texte simple avec un mot ", runs=[("important", {"bold": True})])
    doc.bullet_list(["Point A", "Point B"])
    doc.table([["Rôle", "Description"], ["Gérant", "Consulte les rapports"]],
              header=True)
    doc.page_break()
    doc.save(Path("workspace/docs/cahier-des-charges.docx"))
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape as _xml_escape

__all__ = ["DocxBuilder"]

# A fixed epoch for every ZIP entry → byte-stable output (determinism).
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

# EMU / twips helpers ---------------------------------------------------------
_TWIPS_PER_INCH = 1440


def _esc(text: str) -> str:
    """XML-escape and neutralise control chars Word rejects."""
    if text is None:
        text = ""
    # Strip control characters (except tab/newline handled separately).
    cleaned = "".join(ch for ch in str(text) if ch >= " " or ch in "\t")
    return _xml_escape(cleaned)


class DocxBuilder:
    """Accumulate body blocks, then serialise to a valid .docx ZIP."""

    def __init__(self) -> None:
        self._body: list[str] = []
        # Numbering instances actually referenced (numId -> abstract kind).
        self._bullet_used = False
        self._number_used = False

    # -- Block builders ------------------------------------------------------

    def title(self, text: str, subtitle: str | None = None) -> "DocxBuilder":
        self._body.append(self._para(text, style="SddTitle"))
        if subtitle:
            self._body.append(self._para(subtitle, style="SddSubtitle"))
        return self

    def heading(self, text: str, level: int = 1) -> "DocxBuilder":
        level = max(1, min(4, level))
        self._body.append(self._para(text, style=f"Heading{level}"))
        return self

    def paragraph(
        self,
        text: str = "",
        runs: Sequence[tuple[str, dict]] | None = None,
        style: str | None = None,
    ) -> "DocxBuilder":
        """A body paragraph. `text` is the leading plain run; `runs` appends
        additional styled runs (each a ``(text, props)`` tuple where props may
        hold ``bold``/``italic``)."""
        run_xml = []
        if text:
            run_xml.append(self._run(text))
        for rtext, props in runs or []:
            run_xml.append(self._run(rtext, bold=props.get("bold"), italic=props.get("italic")))
        self._body.append(self._para_raw("".join(run_xml), style=style))
        return self

    def callout(self, text: str, label: str = "Note") -> "DocxBuilder":
        """A shaded/labelled paragraph for confidence notes, gaps, warnings."""
        run_xml = self._run(f"{label} : ", bold=True) + self._run(text)
        self._body.append(self._para_raw(run_xml, style="SddCallout"))
        return self

    def bullet_list(self, items: Iterable[str]) -> "DocxBuilder":
        self._bullet_used = True
        for item in items:
            self._body.append(self._list_item(item, num_id=1))
        return self

    def number_list(self, items: Iterable[str]) -> "DocxBuilder":
        self._number_used = True
        for item in items:
            self._body.append(self._list_item(item, num_id=2))
        return self

    def table(self, rows: Sequence[Sequence[str]], header: bool = False) -> "DocxBuilder":
        if not rows:
            return self
        ncols = max(len(r) for r in rows)
        grid = "".join(f'<w:gridCol w:w="{int(9000/ncols)}"/>' for _ in range(ncols))
        row_xml = []
        for i, row in enumerate(rows):
            cells = []
            for j in range(ncols):
                val = row[j] if j < len(row) else ""
                bold = header and i == 0
                shade = '<w:shd w:val="clear" w:fill="1F3864"/>' if bold else ""
                run = self._run(val, bold=bold, color="FFFFFF" if bold else None)
                cells.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{int(9000/ncols)}" w:type="dxa"/>{shade}</w:tcPr>'
                    f'<w:p><w:pPr><w:pStyle w:val="SddCell"/></w:pPr>{run}</w:p></w:tc>'
                )
            row_xml.append(f"<w:tr>{''.join(cells)}</w:tr>")
        tbl = (
            "<w:tbl><w:tblPr>"
            '<w:tblStyle w:val="SddTable"/>'
            '<w:tblW w:w="0" w:type="auto"/>'
            '<w:tblBorders>'
            + "".join(
                f'<w:{edge} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
                for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
            )
            + "</w:tblBorders>"
            "</w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>"
            f"{''.join(row_xml)}</w:tbl>"
            # An empty paragraph after a table (Word requires a trailing block).
            "<w:p/>"
        )
        self._body.append(tbl)
        return self

    def page_break(self) -> "DocxBuilder":
        self._body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        return self

    def horizontal_rule(self) -> "DocxBuilder":
        self._body.append(
            '<w:p><w:pPr><w:pBdr>'
            '<w:bottom w:val="single" w:sz="6" w:space="1" w:color="1F3864"/>'
            "</w:pBdr></w:pPr></w:p>"
        )
        return self

    # -- Low-level XML fragments ---------------------------------------------

    def _run(self, text: str, bold: bool = False, italic: bool = False, color: str | None = None) -> str:
        rpr = []
        if bold:
            rpr.append("<w:b/>")
        if italic:
            rpr.append("<w:i/>")
        if color:
            rpr.append(f'<w:color w:val="{color}"/>')
        rpr_xml = f"<w:rPr>{''.join(rpr)}</w:rPr>" if rpr else ""
        # xml:space=preserve keeps leading/trailing spaces (Word trims otherwise).
        return f'<w:r>{rpr_xml}<w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'

    def _para(self, text: str, style: str | None = None) -> str:
        return self._para_raw(self._run(text), style=style)

    def _para_raw(self, runs_xml: str, style: str | None = None) -> str:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{ppr}{runs_xml}</w:p>"

    def _list_item(self, text: str, num_id: int) -> str:
        ppr = (
            "<w:pPr><w:pStyle w:val=\"ListParagraph\"/>"
            f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
            "</w:pPr>"
        )
        return f"<w:p>{ppr}{self._run(text)}</w:p>"

    # -- Static OOXML parts --------------------------------------------------

    def _document_xml(self) -> str:
        body = "".join(self._body)
        sect = (
            '<w:sectPr>'
            f'<w:pgSz w:w="{int(8.27*_TWIPS_PER_INCH)}" w:h="{int(11.69*_TWIPS_PER_INCH)}"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
            'w:header="720" w:footer="720" w:gutter="0"/>'
            "</w:sectPr>"
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}{sect}</w:body></w:document>"
        )

    @staticmethod
    def _styles_xml() -> str:
        def style(sid, name, based, props_ppr="", props_rpr="", default=False):
            d = ' w:default="1"' if default else ""
            return (
                f'<w:style w:type="paragraph"{d} w:styleId="{sid}">'
                f'<w:name w:val="{name}"/>'
                + (f'<w:basedOn w:val="{based}"/>' if based else "")
                + (f"<w:pPr>{props_ppr}</w:pPr>" if props_ppr else "")
                + (f"<w:rPr>{props_rpr}</w:rPr>" if props_rpr else "")
                + "</w:style>"
            )

        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            '<w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
            "</w:rPr></w:rPrDefault></w:docDefaults>",
            style("Normal", "Normal", None,
                  '<w:spacing w:after="140" w:line="276" w:lineRule="auto"/>', default=True),
            style("SddTitle", "Titre CDC", "Normal",
                  '<w:spacing w:before="240" w:after="120"/><w:jc w:val="left"/>',
                  '<w:b/><w:color w:val="1F3864"/><w:sz w:val="52"/>'),
            style("SddSubtitle", "Sous-titre CDC", "Normal",
                  '<w:spacing w:after="360"/>',
                  '<w:color w:val="595959"/><w:sz w:val="28"/>'),
            style("Heading1", "heading 1", "Normal",
                  '<w:keepNext/><w:spacing w:before="280" w:after="120"/>'
                  '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="1F3864"/></w:pBdr>',
                  '<w:b/><w:color w:val="1F3864"/><w:sz w:val="34"/>'),
            style("Heading2", "heading 2", "Normal",
                  '<w:keepNext/><w:spacing w:before="240" w:after="80"/>',
                  '<w:b/><w:color w:val="2E5496"/><w:sz w:val="28"/>'),
            style("Heading3", "heading 3", "Normal",
                  '<w:keepNext/><w:spacing w:before="200" w:after="60"/>',
                  '<w:b/><w:color w:val="2E5496"/><w:sz w:val="24"/>'),
            style("Heading4", "heading 4", "Normal",
                  '<w:keepNext/><w:spacing w:before="160" w:after="40"/>',
                  '<w:b/><w:i/><w:color w:val="404040"/><w:sz w:val="22"/>'),
            style("ListParagraph", "List Paragraph", "Normal",
                  '<w:ind w:left="360"/><w:spacing w:after="60"/>'),
            style("SddCell", "Cellule CDC", "Normal",
                  '<w:spacing w:after="20"/>', '<w:sz w:val="20"/>'),
            style("SddCallout", "Callout CDC", "Normal",
                  '<w:pBdr><w:left w:val="single" w:sz="18" w:space="6" w:color="2E5496"/></w:pBdr>'
                  '<w:shd w:val="clear" w:fill="EAF0F8"/><w:spacing w:before="80" w:after="80"/>'
                  '<w:ind w:left="120"/>',
                  '<w:sz w:val="20"/>'),
            "</w:styles>",
        ]
        return "".join(parts)

    @staticmethod
    def _numbering_xml() -> str:
        # Two abstract numbering defs: bullet (0) and decimal (1).
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
            '<w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>'
            '<w:pPr><w:ind w:left="360" w:hanging="240"/></w:pPr>'
            '<w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr></w:lvl></w:abstractNum>'
            '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">'
            '<w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
            '<w:pPr><w:ind w:left="360" w:hanging="240"/></w:pPr></w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
            "</w:numbering>"
        )

    @staticmethod
    def _content_types_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
            "</Types>"
        )

    @staticmethod
    def _root_rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )

    @staticmethod
    def _document_rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            "</Relationships>"
        )

    # -- Serialisation -------------------------------------------------------

    def to_bytes(self) -> bytes:
        import io

        parts = {
            "[Content_Types].xml": self._content_types_xml(),
            "_rels/.rels": self._root_rels_xml(),
            "word/document.xml": self._document_xml(),
            "word/styles.xml": self._styles_xml(),
            "word/numbering.xml": self._numbering_xml(),
            "word/_rels/document.xml.rels": self._document_rels_xml(),
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in parts.items():
                info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, content.encode("utf-8"))
        return buf.getvalue()

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_bytes()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        import os

        os.replace(tmp, path)
        return path
