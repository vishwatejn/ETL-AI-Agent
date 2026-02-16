"""
generate_spool_query.py
-----------------------
Parse an Oracle SQL*Loader control file (.ctl), extract the column list
in order, and generate a SQL*Plus spool query that SELECTs those columns
from the interface table.

Usage (run from workspace root):
    python .cursor/skills/step4-generate-spool-query/scripts/generate_spool_query.py

Inputs:
    config.json  ->  { "ctl_file_path": "...", "table_name": "..." }

Outputs:
    output/<TABLE_NAME>_Spool_Query.sql
"""

import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(SKILL_DIR, "templates")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def read_config():
    """Read and validate config.json."""
    config_path = "config.json"
    if not os.path.isfile(config_path):
        print(f"ERROR: {config_path} not found in workspace root.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required = ["ctl_file_path", "table_name"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"ERROR: Missing config keys: {missing}", file=sys.stderr)
        sys.exit(1)

    return config


# ---------------------------------------------------------------------------
# CTL parser
# ---------------------------------------------------------------------------
def parse_ctl_columns(ctl_path):
    """Parse a SQL*Loader .ctl file and return column names in order.

    Rules:
      - Only the block between the first '(' and matching ')' is inspected.
      - Each non-blank line inside the block is a column entry.
      - Lines containing 'constant' are skipped (e.g. LOAD_REQUEST_ID constant ...).
      - Type annotations like CHAR(360), INTEGER EXTERNAL, DATE "..." are stripped;
        only the leading column name is kept.
      - Trailing commas are removed.
    """
    if not os.path.isfile(ctl_path):
        print(f"ERROR: CTL file not found: {ctl_path}", file=sys.stderr)
        sys.exit(1)

    with open(ctl_path, encoding="utf-8") as f:
        content = f.read()

    # Locate the column block between ( and )
    open_paren = content.find("(")
    close_paren = content.rfind(")")
    if open_paren == -1 or close_paren == -1 or close_paren <= open_paren:
        print("ERROR: Could not find column block (...) in CTL file.", file=sys.stderr)
        sys.exit(1)

    block = content[open_paren + 1 : close_paren]
    columns = []

    for raw_line in block.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # Skip constant definitions
        if re.search(r"\bconstant\b", line, re.IGNORECASE):
            print(f"  Skipping constant: {line.strip()}")
            continue

        # Remove trailing comma
        line = line.rstrip(",").strip()
        if not line:
            continue

        # Extract the leading column name (first token)
        # Handles: "ORGANIZATION_NAME CHAR(360)"  -> ORGANIZATION_NAME
        #          "BATCH_ID,"                     -> BATCH_ID
        #          "EXPENDITURE_ITEM_DATE DATE \"YYYY-MM-DD\"" -> EXPENDITURE_ITEM_DATE
        col_name = re.split(r"\s+", line)[0].strip().upper()

        # Sanity: column name should be a valid SQL identifier
        if re.match(r"^[A-Z_][A-Z0-9_$#]*$", col_name):
            columns.append(col_name)
        else:
            print(f"  WARNING: Skipping non-identifier token: '{col_name}'")

    return columns


def detect_batch_column(columns):
    """Auto-detect the batch column from the column list.

    Looks for a column whose name contains 'BATCH' (case-insensitive).
    Falls back to 'BATCH_ID'.
    """
    for col in columns:
        if "BATCH" in col.upper():
            return col
    return "BATCH_ID"


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def read_template(name):
    """Read a SQL template file from the templates/ directory."""
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.isfile(path):
        print(f"ERROR: Template not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return f.read()


def format_select_columns(columns):
    """Format columns into a comma-separated SELECT list, one per line."""
    if not columns:
        return ""
    lines = []
    for i, col in enumerate(columns):
        suffix = "," if i < len(columns) - 1 else ""
        lines.append(f"{col}{suffix}")
    return "\n".join(lines)


def render(template_text, replacements):
    """Replace all {{KEY}} placeholders in template_text."""
    result = template_text
    for key, val in replacements.items():
        result = result.replace("{{" + key + "}}", val)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    config = read_config()
    table_name = config["table_name"]
    ctl_path = config["ctl_file_path"]

    print(f"Table name : {table_name}")
    print(f"CTL file   : {ctl_path}")
    print()

    # 1. Parse CTL columns
    print("Parsing CTL file...")
    columns = parse_ctl_columns(ctl_path)

    if not columns:
        print("ERROR: No columns found in CTL file.", file=sys.stderr)
        sys.exit(1)

    print(f"  Extracted {len(columns)} columns (excluding constants).")
    print()

    # 2. Detect batch column
    batch_col = detect_batch_column(columns)
    print(f"Batch column: {batch_col}")

    # Warn if batch column is not BATCH_ID
    if batch_col != "BATCH_ID":
        print(
            f"  NOTE: Batch column is '{batch_col}' (not 'BATCH_ID'). "
            f"WHERE clause will use '{batch_col} = :p_batch_id'."
        )
    print()

    # 3. Build spool CSV path and output SQL path
    spool_csv_path = f"output/{table_name}_Spool.csv"
    output_sql_name = f"{table_name}_Spool_Query.sql"
    output_sql_path = os.path.join("output", output_sql_name)

    # 4. Format SELECT column list
    select_columns = format_select_columns(columns)

    # 5. Render template
    print("Rendering spool query...")
    template = read_template("spool_query.tpl.sql")
    sql = render(
        template,
        {
            "TABLE_NAME": table_name,
            "SPOOL_CSV_PATH": spool_csv_path,
            "BATCH_COLUMN": batch_col,
            "SELECT_COLUMNS": select_columns,
        },
    )

    # 6. Write output
    os.makedirs("output", exist_ok=True)
    with open(output_sql_path, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"\nSpool query written to {output_sql_path}")
    print(f"  Spool CSV target : {spool_csv_path}")
    print(f"  SELECT columns   : {len(columns)}")
    print(f"  Batch filter     : {batch_col} = :p_batch_id")
    print(f"\nDone.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    main()
