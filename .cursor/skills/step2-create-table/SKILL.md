---
name: step2-create-table
description: Generate an Oracle CREATE TABLE SQL from the Step 1 interface columns CSV and execute it on ATP. Use when the user asks to create the interface table, run Step 2, or set up the ATP table for the Conversion Agent.
---

# Step 2 -- Create Interface Table on ATP

Generate a `CREATE TABLE` statement from the Step 1 CSV and execute it against an Oracle ATP database.

## Prerequisites

- Step 1 complete: `output/interface_columns.csv` must exist.
- `config.json` must contain: `table_name`, `atp_username`, `atp_password`, `atp_wallet_file_path`, `atp_service`.
- Python 3 with `oracledb` installed (`pip install oracledb`).

## Utility script

**scripts/create_and_run_table.py** -- reads the CSV, builds the DDL, writes the `.sql` file, connects to ATP via python-oracledb thin mode with wallet, and executes.

Run from the **workspace root**:

```bash
python .cursor/skills/step2-create-table/scripts/create_and_run_table.py
```

## Workflow

```
Task Progress:
- [ ] Step 1: Run the script
- [ ] Step 2: Verify SQL file
- [ ] Step 3: Confirm ATP execution
```

### Step 1 -- Run the script

Execute the command above. The script will:

1. Read `config.json` for `table_name` and ATP connection details.
2. Read `output/interface_columns.csv`.
3. Generate a `CREATE TABLE` statement applying the mapping rules below.
4. Write `output/create_table_<TABLE_NAME>.sql`.
5. Unzip the wallet, connect to ATP, and execute the DDL.

### Step 2 -- Verify SQL file

Read the first ~20 lines and last ~5 lines of the generated `.sql` file. Confirm column definitions look correct.

### Step 3 -- Confirm ATP execution

Check the script's stdout. Expected messages:

- `SQL written to output/create_table_HZ_IMP_PARTIES_T.sql`
- `Connected successfully.`
- `SUCCESS: Table HZ_IMP_PARTIES_T created.` -- or --
- `SKIP: Table HZ_IMP_PARTIES_T already exists. No action taken.`

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

If the table already exists in the schema, the script **skips** creation and prints a SKIP message. No DROP is performed.

## Expected outputs

```
output/create_table_HZ_IMP_PARTIES_T.sql
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
| ATP connection fails | Print error and exit |
| Table already exists | Skip creation, print SKIP message |
| `oracledb` not installed | Print install instructions and exit |
