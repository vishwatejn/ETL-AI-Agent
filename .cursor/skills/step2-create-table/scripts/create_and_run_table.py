"""
create_and_run_table.py
-----------------------
Read the interface columns CSV produced by Step 1, generate an Oracle
CREATE TABLE statement, write it to a .sql file, then execute it against
an Oracle ATP database using python-oracledb (thin mode) with wallet.

Usage (run from workspace root):
    python .cursor/skills/step2-create-table/scripts/create_and_run_table.py

Inputs:
    config.json                     ->  table_name, atp_username, atp_password,
                                        atp_wallet_file_path, atp_service
    output/interface_columns.csv    ->  Step 1 output

Outputs:
    output/create_table_<TABLE_NAME>.sql
"""

import csv
import json
import os
import sys
import zipfile
import tempfile
import shutil

try:
    import oracledb
except ImportError:
    print(
        "ERROR: python-oracledb is not installed.\n"
        "       Run:  pip install oracledb",
        file=sys.stderr,
    )
    sys.exit(1)


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
# Wallet helpers
# ---------------------------------------------------------------------------
def prepare_wallet(wallet_path: str) -> str:
    """Resolve the wallet location. Accepts a .zip file OR an existing directory."""
    # If it's already a directory, use it directly
    if os.path.isdir(wallet_path):
        print(f"Using wallet directory: {wallet_path}")
        return wallet_path

    # Otherwise treat it as a zip file
    if not os.path.isfile(wallet_path):
        print(f"ERROR: Wallet path not found: {wallet_path}", file=sys.stderr)
        sys.exit(1)

    wallet_dir = os.path.join(tempfile.gettempdir(), "oracle_wallet")

    # Try to clean up any stale wallet directory; ignore errors from locked files
    if os.path.isdir(wallet_dir):
        try:
            shutil.rmtree(wallet_dir)
        except (PermissionError, OSError):
            wallet_dir = tempfile.mkdtemp(prefix="oracle_wallet_")

    if not os.path.isdir(wallet_dir):
        os.makedirs(wallet_dir)

    with zipfile.ZipFile(wallet_path, "r") as zf:
        zf.extractall(wallet_dir)

    print(f"Wallet extracted to: {wallet_dir}")
    return wallet_dir


# ---------------------------------------------------------------------------
# ATP execution
# ---------------------------------------------------------------------------
def table_exists(cursor, table_name: str) -> bool:
    """Check if the table already exists in the current schema."""
    cursor.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :1",
        [table_name.upper()],
    )
    count = cursor.fetchone()[0]
    return count > 0


def parse_tnsnames(wallet_dir: str, service_alias: str) -> dict | None:
    """Parse tnsnames.ora and extract host, port, service_name for the given alias."""
    import re

    tns_path = os.path.join(wallet_dir, "tnsnames.ora")
    if not os.path.isfile(tns_path):
        return None

    with open(tns_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the entry matching the service alias
    pattern = re.compile(
        rf"{re.escape(service_alias)}\s*=\s*(\(description.*?\))\s*$",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(content)
    if not match:
        return None

    desc = match.group(1)
    host_m = re.search(r"host\s*=\s*([\w.\-]+)", desc, re.IGNORECASE)
    port_m = re.search(r"port\s*=\s*(\d+)", desc, re.IGNORECASE)
    svc_m = re.search(r"service_name\s*=\s*([\w.\-]+)", desc, re.IGNORECASE)

    if host_m and port_m and svc_m:
        return {
            "host": host_m.group(1),
            "port": int(port_m.group(1)),
            "service_name": svc_m.group(1),
        }
    return None


def execute_on_atp(sql: str, table_name: str, config: dict) -> None:
    """Connect to Oracle ATP and execute the SQL statement."""
    wallet_dir = prepare_wallet(config["atp_wallet_file_path"])
    service_alias = config["atp_service"]

    # Parse tnsnames.ora for explicit host/port/service_name (avoids hang)
    tns_info = parse_tnsnames(wallet_dir, service_alias)

    print(f"Connecting to ATP service: {service_alias} as {config['atp_username']} ...")

    connect_kwargs = dict(
        user=config["atp_username"],
        password=config["atp_password"],
        wallet_location=wallet_dir,
        wallet_password=None,  # cwallet.sso does not require a password
        tcp_connect_timeout=30,
        retry_count=1,
        retry_delay=2,
    )

    if tns_info:
        # Use explicit params for fast-fail behaviour
        connect_kwargs.update(
            host=tns_info["host"],
            port=tns_info["port"],
            service_name=tns_info["service_name"],
        )
        print(f"  Resolved from tnsnames.ora -> {tns_info['host']}:{tns_info['port']}")
    else:
        # Fall back to DSN alias + config_dir
        connect_kwargs.update(
            dsn=service_alias,
            config_dir=wallet_dir,
        )

    try:
        connection = oracledb.connect(**connect_kwargs)
    except oracledb.Error as e:
        print(f"ERROR: ATP connection failed: {e}", file=sys.stderr)
        print(
            "HINT: Verify that the ATP instance is running, your IP is in the "
            "access control list, and the wallet matches this database.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Connected successfully.")

    cursor = connection.cursor()
    try:
        if table_exists(cursor, table_name):
            print(f"SKIP: Table {table_name} already exists. No action taken.")
            return

        # Remove trailing semicolon for cursor.execute()
        exec_sql = sql.rstrip().rstrip(";")
        cursor.execute(exec_sql)
        connection.commit()
        print(f"SUCCESS: Table {table_name} created.")
    except oracledb.DatabaseError as e:
        print(f"ERROR executing SQL: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cursor.close()
        connection.close()
        print("Connection closed.")


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

    # 2. Generate SQL from CSV (Step 1 writes output/{table_name}_interface_columns.csv)
    csv_path = os.path.join("output", f"{table_name}_interface_columns.csv")
    if not os.path.isfile(csv_path):
        csv_path = "output/interface_columns.csv"
    if not os.path.isfile(csv_path):
        print(f"ERROR: No interface columns CSV found. Run Step 1 first.", file=sys.stderr)
        sys.exit(1)

    sql = generate_create_sql(table_name, csv_path)

    # 3. Write .sql file
    os.makedirs("output", exist_ok=True)
    sql_filename = f"create_table_{table_name}.sql"
    sql_path = os.path.join("output", sql_filename)

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"SQL written to {sql_path}")

    # 4. Execute on ATP
    required_keys = ["atp_username", "atp_password", "atp_wallet_file_path", "atp_service"]
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        print(f"ERROR: Missing config keys for ATP connection: {missing}", file=sys.stderr)
        sys.exit(1)

    execute_on_atp(sql, table_name, config)


if __name__ == "__main__":
    # Ensure output is not buffered so progress prints appear immediately
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    main()
