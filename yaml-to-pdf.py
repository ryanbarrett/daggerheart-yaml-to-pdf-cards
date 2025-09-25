#!/usr/bin/env python3
"""
Generate a Letter-size PDF with Investigation Cards arranged in a grid (default 3x3).

INPUT:
  A file containing one or more YAML documents (the output of your Investigation Card Prompt),
  either as:
    - plain multi-doc YAML separated by '---', OR
    - Markdown with fenced ```yaml code blocks (we'll auto-extract the YAML).

Each card supports:
  title, description, reward (optional), insight or consequence, cost (for fear/fail).

USAGE:
  python make_investigation_card_sheet.py cards.yaml -o sheet.pdf

  # Or if you have a Markdown file with YAML code blocks:
  python make_investigation_card_sheet.py cards.md -o sheet.pdf

OPTIONS:
  -o/--output        Output PDF path (default: ./investigation_cards.pdf)
  --rows             Rows per page (default: 3)
  --cols             Columns per page (default: 3)
  --copies           How many times to replicate the full card set (default: 1)
  --margin           Page margin in inches (default: 0.25)
  --gutter           Gutter between cards in inches (default: 0.10)
  --corner           Corner radius in points (default: 10)
  --title-size       Title font size (default: 12)
  --body-size        Body font size (default: 9)

NOTES:
  - If you provide more than (rows*cols) cards after replication, the script will paginate.
  - If you provide fewer cards than fit on a page, the remaining slots will be blank.

Example YAML document (separate multiple documents with ---):

---
title: Success with Hope — Echoes in the Stone
description: >
  The carvings on the temple’s foundation stones are far older than the current bird-folk shrine...
reward: >
  Gain leverage: proof of the Scars of Verdeth’s involvement, tradable in Fort Dendras.
insight: >
  The Scars were here recently; their ash-mark still smolders.
cost:

"""

import argparse
import re
import sys
from pathlib import Path
from textwrap import wrap

import yaml
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

# ----------------------------
# Parsing helpers
# ----------------------------

