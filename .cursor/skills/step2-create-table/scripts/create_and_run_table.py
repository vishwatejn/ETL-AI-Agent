"""
create_and_run_table.py
-----------------------
Read the interface columns CSV produced by Step 1, generate an Oracle
CREATE TABLE statement, and write it to a .sql file. Database execution
is performed via SQLcl MCP (see Step 2 SKILL.md), not by this script.

Usage (run from workspace root):
    python .cursor/skills/step2-create-table/scripts/create_and_run_table.py

Inputs:
    config.json                     ->  table_name
    output/<table_name>_interface_columns.csv  or  output/interface_columns.csv

Outputs:
    output/create_table_<TABLE_NAME>.sql
"""

import csv
import json
import os
import sys


# ---------------------------------------------------------------------------
# SQL type mapping
# ---------------------------------------------------------------------------
def column_ddl(name: str, datatype: str, length: str, precision: str, not_null: str) -> str:
    """Return a single column definition line for a CREATE TABLE statement."""
    dt = datatype.strip().upper()

    if dt == "VARCHAR2":
        if length:
            type_str = f"VARCHAR2({length})"
        else:
            type_str = "VARCHAR2(255)"  # safe fallback
    elif dt == "NUMBER":
        if precision:
            type_str = f"NUMBER({precision})"
        else:
            type_str = "NUMBER"
    elif dt in ("DATE", "TIMESTAMP", "CLOB"):
        type_str = dt
    else:
        # Unknown type -- use as-is
        type_str = dt

    constraint = " NOT NULL" if not_null.strip().upper() == "YES" else ""
    return f"    {name} {type_str}{constraint}"


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------
def generate_create_sql(table_name: str, csv_path: str) -> str:
    """Read the interface columns CSV and return a CREATE TABLE statement."""
    columns: list[str] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            col_line = column_ddl(
                name=row["Name"],
                datatype=row["Datatype"],
                length=row.get("Length", ""),
                precision=row.get("Precision", ""),
                not_null=row.get("Not-null", ""),
            )
            columns.append(col_line)

    if not columns:
        print("ERROR: No columns found in CSV.", file=sys.stderr)
        sys.exit(1)

    body = ",\n".join(columns)
    return f"CREATE TABLE {table_name} (\n{body}\n);\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # 1. Read config
    config_path = "config.json"
    if not os.path.isfile(config_path):
        print(f"ERROR: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    table_name = config.get("table_name")
    if not table_name:
        print("ERROR: 'table_name' missing in config.json.", file=sys.stderr)
        sys.exit(1)

    # 2. Locate interface columns CSV (Step 1 output)
    csv_path = os.path.join("output", f"{table_name}_interface_columns.csv")
    if not os.path.isfile(csv_path):
        csv_path = "output/interface_columns.csv"
    if not os.path.isfile(csv_path):
        print("ERROR: No interface columns CSV found. Run Step 1 first.", file=sys.stderr)
        sys.exit(1)

    sql = generate_create_sql(table_name, csv_path)

    # 3. Write .sql file
    os.makedirs("output", exist_ok=True)
    sql_filename = f"create_table_{table_name}.sql"
    sql_path = os.path.join("output", sql_filename)

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"SQL written to {sql_path}")
    print("Execute this DDL via SQLcl MCP (connect, run-sql, disconnect) per Step 2 SKILL.md.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    main()
