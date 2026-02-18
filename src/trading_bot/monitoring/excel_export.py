from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
import zipfile

from trading_bot.common import utc_now


def _column_name(index: int) -> str:
    result = ""
    value = index
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(ref: str, value: Any, style_id: int, numeric: bool = False) -> str:
    if numeric:
        return f'<c r="{ref}" s="{style_id}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t>{text}</t></is></c>'


def _xlsx_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="5">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF4CCCC"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE6E6E6"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""


def _rows_for_date(trade_file: Path, target_date: str) -> list[dict[str, str]]:
    if not trade_file.exists():
        return []

    rows: list[dict[str, str]] = []
    with trade_file.open("r", newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            timestamp = str(row.get("timestamp", ""))
            if timestamp[:10] != target_date:
                continue
            if str(row.get("status", "")) != "filled":
                continue
            rows.append({key: str(value) for key, value in row.items()})
    return rows


def export_trades_to_excel(
    ledger_dir: str,
    output_path: str | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    date = target_date or utc_now().date().isoformat()
    base = Path(ledger_dir)
    trade_file = base / "trade_log.csv"

    rows = _rows_for_date(trade_file, date)
    total_pnl = 0.0
    for row in rows:
        try:
            total_pnl += float(row.get("net_pnl", 0.0))
        except (TypeError, ValueError):
            continue

    if output_path:
        output = Path(output_path)
    else:
        output = Path("reports") / f"trade_report_{date}.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "Timestamp",
        "Market",
        "Strategy",
        "Notional",
        "Net PnL",
        "Return %",
        "Held Seconds",
        "Opened At",
        "Closed At",
        "Status",
    ]

    sheet_rows: list[str] = []

    # Header row (style 1)
    header_cells = []
    for col_idx, header in enumerate(headers, start=1):
        ref = f"{_column_name(col_idx)}1"
        header_cells.append(_cell(ref, header, style_id=1, numeric=False))
    sheet_rows.append(f"<row r=\"1\">{''.join(header_cells)}</row>")

    excel_row = 2
    for row in rows:
        try:
            notional = float(row.get("notional", 0.0))
        except (TypeError, ValueError):
            notional = 0.0
        try:
            net_pnl = float(row.get("net_pnl", 0.0))
        except (TypeError, ValueError):
            net_pnl = 0.0
        try:
            held_seconds = float(row.get("held_seconds", 0.0))
        except (TypeError, ValueError):
            held_seconds = 0.0

        return_pct = (net_pnl / notional * 100.0) if notional > 0 else 0.0

        # style 2 = green, style 3 = red, style 0 = neutral
        style_id = 2 if net_pnl > 0 else (3 if net_pnl < 0 else 0)

        values = [
            row.get("timestamp", ""),
            row.get("ticker", ""),
            row.get("strategy", ""),
            notional,
            net_pnl,
            return_pct,
            held_seconds,
            row.get("opened_at", ""),
            row.get("closed_at", ""),
            row.get("status", ""),
        ]

        row_cells = []
        for col_idx, value in enumerate(values, start=1):
            ref = f"{_column_name(col_idx)}{excel_row}"
            numeric = isinstance(value, (int, float))
            row_cells.append(_cell(ref, value, style_id=style_id, numeric=numeric))
        sheet_rows.append(f"<row r=\"{excel_row}\">{''.join(row_cells)}</row>")
        excel_row += 1

    # Blank row
    excel_row += 1

    # Grand total row
    total_style = 4 if total_pnl > 0 else (5 if total_pnl < 0 else 1)
    total_cells = [
        _cell(f"A{excel_row}", "Grand Net Total", style_id=total_style, numeric=False),
        _cell(f"D{excel_row}", len(rows), style_id=total_style, numeric=True),
        _cell(f"E{excel_row}", round(total_pnl, 6), style_id=total_style, numeric=True),
    ]
    sheet_rows.append(f"<row r=\"{excel_row}\">{''.join(total_cells)}</row>")

    sheet_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData>"
        "</worksheet>"
    )

    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Trades" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""

    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

    root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/styles.xml", _xlsx_styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return {
        "date": date,
        "output_path": str(output),
        "trades_exported": len(rows),
        "grand_net_total": round(total_pnl, 6),
        "source_trade_log": str(trade_file),
    }
