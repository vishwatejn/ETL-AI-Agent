# Oracle ERP Data Conversion Agent

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
- **python-oracledb** — `pip install oracledb` (required for Step 2)
- **Oracle ATP access** — an Autonomous Transaction Processing database with a wallet file (Steps 2-4)
- **Cursor IDE** — recommended for the skill-based workflow (or run scripts standalone)

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/vishwatejn/Conversion-Agent.git
   cd Conversion-Agent
   ```

2. Install dependencies:
   ```bash
   pip install oracledb
   ```

3. Create your config file:
   ```bash
   cp config.example.json config.json
   ```

4. Edit `config.json` with your values:
   - `interface_table_doc` — Oracle docs URL for the target interface table
   - `table_name` — name for the interface table (e.g. `HZ_IMP_PARTIES_T`)
   - `mapping_sheet_path` — path to your mapping sheet CSV
   - `ctl_file_path` — path to your SQL*Loader control file
   - `atp_username` / `atp_password` — Oracle ATP credentials
   - `atp_wallet_file_path` — path to your downloaded ATP wallet zip
   - `atp_service` — ATP service name (e.g. `yourdb_tp`)

## Usage

### With Cursor IDE (recommended)

Each step is registered as a Cursor skill. Ask the agent to run any step:

- *"Run Step 1"* — fetches interface columns
- *"Run Step 2"* — creates the table on ATP
- *"Run Step 3"* — generates the validation package
- *"Run Step 4"* — generates the spool query

The agent will execute the script, verify the output, and in Step 3, complete any `TODO` items that require AI reasoning.

### Standalone Python Scripts

Run each step directly from the workspace root:

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
