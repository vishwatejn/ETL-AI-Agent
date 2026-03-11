# Oracle ERP Data Conversion AI Agent

An AI-powered agent that automates validation, transformation, and load file creation for Oracle ERP interface tables. Built as a set of Cursor IDE skills, it takes an Oracle interface table documentation URL and a mapping sheet as input and produces validated, export-ready data.

## How It Works

The agent follows a 4-step pipeline. Each step is an independent Cursor skill backed by a Python script.

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Step 1              │     │  Step 2              │     │  Step 3              │     │  Step 4              │
│  Fetch Interface     │────▶│  Create Table        │────▶│  Generate Validation │────▶│  Generate Spool      │
│  Columns             │     │  on ATP              │     │  Package             │     │  Query               │
│                      │     │                      │     │                      │     │                      │
│  Scrapes Oracle docs │     │  Builds CREATE TABLE │     │  Reads mapping sheet │     │  Parses .ctl file    │
│  for column metadata │     │  DDL and executes    │     │  and generates PL/SQL│     │  and creates spool   │
│  → CSV               │     │  on Oracle ATP       │     │  validation package  │     │  export query        │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

**Step 1** — Fetches column metadata (name, datatype, length, precision, not-null, status) from an Oracle ERP interface table docs page and writes it to CSV.

**Step 2** — Reads the CSV from Step 1, generates a `CREATE TABLE` statement respecting datatypes and constraints, and executes it on an Oracle ATP database.

**Step 3** — Reads a mapping sheet CSV that defines mandatory fields, validation rules, and transformations. Generates a PL/SQL package (`.pks` + `.pkb`) with deterministic validation logic. Complex rules are emitted as `TODO` comments for AI-assisted completion.

**Step 4** — Parses the SQL*Loader control file (`.ctl`) to extract columns in load order and generates a SQL*Plus spool query that exports validated rows to CSV.

## Project Structure

```
.
├── config.json                          # Your local config (not committed)
├── config.example.json                  # Template with placeholder values
├── parties_mapping_sheet.csv            # Sample mapping sheet
├── HzImpPartiesT.ctl                   # Sample SQL*Loader control file
├── output/                              # Generated artifacts (not committed)
│   ├── *_interface_columns.csv
│   ├── create_table_*.sql
│   ├── *_VAL_PKG.pks
│   ├── *_VAL_PKG.pkb
│   ├── *_mapping_rules.json
│   └── *_Spool_Query.sql
└── .cursor/skills/
    ├── step1-fetch-interface-columns/
    │   ├── SKILL.md
    │   └── scripts/fetch_interface_columns.py
    ├── step2-create-table/
    │   ├── SKILL.md
    │   └── scripts/create_and_run_table.py
    ├── step3-generate-validation-package/
    │   ├── SKILL.md
    │   ├── scripts/generate_validation_package.py
    │   └── templates/
    │       ├── package_spec.tpl.sql
    │       └── package_body.tpl.sql
    └── step4-generate-spool-query/
        ├── SKILL.md
        ├── scripts/generate_spool_query.py
        └── templates/spool_query.tpl.sql
```

## Prerequisites

