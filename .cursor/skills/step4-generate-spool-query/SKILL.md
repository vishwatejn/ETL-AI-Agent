---
name: step4-generate-spool-query
description: Generate a SQL*Plus spool query from the CTL file column order and run it via SQLcl MCP. Use when the user asks to create the spool query, run Step 4, or export validated data from the ATP interface table for the Conversion Agent.
---

# Step 4 -- Generate Spool Query

Parse the SQL*Loader control file (.ctl), extract columns in order, generate a SQL*Plus spool query that exports validated rows from the interface table to CSV, and optionally execute it using **SQLcl MCP**.

## Prerequisites

- Steps 1-3 complete (interface table exists on ATP with validated data).
- `config.json` must contain: `ctl_file_path`, `table_name`. For running the spool in the DB: `sqlcl_connection_name`.
- The CTL file must have a column block between `(` and `)`.
- Python 3 available on PATH.

## Utility script

**scripts/generate_spool_query.py** -- reads the CTL file, extracts columns, and renders the spool SQL from a template. It does not connect to the database; execution is done via SQLcl MCP.

Run from the **workspace root**:

```bash
python .cursor/skills/step4-generate-spool-query/scripts/generate_spool_query.py
```

The script will:

1. Read `config.json` -> `ctl_file_path` and `table_name`.
2. Parse the CTL file to extract columns between `(` and `)`.
3. Skip `constant` definitions (e.g. `LOAD_REQUEST_ID constant '#LOADREQUESTID#'`).
4. Strip type annotations (e.g. `CHAR(360)`, `INTEGER EXTERNAL`) keeping only column names.
5. Auto-detect the batch filter column (first column containing "BATCH").
6. Render the spool SQL from template with columns in exact CTL order.
7. Write `output/<TABLE_NAME>_Spool_Query.sql`.

## Workflow

```
Task Progress:
- [ ] Step 1: Run the generator script
- [ ] Step 2: Verify output
- [ ] Step 3 (optional): Run spool query via SQLcl MCP
```

### Step 1 -- Run the generator script

Execute the command above from the workspace root. The script prints progress to stdout.

### Step 2 -- Verify output

Read back `output/<TABLE_NAME>_Spool_Query.sql` and confirm:

- SQL*Plus settings block is present (`set colsep`, `set heading OFF`, `set markup csv on`, etc.).
- `Spool` path is `output/<TABLE_NAME>_Spool.csv`.
- SELECT column list matches CTL file column order exactly (excluding constant fields).
- No type annotations remain (e.g. no `CHAR(360)` in SELECT).
- WHERE clause is `STATUS = 'V' AND <BATCH_COLUMN> = :p_batch_id`.
- `spool OFF;` at the end.

### Step 3 (optional) -- Run spool query via SQLcl MCP

If the user wants to export data and `config.json` contains `sqlcl_connection_name`:

1. **Connect**: Call the `connect` tool with `connection_name` = `config.json` → `sqlcl_connection_name`.
2. **Set bind variable**: The spool query uses `:p_batch_id`. Use `run-sqlcl` to set the variable and run the script, or run the SELECT part via `run-sql` with the batch id substituted, then write results to the expected CSV path as needed. Prefer `run-sqlcl` with the full contents of `output/<TABLE_NAME>_Spool_Query.sql` (with `p_batch_id` set first) when the MCP supports multi-statement execution and spool semantics.
3. **Disconnect**: Call the `disconnect` tool.

If SQLcl MCP does not support spool-to-file, inform the user they can run the generated `.sql` file locally with SQLcl/SQL*Plus after setting `p_batch_id`.

## CTL parsing rules

| CTL line pattern | Action |
|---|---|
| `COLUMN_NAME,` | Extract `COLUMN_NAME` |
| `COLUMN_NAME CHAR(N),` | Extract `COLUMN_NAME` (strip `CHAR(N)`) |
| `COLUMN_NAME INTEGER EXTERNAL,` | Extract `COLUMN_NAME` (strip `INTEGER EXTERNAL`) |
| `COLUMN_NAME DATE "fmt",` | Extract `COLUMN_NAME` (strip `DATE "..."`) |
| `COLUMN_NAME constant '...'` | Skip entirely (not included in SELECT) |
| Blank lines | Skip |

## Expected output

```
output/<TABLE_NAME>_Spool_Query.sql
```

Sample output for `HZ_IMP_PARTIES_T`:

```sql
set colsep      ;
set headsep off  ;
set pagesize 0   ;
set trimspool on ;
set heading OFF  ;
set FEEDBACK OFF ;
set markup csv on;

Spool 'output/HZ_IMP_PARTIES_T_Spool.csv';
---HZ_IMP_PARTIES_T
select
/*csv*/
distinct
BATCH_ID,
PARTY_ORIG_SYSTEM,
...
ATTRIBUTE30
from HZ_IMP_PARTIES_T WHERE STATUS = 'V' AND BATCH_ID = :p_batch_id;
spool OFF;
```

## Error handling

| Condition | Action |
|---|---|
| `ctl_file_path` missing in config | Stop with error |
| `table_name` missing in config | Stop with error |
| CTL file not found | Stop with error |
| No column block `(...)` in CTL | Stop with error |
| No parseable columns found | Stop with error |
| Batch column is not `BATCH_ID` | Print NOTE (uses detected name in WHERE clause) |
| Non-identifier token in column block | Print WARNING and skip the token |
| SQLcl MCP connect/run-sqlcl fails | Report error; suggest running the generated .sql file locally with SQLcl |
