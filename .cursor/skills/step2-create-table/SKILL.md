---
name: step2-create-table
description: Generate an Oracle CREATE TABLE SQL from the Step 1 interface columns CSV and execute it via SQLcl MCP. Use when the user asks to create the interface table, run Step 2, or set up the ATP table for the Conversion Agent.
---

# Step 2 -- Create Interface Table on ATP

Generate a `CREATE TABLE` statement from the Step 1 CSV, write it to a `.sql` file, and execute it against the database using **SQLcl MCP** (no python-oracledb or wallet in scripts).

## Prerequisites

- Step 1 complete: `output/interface_columns.csv` (or `output/<table_name>_interface_columns.csv`) must exist.
- `config.json` must contain: `table_name`, `sqlcl_connection_name` (name of a saved SQLcl connection to use for execution).
- Python 3 available on PATH (no `oracledb` required).

## Utility script

**scripts/create_and_run_table.py** -- reads the CSV, builds the DDL, and writes `output/create_table_<TABLE_NAME>.sql`. It does **not** connect to the database; execution is done via SQLcl MCP.

Run from the **workspace root**:

```bash
python .cursor/skills/step2-create-table/scripts/create_and_run_table.py
```

## Workflow

```
Task Progress:
- [ ] Step 1: Run the script (generate DDL)
- [ ] Step 2: Verify SQL file
- [ ] Step 3: Execute on DB via SQLcl MCP
```

### Step 1 -- Run the script

Execute the command above. The script will:

1. Read `config.json` for `table_name`.
2. Read the interface columns CSV from `output/`.
3. Generate a `CREATE TABLE` statement using the mapping rules below.
4. Write `output/create_table_<TABLE_NAME>.sql`.

### Step 2 -- Verify SQL file

Read the first ~20 lines and last ~5 lines of the generated `.sql` file. Confirm column definitions look correct.

### Step 3 -- Execute on DB via SQLcl MCP

Use the **user-sqlcl** MCP server to run the DDL against the database:

1. **Connect**: Call the `connect` tool with `connection_name` = the value of `config.json` → `sqlcl_connection_name`. (Connection name is case-sensitive.)
2. **Skip if table exists**: Call `run-sql` with a query that checks existence, e.g.  
   `SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER('<TABLE_NAME>');`  
   If the result indicates the table already exists, skip creation and report: `SKIP: Table <TABLE_NAME> already exists. No action taken.`
3. **Create table**: If the table does not exist, read the contents of `output/create_table_<TABLE_NAME>.sql`, strip trailing semicolons if needed for the tool, and execute via `run-sql` (or `run-sqlcl` for multi-statement scripts).
4. **Confirm**: Report `SUCCESS: Table <TABLE_NAME> created.`
5. **Disconnect**: Call the `disconnect` tool to close the session.

## SQL mapping rules

| CSV Datatype | CSV field used | Oracle DDL |
|---|---|---|
| VARCHAR2 | Length | `VARCHAR2(length)` |
| NUMBER | Precision | `NUMBER(precision)` if present, else `NUMBER` |
| DATE | -- | `DATE` |
| TIMESTAMP | -- | `TIMESTAMP` |
| CLOB | -- | `CLOB` |

- `Not-null = Yes` adds a `NOT NULL` constraint.

## Existing table behavior

If the table already exists in the schema, do **not** run the CREATE TABLE; report SKIP. No DROP is performed.

## Expected outputs

```
output/create_table_<TABLE_NAME>.sql
```

Sample header:

```sql
CREATE TABLE HZ_IMP_PARTIES_T (
    PARTY_T_ID NUMBER(18),
    INTERFACE_ROW_ID NUMBER(18),
    BATCH_ID NUMBER(18) NOT NULL,
    PARTY_ORIG_SYSTEM VARCHAR2(30),
    ...
);
```

## Error handling

| Condition | Action |
|---|---|
| `interface_columns.csv` missing | Stop with error; run Step 1 first |
| `table_name` missing in config | Stop with error |
| `sqlcl_connection_name` missing in config | Stop with error; add to config or use list-connections to choose a name |
| SQLcl MCP connect fails (invalid or unknown connection) | Tell user to create/fix the named connection in SQLcl and ensure the name matches exactly (case-sensitive) |
| `run-sql` execution fails | Report the error; suggest checking object name, privileges, and that the connection targets the correct schema |
| Table already exists | Skip creation, report SKIP message |
