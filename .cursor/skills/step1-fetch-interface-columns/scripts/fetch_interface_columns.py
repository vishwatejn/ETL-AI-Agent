"""
fetch_interface_columns.py
--------------------------
Fetch an Oracle ERP interface-table documentation page, parse the HTML
Columns table (identified by <table summary="Columns">), and write selected
column metadata to a CSV file.

Usage (run from workspace root):
    python .cursor/skills/step1-fetch-interface-columns/scripts/fetch_interface_columns.py

Inputs:
    config.json  ->  { "interface_table_doc": "<oracle-docs-url>" }

Outputs:
    output/{table_name}_interface_columns.csv  (Name, Datatype, Length, Precision, Not-null, Status)
"""

import json
import urllib.request
import csv
import os
import sys
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# HTML parser that extracts the <table summary="Columns"> from Oracle docs
# ---------------------------------------------------------------------------
class ColumnsTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_target_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.row_is_header = False
        self.current_row: list[str] = []
        self.current_cell = ""
        self.headers: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "table" and ad.get("summary") == "Columns":
            self.in_target_table = True
            self.table_depth = 1
            return
        if not self.in_target_table:
            return
        if tag == "table":
            self.table_depth += 1
        elif tag == "tr":
            self.in_row = True
            self.current_row = []
            self.row_is_header = False
        elif tag == "th":
            self.in_cell = True
            self.row_is_header = True
            self.current_cell = ""
        elif tag == "td":
            self.in_cell = True
            self.current_cell = ""

    def handle_endtag(self, tag):
        if not self.in_target_table:
            return
        if tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_target_table = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                if self.row_is_header:
                    self.headers = [c.strip() for c in self.current_row]
                else:
                    self.rows.append([c.strip() for c in self.current_row])
        elif tag in ("th", "td") and self.in_cell:
            self.current_row.append(self.current_cell)
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data

    def handle_entityref(self, name):
        if self.in_cell:
            self.current_cell += f"&{name};"

    def handle_charref(self, name):
        if self.in_cell:
            self.current_cell += f"&#{name};"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
TARGET_COLUMNS = ["Name", "Datatype", "Length", "Precision", "Not-null", "Status"]


def main():
    # 1. Read config
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"ERROR: {config_path} not found in workspace root.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    url = config.get("interface_table_doc")
    if not url:
        print("ERROR: 'interface_table_doc' key missing in config.json.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching: {url}")

    # 2. Fetch HTML
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")

    # 3. Parse the Columns table
    parser = ColumnsTableParser()
    parser.feed(html)

    if not parser.headers:
        print("ERROR: Could not find <table summary='Columns'> in the page.", file=sys.stderr)
        sys.exit(1)

    print(f"Headers found ({len(parser.headers)}): {parser.headers}")
    print(f"Data rows parsed: {len(parser.rows)}")

    # 4. Build column index map for target columns
    idx_map = {}
    for tc in TARGET_COLUMNS:
        for i, h in enumerate(parser.headers):
            if h.strip().lower() == tc.lower():
                idx_map[tc] = i
                break

    missing = [tc for tc in TARGET_COLUMNS if tc not in idx_map]
    if missing:
        print(f"WARNING: These target columns were not found in headers: {missing}", file=sys.stderr)

    print(f"Column index map: {idx_map}")

    # 5. Write CSV
    os.makedirs("output", exist_ok=True)
    table_name = config.get("table_name")
    if not table_name:
        print("ERROR: 'table_name' key missing in config.json.", file=sys.stderr)
        sys.exit(1)

    print(f"Table name: {table_name}")
    out_path = f"output/{table_name}_interface_columns.csv"
    

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(TARGET_COLUMNS)
        for row in parser.rows:
            csv_row = []
            for tc in TARGET_COLUMNS:
                i = idx_map.get(tc)
                if i is not None and i < len(row):
                    csv_row.append(row[i].strip())
                else:
                    csv_row.append("")
            writer.writerow(csv_row)

    print(f"CSV written to {out_path} ({len(parser.rows)} rows)")


if __name__ == "__main__":
    main()
