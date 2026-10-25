#!/usr/bin/env python3
"""Turn a JSON list of categorized transactions into a staging .xlsx.

Claude does the categorization reasoning and writes a JSON file describing
the new rows (see the JSON shape below). This script's only job is the
mechanical part: lay the rows out with the exact same columns as the
historical sheet, and highlight the cells that are guesses so the user knows
what to double-check before pasting into the master Google Sheet.

Usage:
    python3 generate_xlsx.py <input.json> [--reference path/to/historico-gastos.csv]

Input JSON shape:
{
    "output_path": "/abs/path/to/output.xlsx",
    "rows": [
        {
            "Year": "2026", "Month": "septiembre", "Date": "03/09/2026",
            "Paid by": "Viboras", "Income/expense": "Gasto", "Amount": "-24,11",
            "Category": "Compra", "Subcategory": "Mercadona",
            "Common": "Sí", "Quien se beneficia": "Marin;Viboras",
            "guess_fields": ["Category", "Common", "Quien se beneficia"],
            "low_confidence_fields": ["Category"]
        }
    ]
}

Any historical column not present in a row's keys (the derived/formula
columns: Marin disfruta, Viboras disfruta, Pagado por Marin, Pagado por
Viboras, Saldo Marin, Saldo Viboras, and the two "Coeficiente ... disfruta"
+ "Coef M paga 1..." columns) is left blank on purpose -- those are almost
certainly live formulas in the real Google Sheet, so writing static numbers
into them here would just get overwritten (or worse, look right but silently
diverge from the formula once the user tweaks Common / Quien se beneficia).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

GUESS_FILL = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
LOW_CONFIDENCE_FILL = PatternFill(start_color="FFCC80", end_color="FFCC80", fill_type="solid")
HEADER_FILL = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")

DEFAULT_REFERENCE = Path(__file__).resolve().parents[4] / "skills-data" / "historico-gastos.csv"


def load_header(reference_path: Path) -> list[str]:
    with reference_path.open(newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def build_workbook(header: list[str], rows: list[dict]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Nuevas transacciones"

    ws.append(header)
    for col_idx in range(1, len(header) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
    ws.freeze_panes = "A2"

    for row_idx, row in enumerate(rows, start=2):
        guess_fields = set(row.get("guess_fields", []))
        low_confidence_fields = set(row.get("low_confidence_fields", []))

        for col_idx, column_name in enumerate(header, start=1):
            value = row.get(column_name, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=value)

            if column_name in low_confidence_fields:
                cell.fill = LOW_CONFIDENCE_FILL
            elif column_name in guess_fields:
                cell.fill = GUESS_FILL

    for col_idx, column_name in enumerate(header, start=1):
        max_len = max(
            [len(column_name)] + [len(str(row.get(column_name, ""))) for row in rows]
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 10), 40)

    ws.sheet_view.showGridLines = True
    for row_idx in range(2, len(rows) + 2):
        ws.row_dimensions[row_idx].alignment = Alignment(vertical="top")

    return wb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_json", type=Path, help="Path to the JSON file with output_path + rows")
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help="Path to historico-gastos.csv, used only to read the exact column header order",
    )
    args = parser.parse_args()

    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    rows = data["rows"]
    output_path = Path(data["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = load_header(args.reference)
    wb = build_workbook(header, rows)
    wb.save(output_path)

    total = len(rows)
    low_confidence = sum(1 for r in rows if r.get("low_confidence_fields"))
    print(f"OK: {total} filas escritas en {output_path}")
    print(f"  Baja confianza en Category: {low_confidence} de {total}")
    print(f"  Alta confianza: {total - low_confidence} de {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