FENCE_RE = re.compile(r"```(?:yaml)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

REQUIRED_FIELDS = {
    "card_id",
    "title",
    "description",
    "print_layout",
    "scenario",
    "outcome",
}

# Fields that should be normalised into display strings. This includes the
# common descriptive sections that appear on most cards so that lists/dicts
# render predictably when drawn on the PDF.
TEXT_FIELDS = {
    "title",
    "description",
    "reward",
    "insight",
    "cost",
    "features",
    "exits",
    "secret_door",
    "encounter_hooks",
    "traps_hazards",
    "loot",
    "clue_threads",
}



def _stringify_text(value):
    """Convert card text fields into trimmed display strings."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        lines = []
        for item in value:
            item_text = _stringify_text(item)
            if not item_text:
                continue
            item_lines = item_text.split("\n")
            bullet = f"• {item_lines[0]}"
            lines.append(bullet)
            for extra in item_lines[1:]:
                lines.append(f"  {extra}")
        return "\n".join(lines).strip()
    if isinstance(value, dict):
        lines = []
        for key, val in value.items():
            key = str(key)
            val_text = _stringify_text(val)
            if val_text:
                val_lines = val_text.split("\n")
                lines.append(f"{key}: {val_lines[0]}")
                for extra in val_lines[1:]:
                    lines.append(f"  {extra}")
            else:
                lines.append(f"{key}:")
        return "\n".join(lines).strip()
    return str(value).strip()


def _has_required_value(card, field):
    """Return True if the field is present and non-empty for required keys."""

    if field not in card:
        return False
    value = card[field]
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True

def load_cards_from_file(path: Path):
    text = path.read_text(encoding="utf-8")

    # Extract YAML code blocks if present
    blocks = FENCE_RE.findall(text)
    if blocks:
        yaml_text = "\n---\n".join(blocks)
    else:
        yaml_text = text

    # Parse as multi-doc YAML
    docs = [d for d in yaml.safe_load_all(yaml_text) if d]

    # Normalize keys and ensure fields exist
    normalized = []
    for index, d in enumerate(docs, start=1):
        if not isinstance(d, dict):
            raise ValueError(f"Document #{index} is not a mapping and cannot be used as a card definition.")

        nd = {}
        for k, v in d.items():
            if k is None:
                continue
            key = str(k).strip().lower()
            nd[key] = v

        # Allow either 'insight' or 'consequence'
        if "insight" not in nd and "consequence" in nd:
            nd["insight"] = nd["consequence"]

        missing = [field for field in REQUIRED_FIELDS if not _has_required_value(nd, field)]
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(
                f"Document #{index} is missing required field(s): {missing_list}."
            )

        # Normalise types for commonly displayed text fields.
        nd["card_id"] = _stringify_text(nd.get("card_id"))
        nd["title"] = _stringify_text(nd.get("title"))
        nd["description"] = _stringify_text(nd.get("description"))
        nd["outcome"] = _stringify_text(nd.get("outcome"))

        for field in TEXT_FIELDS - {"title", "description"}:
            nd[field] = _stringify_text(nd.get(field, ""))

        normalized.append(nd)

    return normalized


# ----------------------------
# Layout + drawing
# ----------------------------

def draw_cut_guides(canvas: Canvas, page_w, page_h, margin, gutter, cols, rows):
    """
    Light crop/cut guide marks at card boundaries near margins.
    """
    canvas.saveState()
    canvas.setStrokeColor(colors.lightgrey)
    canvas.setLineWidth(0.3)

    # Vertical guides between columns (inside margins)
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    card_w = (usable_w - (cols - 1) * gutter) / cols
    card_h = (usable_h - (rows - 1) * gutter) / rows

    # Vertical lines
    for c in range(1, cols):
        x = margin + c * (card_w + gutter) - gutter / 2.0
        canvas.line(x, margin, x, page_h - margin)

    # Horizontal lines
    for r in range(1, rows):
        y = margin + r * (card_h + gutter) - gutter / 2.0
        canvas.line(margin, y, page_w - margin, y)

    canvas.restoreState()


def wrap_paragraph(text, font_name, font_size, max_width):
    """
    Wrap text to a given pixel width using ReportLab's stringWidth for accuracy.
    Respects existing newline breaks so that bullet lists and multi-line values
    keep their structure.
    """
    if not text:
        return []

    paragraphs = text.replace("\r", "").split("\n")
    wrapped_lines = []

    for para in paragraphs:
        if not para.strip():
            # Preserve deliberate blank lines as spacing markers.
            wrapped_lines.append("")
            continue

        words = para.split()
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if stringWidth(trial, font_name, font_size) <= max_width:
                line = trial
            else:
                if line:
                    wrapped_lines.append(line)
                line = w
        if line:
            wrapped_lines.append(line)

    return wrapped_lines


def draw_card(canvas: Canvas, x, y, w, h, card, fonts, sizes, corner_radius=10):
    """
    Draw a single card within the box at (x,y) with width w and height h.
    (x,y) is bottom-left corner.
    """
    title_font, body_font, bold_font = fonts
    title_size, body_size = sizes

    # Border
    canvas.saveState()
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(1)
    # Rounded rectangle
    canvas.roundRect(x, y, w, h, corner_radius, stroke=1, fill=0)
    canvas.restoreState()

    # Inset padding
    pad = 10  # points
    inner_x = x + pad
    inner_y = y + pad
    inner_w = w - 2 * pad
    inner_h = h - 2 * pad

    cursor_y = inner_y + inner_h

    # Title
    canvas.setFont(title_font, title_size)
    title = card.get("title", "Untitled")
    # Slight bold highlight if it includes an outcome prefix
    title_font_name = bold_font if "—" in title or "-" in title else title_font
    canvas.setFont(title_font_name, title_size)
    title_parts = [seg.strip() for seg in title.split(" - ")]
    for part in title_parts:
        lines = wrap_paragraph(part, title_font_name, title_size, inner_w)
        for line in lines:
            cursor_y -= title_size * 1.2
            canvas.drawString(inner_x, cursor_y, line)

    # Thin divider
    cursor_y -= 4
    canvas.setLineWidth(0.5)
    canvas.setStrokeColor(colors.grey)
    canvas.line(inner_x, cursor_y, inner_x + inner_w, cursor_y)
    cursor_y -= 6

    # Body sections in a consistent order
    sections = [
        ("description", "Description"),
        ("features", "Features"),
        ("exits", "Exits"),
        ("secret_door", "Secret Door"),
        ("encounter_hooks", "Encounter Hooks"),
        ("traps_hazards", "Traps & Hazards"),
        ("loot", "Loot"),
        ("clue_threads", "Clue Threads"),
        ("reward", "Reward"),
        ("insight", "Insight"),
        ("cost", "Cost"),
    ]

    canvas.setFont(body_font, body_size)
    for key, label in sections:
        val = card.get(key, "")
        if not val:
            continue
        # Label
        lbl = f"{label}:"
        lbl_w = stringWidth(lbl, bold_font, body_size)
        cursor_y -= body_size * 1.15
        canvas.setFont(bold_font, body_size)
        canvas.drawString(inner_x, cursor_y, lbl)
        # Text wrapped to width
        canvas.setFont(body_font, body_size)
        lines = wrap_paragraph(val, body_font, body_size, inner_w)
        for ln in lines:
            cursor_y -= body_size * 1.15
            if cursor_y < inner_y + body_size:  # simple overflow guard
                # Truncate with ellipsis if overflow
                ell = "…"
                ell_w = stringWidth(ell, body_font, body_size)
                canvas.drawString(inner_x, inner_y + body_size, ell)
                return
            if not ln:
                # Blank spacer line for readability
                continue
            canvas.drawString(inner_x, cursor_y, ln)


def paginate(cards, rows, cols):
    per_page = rows * cols
    for i in range(0, len(cards), per_page):
        yield cards[i:i + per_page]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Path to YAML/Markdown with card docs")
    ap.add_argument("-o", "--output", type=Path, default=Path("investigation_cards.pdf"))
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--copies", type=int, default=1,
                    help="Replicate the full card set this many times")
    ap.add_argument("--margin", type=float, default=0.25, help="Page margin in inches")
    ap.add_argument("--gutter", type=float, default=0.10, help="Gutter between cards in inches")
    ap.add_argument("--corner", type=float, default=10, help="Corner radius in points")
    ap.add_argument("--title-size", type=int, default=12)
    ap.add_argument("--body-size", type=int, default=9)
    args = ap.parse_args()

    try:
        base_cards = load_cards_from_file(args.input)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    if not base_cards:
        print("No cards parsed. Make sure your file contains valid YAML documents.", file=sys.stderr)
        sys.exit(1)

    # Replicate the cards N times to fill the sheet(s)
    cards = []
    for _ in range(max(1, args.copies)):
        cards.extend(base_cards)

    # Page + grid math
    page_w, page_h = letter
    margin = args.margin * inch
    gutter = args.gutter * inch
    rows, cols = args.rows, args.cols

    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    card_w = (usable_w - (cols - 1) * gutter) / cols
    card_h = (usable_h - (rows - 1) * gutter) / rows

    canvas = Canvas(str(args.output), pagesize=letter)

    fonts = ("Helvetica", "Helvetica", "Helvetica-Bold")
    sizes = (args.title_size, args.body_size)

    for page_cards in paginate(cards, rows, cols):
        draw_cut_guides(canvas, page_w, page_h, margin, gutter, cols, rows)
        # Draw in reading order: top-left to bottom-right
        for i, card in enumerate(page_cards):
            r = i // cols
            c = i % cols
            # Convert to "top-left origin" for rows
            x = margin + c * (card_w + gutter)
            # from top down: row 0 is top
            y_top_origin = page_h - margin - card_h - r * (card_h + gutter)
            draw_card(canvas, x, y_top_origin, card_w, card_h, card, fonts, sizes, corner_radius=args.corner)
        canvas.showPage()

    canvas.save()
    print(f"Wrote {args.output} with {len(cards)} cards across {len(list(paginate(cards, rows, cols)))} page(s).")


if __name__ == "__main__":
    main()
