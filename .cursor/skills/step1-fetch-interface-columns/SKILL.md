---
name: step1-fetch-interface-columns
description: Fetch Oracle ERP interface table column metadata from config-driven URL and write to CSV. Use when the user asks to extract interface table columns, run Step 1, or build the interface column list for the Conversion Agent.
---

# Step 1 -- Fetch Interface Table Columns

Extract column metadata from an Oracle ERP interface-table documentation page and save the result as a CSV file.

## Prerequisites

- `config.json` must exist in the workspace root with an `interface_table_doc` key containing a valid Oracle docs URL.
- Python 3 available on PATH.

## Utility script

**scripts/fetch_interface_columns.py** -- fetches the Oracle docs page, parses the HTML `<table summary="Columns">`, extracts the 6 target fields, and writes the CSV.

Run from the **workspace root**:

```bash
python .cursor/skills/step1-fetch-interface-columns/scripts/fetch_interface_columns.py
```

The script will:

1. Read `config.json` -> `interface_table_doc` URL.
2. HTTP-GET the page and parse the Columns table using Python's `html.parser`.
3. Map each `<tr>` to the 7 HTML headers (Name, Datatype, Length, Precision, Not-null, Comments, Status).
4. Drop the Comments column and write the remaining 6 fields to `output/interface_columns.csv`.

## Workflow

```
Task Progress:
- [ ] Step 1: Run the script
- [ ] Step 2: Verify output
```

### Step 1 -- Run the script

Execute the command above from the workspace root. The script prints progress to stdout and errors to stderr.

### Step 2 -- Verify output

Read back the first 10 lines of `output/interface_columns.csv` and confirm:

- The header matches `Name,Datatype,Length,Precision,Not-null,Status`.
- Row count is > 0.
- No stray HTML or markdown artefacts remain.

## How the parser works

The HTML parser targets `<table summary="Columns">` and maps cells by position:

| Column position | Oracle HTML header | Kept in CSV? |
|---|---|---|
| 0 | Name | Yes |
| 1 | Datatype | Yes |
| 2 | Length | Yes |
| 3 | Precision | Yes |
| 4 | Not-null | Yes |
| 5 | Comments | No (dropped) |
| 6 | Status | Yes |

- VARCHAR2 columns store their size in **Length** (e.g. `VARCHAR2, Length=30`).
- NUMBER columns store their size in **Precision** (e.g. `NUMBER, Precision=18`).

## Expected output

```
output/{table_name}_interface_columns.csv
```

Sample rows:

```csv
Name,Datatype,Length,Precision,Not-null,Status
PARTY_T_ID,NUMBER,18,,,Active
BATCH_ID,NUMBER,18,,Yes,Active
PARTY_ORIG_SYSTEM,VARCHAR2,30,,,Active
```

## Error handling

| Condition | Action |
|---|---|
| `interface_table_doc` key missing in config | Stop and notify user |
| WebFetch fails or returns empty | Retry once; if still failing, stop and notify user |
| Columns table not found in response | Stop and notify user with the fetched content snippet |
| Row has fewer than 2 cells after split | Skip the row and log a warning |
