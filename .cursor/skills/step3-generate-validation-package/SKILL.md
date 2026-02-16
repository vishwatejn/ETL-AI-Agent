---
name: step3-generate-validation-package
description: Generate an Oracle PL/SQL validation package (.pks, .pkb) from the mapping sheet CSV. Use when the user asks to create the validation package, run Step 3, or generate validation/transformation logic for the Conversion Agent.
---

# Step 3 -- Generate Validation Package

Read the mapping sheet CSV, generate Oracle PL/SQL validation and transformation package files, and save them to `/output`.

## Prerequisites

- Steps 1 and 2 complete (interface columns CSV exists and table created on ATP).
- `config.json` must contain: `mapping_sheet_path`, `table_name`.
- The mapping sheet CSV must have at least a `Field` header. Optional headers: `Mandatory`, `Validations`, `Transformations`.
- Python 3 available on PATH.

## Utility script

**scripts/generate_validation_package.py** -- reads the mapping CSV, generates mandatory checks deterministically, parses common validation rule patterns into PL/SQL, and renders the output via SQL templates.

Run from the **workspace root**:

```bash
python .cursor/skills/step3-generate-validation-package/scripts/generate_validation_package.py
```

The script will:

1. Read `config.json` -> `mapping_sheet_path` and `table_name`.
2. Parse the mapping CSV into structured field rules.
3. Auto-detect the batch filter column (field name containing "BATCH").
4. Generate PL/SQL `UPDATE` blocks for:
   - **Mandatory checks**: fields with `Mandatory=Yes` -> set `status='E'` when NULL.
   - **Validation rules**: pattern-matched from free-text `Validations` column.
   - **Transformation rules**: emitted as TODO comments for LLM review.
5. Inject generated SQL into deterministic package templates.
6. Run guardrail checks (reject DROP/TRUNCATE/ALTER in non-comment lines).
7. Write output files.

## Workflow

```
Task Progress:
- [ ] Step 1: Run the generator script
- [ ] Step 2: Review generated package body for TODO comments
- [ ] Step 3: Complete any TODO items using LLM intelligence
- [ ] Step 4: Verify output
```

### Step 1 -- Run the generator script

Execute the command above from the workspace root. The script prints progress and a summary to stdout.

### Step 2 -- Review generated package body

Read back the generated `.pkb` file and search for `TODO` comments. These mark:

- **Validation rules** that the deterministic parser could not convert to SQL.
- **Transformation rules** that require domain-specific logic.

### Step 3 -- Complete TODO items (LLM-assisted)

For each TODO block in the generated `.pkb`, use LLM intelligence to:

1. Read the free-text rule from the comment.
2. Study the sample packages in `/samples` for pattern reference:
   - `PEG_CONV10_SUPPLIER_HDR_PKG.pkb` -- UPDATE-based validations with error_message appending.
   - `PEG_CONV23_PJC_TXN_XFACE_STAGE_ALL_PKG.pkb` -- CASE-based multi-column validations.
   - `PEG_CONV02_ITEM_MASTER_VALIDATIONS_PKG.pkb` -- BULK COLLECT + PL/SQL loop validations.
3. Generate the appropriate PL/SQL UPDATE or loop block.
4. Ensure every DML statement includes a `WHERE <batch_column> = p_batch_id` filter.
5. Do NOT introduce `DROP`, `TRUNCATE`, or `ALTER` statements.
6. Uncomment or replace the TODO block with the final SQL.

### Step 4 -- Verify output

Check the generated files for:

- Package spec (`.pks`): has `PROCEDURE validate_batch(p_batch_id IN VARCHAR2);`.
- Package body (`.pkb`):
  - Phase 0: Reset status.
  - Phase 1: Mandatory field checks (one UPDATE per mandatory field).
  - Phase 2: Validation checks (parsed from Validations column).
  - Phase 3: Transformation logic (from Transformations column).
  - Phase 4: Mark valid records (`status = 'V'`).
  - Phase 5: Summary logging with DBMS_OUTPUT.
  - Exception handler at the end.
- No remaining TODO comments (all rules implemented).
- No dangerous SQL outside comments.

## Supported validation rule patterns

The deterministic parser handles these common patterns automatically:

| Pattern | Example rule text | Generated SQL |
|---|---|---|
| Allowed values | "should only be 'I' or 'U'" | `NOT IN ('I','U')` |
| Conditional allowed values | "If NOT NULL, then should only be 'X' or 'Y'" | `IS NOT NULL AND NOT IN (...)` |
| Numeric check | "must be numeric" | `NOT REGEXP_LIKE(col, '^[0-9]+...')` |
| Max length | "length must not exceed 30" | `LENGTH(col) > 30` |
| No special characters | "cannot contain special characters" | `LENGTH != LENGTHB` |
| Cross-table lookup | "must exist in REF_TABLE.REF_COL" | `NOT EXISTS (SELECT 1 FROM ...)` |

Rules not matching any pattern are emitted as TODO comments.

## Expected outputs

```
output/<TABLE_NAME>_VAL_PKG.pks          -- Package specification
output/<TABLE_NAME>_VAL_PKG.pkb          -- Package body
output/<TABLE_NAME>_mapping_rules.json   -- Parsed rules for traceability
```

Sample spec header:

```sql
CREATE OR REPLACE PACKAGE "HZ_IMP_PARTIES_T_VAL_PKG" AS
    PROCEDURE validate_batch(p_batch_id IN VARCHAR2);
END HZ_IMP_PARTIES_T_VAL_PKG;
/
```

Sample body excerpt (mandatory check):

```sql
-- 1. Mandatory: PARTY_ORIG_SYSTEM
UPDATE HZ_IMP_PARTIES_T t
SET t.status = 'E',
    t.error_message = NVL(t.error_message, '') || 'PARTY_ORIG_SYSTEM is mandatory and cannot be NULL; '
WHERE t.BATCH_ID = p_batch_id
AND t.PARTY_ORIG_SYSTEM IS NULL;
```

## Error handling

| Condition | Action |
|---|---|
| `mapping_sheet_path` missing in config | Stop with error |
| Mapping CSV file not found | Stop with error |
| CSV missing `Field` header | Stop with error |
| No field rules in CSV | Stop with error |
| Template files missing | Stop with error |
| Validation rule unparseable | Emit as TODO comment; warn on stdout |
| Dangerous SQL in generated output | Print WARNING (does not block) |

## Guardrails

- Every generated `UPDATE` statement is scoped by the batch column filter.
- `DROP`, `TRUNCATE`, and `ALTER` statements in non-comment lines trigger warnings.
- The batch column is auto-detected from the mapping sheet (first field containing "BATCH").
- `BATCH_ID` itself is excluded from mandatory NULL checks (it is the WHERE filter).
