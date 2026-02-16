"""
generate_validation_package.py
------------------------------
Parse the mapping CSV from config.json, generate Oracle PL/SQL validation
package files (.pks, .pkb) for batch validation and transformation.

The script handles:
  - Mandatory field checks (deterministic: IS NULL -> set status='E')
  - Validation rules   (pattern-based parser for common patterns;
                         unparseable rules become TODO comments for LLM review)
  - Transformation rules (included as TODO comments for LLM review)

Usage (run from workspace root):
    python .cursor/skills/step3-generate-validation-package/scripts/generate_validation_package.py

Inputs:
    config.json  ->  { "mapping_sheet_path": "...", "table_name": "..." }

Outputs:
    output/<TABLE_NAME>_VAL_PKG.pks
    output/<TABLE_NAME>_VAL_PKG.pkb
    output/<TABLE_NAME>_mapping_rules.json   (structured rules for LLM review)
"""

import csv
import json
import os
import re
import sys
from datetime import datetime

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

    required = ["mapping_sheet_path", "table_name"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"ERROR: Missing config keys: {missing}", file=sys.stderr)
        sys.exit(1)

    return config


# ---------------------------------------------------------------------------
# Mapping-sheet parser
# ---------------------------------------------------------------------------
def parse_mapping_sheet(csv_path):
    """Parse the mapping CSV into structured rules.

    Returns a list of dicts:
        { field, mandatory, validation, transformation }
    """
    if not os.path.isfile(csv_path):
        print(f"ERROR: Mapping sheet not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    rules = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        headers = set(reader.fieldnames or [])
        if "Field" not in headers:
            print(
                f"ERROR: CSV must have a 'Field' header. Found: {reader.fieldnames}",
                file=sys.stderr,
            )
            sys.exit(1)

        for row in reader:
            field = (row.get("Field") or "").strip()
            if not field:
                continue

            rules.append(
                {
                    "field": field,
                    "mandatory": (row.get("Mandatory") or "").strip().upper() == "YES",
                    "validation": (row.get("Validations") or "").strip(),
                    "transformation": (row.get("Transformations") or "").strip(),
                }
            )

    if not rules:
        print("ERROR: No field rules found in mapping sheet.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(rules)} field rules from mapping sheet.")
    return rules


def detect_batch_column(rules):
    """Auto-detect the batch ID column from the field list.

    Looks for a field whose name contains 'BATCH' (case-insensitive).
    Falls back to 'BATCH_ID'.
    """
    for r in rules:
        if "BATCH" in r["field"].upper():
            return r["field"]
    return "BATCH_ID"


# ---------------------------------------------------------------------------
# Deterministic SQL generators
# ---------------------------------------------------------------------------
def generate_mandatory_sql(table_name, batch_col, rules):
    """Generate UPDATE statements for mandatory NULL checks."""
    mandatory_fields = [r for r in rules if r["mandatory"]]
    if not mandatory_fields:
        return "        -- No mandatory field checks defined.\n"

    blocks = []
    check_num = 0
    for rule in mandatory_fields:
        field = rule["field"]
        # Skip the batch column itself -- it's the WHERE filter
        if field.upper() == batch_col.upper():
            continue
        check_num += 1
        escaped_field = field.replace("'", "''")
        block = (
            f"        -- {check_num}. Mandatory: {field}\n"
            f"        UPDATE {table_name} t\n"
            f"        SET t.status = 'E',\n"
            f"            t.error_message = NVL(t.error_message, '') || '{escaped_field} is mandatory and cannot be NULL; '\n"
            f"        WHERE t.{batch_col} = p_batch_id\n"
            f"        AND t.{field} IS NULL;\n"
        )
        blocks.append(block)

    return "\n".join(blocks) if blocks else "        -- No mandatory field checks defined.\n"


# ---------------------------------------------------------------------------
# Validation-rule pattern parser
# ---------------------------------------------------------------------------
def _escape_plsql(text):
    """Escape single quotes for use inside a PL/SQL string literal."""
    return text.replace("'", "''")


def parse_validation_rule(field, rule_text, table_name, batch_col):
    """Try to convert a free-text validation rule into a PL/SQL UPDATE block.

    Returns (sql_block: str, fully_parsed: bool).
    """
    if not rule_text:
        return "", True

    sql_parts = []
    fully_parsed = True

    # ------------------------------------------------------------------
    # Pattern 1: "should only be 'X' or 'Y'" / "must be 'A', 'B' or 'C'"
    # ------------------------------------------------------------------
    only_match = re.search(
        r"(?:should|must)\s+only\s+be\s+((?:'[^']+'\s*(?:,\s*|or\s+))*'[^']+')",
        rule_text,
        re.IGNORECASE,
    )
    if only_match:
        values = re.findall(r"'([^']+)'", only_match.group(1))
        if values:
            in_list_msg = ", ".join(f"''{v}''" for v in values)
            in_list_sql = ", ".join(f"'{v}'" for v in values)
            is_conditional = bool(
                re.search(r"if.*not\s*null", rule_text, re.IGNORECASE)
            )
            null_guard = (
                f"\n        AND t.{field} IS NOT NULL" if is_conditional else ""
            )
            block = (
                f"        -- Validation: {field} - {rule_text}\n"
                f"        UPDATE {table_name} t\n"
                f"        SET t.status = 'E',\n"
                f"            t.error_message = NVL(t.error_message, '') || "
                f"'{_escape_plsql(field)} must be one of ({in_list_msg}); '\n"
                f"        WHERE t.{batch_col} = p_batch_id{null_guard}\n"
                f"        AND t.{field} NOT IN ({in_list_sql});\n"
            )
            sql_parts.append(block)
            return "\n".join(sql_parts), True

    # ------------------------------------------------------------------
    # Pattern 2: "must be numeric" / "should be a number"
    # ------------------------------------------------------------------
    if re.search(r"(must|should)\s+be\s+(numeric|a\s+number)", rule_text, re.IGNORECASE):
        block = (
            f"        -- Validation: {field} - {rule_text}\n"
            f"        UPDATE {table_name} t\n"
            f"        SET t.status = 'E',\n"
            f"            t.error_message = NVL(t.error_message, '') || "
            f"'{_escape_plsql(field)} must be numeric; '\n"
            f"        WHERE t.{batch_col} = p_batch_id\n"
            f"        AND t.{field} IS NOT NULL\n"
            f"        AND NOT REGEXP_LIKE(t.{field}, ''^[0-9]+(\\.[0-9]+)?$'');\n"
        )
        sql_parts.append(block)
        return "\n".join(sql_parts), True

    # ------------------------------------------------------------------
    # Pattern 3: "length must not exceed N" / "max length N"
    # ------------------------------------------------------------------
    len_match = re.search(
        r"(?:length|max\s+length)\s+(?:must\s+not\s+exceed|is|of)\s+(\d+)",
        rule_text,
        re.IGNORECASE,
    )
    if len_match:
        max_len = len_match.group(1)
        block = (
            f"        -- Validation: {field} - {rule_text}\n"
            f"        UPDATE {table_name} t\n"
            f"        SET t.status = 'E',\n"
            f"            t.error_message = NVL(t.error_message, '') || "
            f"'{_escape_plsql(field)} exceeds maximum length of {max_len}; '\n"
            f"        WHERE t.{batch_col} = p_batch_id\n"
            f"        AND t.{field} IS NOT NULL\n"
            f"        AND LENGTH(t.{field}) > {max_len};\n"
        )
        sql_parts.append(block)
        return "\n".join(sql_parts), True

    # ------------------------------------------------------------------
    # Pattern 4: "cannot contain special characters"
    # ------------------------------------------------------------------
    if re.search(r"(cannot|must\s+not|should\s+not)\s+contain\s+special\s+char", rule_text, re.IGNORECASE):
        block = (
            f"        -- Validation: {field} - {rule_text}\n"
            f"        UPDATE {table_name} t\n"
            f"        SET t.status = 'E',\n"
            f"            t.error_message = NVL(t.error_message, '') || "
            f"'{_escape_plsql(field)} contains special characters; '\n"
            f"        WHERE t.{batch_col} = p_batch_id\n"
            f"        AND t.{field} IS NOT NULL\n"
            f"        AND LENGTH(t.{field}) != LENGTHB(t.{field});\n"
        )
        sql_parts.append(block)
        return "\n".join(sql_parts), True

    # ------------------------------------------------------------------
    # Pattern 5: "must exist in <TABLE>.<COLUMN>" (cross-table lookup)
    # ------------------------------------------------------------------
    exists_match = re.search(
        r"(?:must|should)\s+exist\s+in\s+(\w+)\.(\w+)",
        rule_text,
        re.IGNORECASE,
    )
    if exists_match:
        ref_table = exists_match.group(1)
        ref_col = exists_match.group(2)
        block = (
            f"        -- Validation: {field} - {rule_text}\n"
            f"        UPDATE {table_name} t\n"
            f"        SET t.status = 'E',\n"
            f"            t.error_message = NVL(t.error_message, '') || "
            f"'{_escape_plsql(field)} does not exist in {ref_table}; '\n"
            f"        WHERE t.{batch_col} = p_batch_id\n"
            f"        AND t.{field} IS NOT NULL\n"
            f"        AND NOT EXISTS (\n"
            f"            SELECT 1 FROM {ref_table} ref\n"
            f"            WHERE ref.{ref_col} = t.{field}\n"
            f"        );\n"
        )
        sql_parts.append(block)
        return "\n".join(sql_parts), True

    # ------------------------------------------------------------------
    # Fallback: unparseable rule -> TODO comment for LLM review
    # ------------------------------------------------------------------
    block = (
        f"        -- TODO: Implement validation for {field}: {rule_text}\n"
        f"        -- UPDATE {table_name} t\n"
        f"        -- SET t.status = 'E',\n"
        f"        --     t.error_message = NVL(t.error_message, '') || "
        f"'{_escape_plsql(field)} validation failed; '\n"
        f"        -- WHERE t.{batch_col} = p_batch_id\n"
        f"        -- AND <condition>;\n"
    )
    sql_parts.append(block)
    return "\n".join(sql_parts), False


def generate_validation_sql(table_name, batch_col, rules):
    """Generate SQL blocks for all validation rules."""
    validation_rules = [r for r in rules if r["validation"]]
    if not validation_rules:
        return "        -- No custom validation rules defined.\n"

    blocks = []
    unparsed = 0
    for rule in validation_rules:
        sql, parsed = parse_validation_rule(
            rule["field"], rule["validation"], table_name, batch_col
        )
        if sql:
            blocks.append(sql)
        if not parsed:
            unparsed += 1

    if unparsed:
        print(
            f"  WARNING: {unparsed} validation rule(s) could not be fully parsed. "
            f"Look for TODO comments in the generated .pkb."
        )

    return "\n".join(blocks) if blocks else "        -- No custom validation rules defined.\n"


def generate_transformation_sql(table_name, batch_col, rules):
    """Generate SQL blocks for transformation rules.

    Transformations are free-form and typically require LLM review,
    so they are emitted as commented-out TODO blocks.
    """
    transformation_rules = [r for r in rules if r["transformation"]]
    if not transformation_rules:
        return "        -- No transformation rules defined.\n"

    blocks = []
    for rule in transformation_rules:
        block = (
            f"        -- TODO: Implement transformation for {rule['field']}: "
            f"{rule['transformation']}\n"
            f"        -- UPDATE {table_name} t\n"
            f"        -- SET t.{rule['field']} = <transformed_value>\n"
            f"        -- WHERE t.{batch_col} = p_batch_id;\n"
        )
        blocks.append(block)

    if blocks:
        print(
            f"  INFO: {len(blocks)} transformation rule(s) emitted as TODO. "
            f"Review and implement in the generated .pkb."
        )

    return "\n".join(blocks)


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


def render(template_text, replacements):
    """Replace all {{KEY}} placeholders in template_text."""
    result = template_text
    for key, val in replacements.items():
        result = result.replace("{{" + key + "}}", val)
    return result


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
DANGEROUS_KEYWORDS = ["DROP ", "TRUNCATE ", "ALTER "]


def validate_generated_sql(sql_text):
    """Warn if generated SQL contains potentially dangerous statements."""
    warnings = []
    for line_no, line in enumerate(sql_text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        for kw in DANGEROUS_KEYWORDS:
            if kw in stripped.upper():
                warnings.append(f"  Line {line_no}: {stripped[:100]}")
    if warnings:
        print("WARNING: Potentially dangerous statements found:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)
    return len(warnings) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    config = read_config()
    table_name = config["table_name"]
    mapping_path = config["mapping_sheet_path"]
    pkg_name = f"{table_name}_VAL_PKG"

    print(f"Table name   : {table_name}")
    print(f"Package name : {pkg_name}")
    print(f"Mapping sheet: {mapping_path}")
    print()

    # 1. Parse mapping sheet
    rules = parse_mapping_sheet(mapping_path)

    # Auto-detect batch column
    batch_col = detect_batch_column(rules)
    print(f"Batch column : {batch_col}")
    print()

    # 2. Write structured rules JSON for traceability / LLM review
    os.makedirs("output", exist_ok=True)
    rules_json_path = os.path.join("output", f"{table_name}_mapping_rules.json")
    with open(rules_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "table_name": table_name,
                "package_name": pkg_name,
                "batch_column": batch_col,
                "rules": rules,
            },
            f,
            indent=2,
        )
    print(f"Parsed rules written to {rules_json_path}")

    # 3. Generate SQL fragments
    print("\nGenerating mandatory checks...")
    mandatory_sql = generate_mandatory_sql(table_name, batch_col, rules)

    print("Generating validation checks...")
    validation_sql = generate_validation_sql(table_name, batch_col, rules)

    print("Generating transformation logic...")
    transformation_sql = generate_transformation_sql(table_name, batch_col, rules)

    # 4. Render templates
    today = datetime.now().strftime("%d-%b-%Y").upper()
    common = {
        "PKG_NAME": pkg_name,
        "TABLE_NAME": table_name,
        "DATE": today,
        "BATCH_COLUMN": batch_col,
    }

    print("\nRendering package spec...")
    spec_sql = render(read_template("package_spec.tpl.sql"), common)

    print("Rendering package body...")
    body_replacements = {
        **common,
        "MANDATORY_CHECKS": mandatory_sql,
        "VALIDATION_CHECKS": validation_sql,
        "TRANSFORMATION_LOGIC": transformation_sql,
    }
    body_sql = render(read_template("package_body.tpl.sql"), body_replacements)

    # 5. Guardrails
    validate_generated_sql(body_sql)

    # 6. Write output files
    spec_path = os.path.join("output", f"{pkg_name}.pks")
    body_path = os.path.join("output", f"{pkg_name}.pkb")

    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_sql)
    print(f"\nPackage spec written to {spec_path}")

    with open(body_path, "w", encoding="utf-8") as f:
        f.write(body_sql)
    print(f"Package body written to {body_path}")

    # 7. Summary
    mandatory_count = sum(1 for r in rules if r["mandatory"])
    validation_count = sum(1 for r in rules if r["validation"])
    transformation_count = sum(1 for r in rules if r["transformation"])
    print(f"\nSummary:")
    print(f"  Fields processed      : {len(rules)}")
    print(f"  Mandatory checks      : {mandatory_count}")
    print(f"  Validation rules      : {validation_count}")
    print(f"  Transformation rules  : {transformation_count}")
    print(f"\nDone. Review generated files for any TODO comments that need completion.")


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    main()