- **Python 3** (3.8+)
- **Oracle database access** — ATP (or another Oracle DB) reachable from your saved SQLcl connection (Steps 2-4)
- **Cursor IDE** — recommended for the skill-based workflow (or run scripts standalone)
- **SQLcl MCP** — Cursor MCP server used by the agent to run DDL and SQL against Oracle (Steps 2–4). See [SQLcl MCP dependency](#sqlcl-mcp-dependency) below.

### SQLcl MCP dependency

Steps **2**, **3**, and **4** run SQL against your Oracle database (create table, deploy package, run spool query). The agent does this through the **SQLcl MCP** server, not via Python or a wallet in scripts. You must:

1. **Enable the SQLcl MCP server** in Cursor (e.g. add and enable the `user-sqlcl` / SQLcl MCP server in your Cursor MCP settings).
2. **Create a named connection in SQLcl** for your Oracle ATP (or other Oracle) database. The connection name is arbitrary (e.g. `atp_dev`, `conversion_db`).
3. **Bind the connection to this project** by setting `sqlcl_connection_name` in `config.json` to that exact connection name. The name is **case-sensitive**; it must match the saved connection in SQLcl.

The agent then uses the MCP tools `connect`, `run-sql` / `run-sqlcl`, and `disconnect` with `connection_name` = `config.json` → `sqlcl_connection_name`. You can discover available connection names with the MCP tool `list-connections`. If `sqlcl_connection_name` is missing or invalid, the agent will report an error and ask you to fix the config or create the connection in SQLcl.

| Step | SQLcl MCP usage |
|------|-----------------|
| 2 | Connect, run CREATE TABLE DDL, disconnect |
| 3 | Connect, run package spec/body, disconnect (optional deploy) |
| 4 | Connect, run spool query (optional), disconnect |

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/vishwatejn/ETL-AI-Agent.git
   cd ETL-AI-Agent
   ```

2. Install dependencies:
   - Install **SQLcl**: https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/
   - In Cursor, enable/configure your SQLcl MCP server (for this repo: `user-sqlcl`).
   - Verify a named SQLcl connection exists (or create one) that points to your target DB.

3. Create your config file:
   ```bash
   cp config.example.json config.json
   ```

4. Edit `config.json` with your values:
   - `interface_table_doc` — Oracle docs URL for the target interface table
   - `table_name` — name for the interface table (e.g. `HZ_IMP_PARTIES_T`)
   - `mapping_sheet_path` — path to your mapping sheet CSV
   - `ctl_file_path` — path to your SQL*Loader control file
   - `sqlcl_connection_name` — name of the saved SQLcl connection to use for Steps 2–4 (must match exactly; see [SQLcl MCP dependency](#sqlcl-mcp-dependency))

## Usage

### With Cursor IDE (recommended)

Each step is registered as a Cursor skill. Ask the agent to run any step:

- *"Run Step 1"* — fetches interface columns
- *"Run Step 2"* — creates the table on ATP
- *"Run Step 3"* — generates the validation package
- *"Run Step 4"* — generates the spool query

The agent will execute the script, verify the output, and in Step 3, complete any `TODO` items that require AI reasoning.

### Standalone Python Scripts

Run each step directly from the workspace root to generate artifacts. For DB execution in Steps 2-4, use Cursor + SQLcl MCP (or run the generated SQL manually in SQLcl):

```bash
# Step 1: Fetch interface table columns → output/*_interface_columns.csv
python .cursor/skills/step1-fetch-interface-columns/scripts/fetch_interface_columns.py

# Step 2: Create table on ATP → output/create_table_*.sql
python .cursor/skills/step2-create-table/scripts/create_and_run_table.py

# Step 3: Generate validation package → output/*_VAL_PKG.pks, .pkb
python .cursor/skills/step3-generate-validation-package/scripts/generate_validation_package.py

# Step 4: Generate spool query → output/*_Spool_Query.sql
python .cursor/skills/step4-generate-spool-query/scripts/generate_spool_query.py
```

## Output

| Step | Generated Files | Description |
|------|----------------|-------------|
| 1 | `output/<TABLE>_interface_columns.csv` | Column metadata extracted from Oracle docs |
| 2 | `output/create_table_<TABLE>.sql` | DDL executed on ATP |
| 3 | `output/<TABLE>_VAL_PKG.pks` | PL/SQL package specification |
| 3 | `output/<TABLE>_VAL_PKG.pkb` | PL/SQL package body with validation logic |
| 3 | `output/<TABLE>_mapping_rules.json` | Parsed rules for traceability |
| 4 | `output/<TABLE>_Spool_Query.sql` | SQL*Plus spool export query |
