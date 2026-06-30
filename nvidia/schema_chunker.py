import pandas as pd
import uuid

def build_table_chunks(df: pd.DataFrame) -> list[dict]:
    """
    Input:
        df — dataframe with columns:
             schema_name, table_name, column_name, data_type,
             is_primary_key, is_foreign_key,
             referenced_schema, referenced_table, referenced_column,
             description, keyword

    Output:
        list of chunk dicts, one per table:
        {
            "chunk_id"  : "schema.table",
            "chunk_type": "table",
            "content"   : <formatted string to embed>
        }
    """

    chunks = []

    # group all rows by schema + table
    grouped = df.groupby(["schema_name", "table_name"])

    for (schema, table), group in grouped:

        full_name   = f"{schema}.{table}"
        description = group["description"].iloc[0] if "description" in group.columns else ""
        keywords    = group["keyword"].iloc[0] if "keyword" in group.columns else ""

        # ── columns ──────────────────────────────────────────────
        col_lines = []
        for _, row in group.iterrows():
            flags = []
            if row.get("is_primary_key") == 1:
                flags.append("PK")
            if row.get("is_foreign_key") == 1:
                ref = f"{row['referenced_schema']}.{row['referenced_table']}.{row['referenced_column']}"
                flags.append(f"FK -> {ref}")
            flag_str = f", {', '.join(flags)}" if flags else ""
            col_lines.append(f"- {row['column_name']} ({row['data_type']}{flag_str})")

        # ── assemble chunk content ────────────────────────────────
        content_lines = [f"## Table: {full_name}"]
        
        if pd.notna(description) and str(description).strip() and str(description).strip() != "nan":
            content_lines.append(f"-- Description: {str(description).strip()}")
            
        content_lines.extend(col_lines)

        content = "\n".join(content_lines)

        chunks.append({
            "chunk_id"  : str(uuid.uuid5(uuid.NAMESPACE_DNS, full_name)),
            "original_id": full_name,
            "chunk_type": "table",
            "content"   : content
        })

    return chunks


def build_business_rule_chunks(df: pd.DataFrame) -> list[dict]:
    """
    Input:
        df — dataframe with column:
             Business Rules

    Output:
        list of chunk dicts, one per rule:
        {
            "chunk_id"  : "rule_<index>",
            "chunk_type": "business_rule",
            "content"   : <rule text to embed>
        }
    """
    chunks = []

    for idx, row in df.iterrows():
        if "Business Rules" not in row:
            continue
        rule = str(row["Business Rules"]).strip()

        # skip empty rows
        if not rule or rule.lower() == "nan":
            continue

        rule_id = f"rule_{idx}"
        chunks.append({
            "chunk_id"  : str(uuid.uuid5(uuid.NAMESPACE_DNS, rule_id)),
            "original_id": rule_id,
            "chunk_type": "business_rule",
            "content"   : rule
        })

    return chunks


def build_sample_query_chunks(df: pd.DataFrame) -> list[dict]:
    """
    Input:
        df — dataframe with columns:
             intent, tables, sql, tags

    Output:
        list of chunk dicts, one per query:
        {
            "chunk_id"  : "sample_<index>",
            "chunk_type": "sample_query",
            "content"   : <intent + tags to embed>,
            "sql"       : <actual SQL stored as metadata>
        }
    """
    chunks = []

    for idx, row in df.iterrows():
        intent = str(row.get("intent", "")).strip()
        tags   = str(row.get("tags", "")).strip()
        sql    = str(row.get("sql", "")).strip()

        # skip empty rows
        if not intent or intent.lower() == "nan":
            continue

        # combine intent + tags for embedding
        content = intent
        if tags and tags.lower() != "nan":
            content += f" | {tags}"

        sample_id = f"sample_{idx}"
        chunks.append({
            "chunk_id"  : str(uuid.uuid5(uuid.NAMESPACE_DNS, sample_id)),
            "original_id": sample_id,
            "chunk_type": "sample_query",
            "content"   : content,
            "sql"       : sql
        })

    return chunks

if __name__ == "__main__":
    # Dummy data to test the chunker
    data = {
        "schema_name": ["dbo", "dbo", "dbo"],
        "table_name": ["pomain", "pomain", "tax_table"],
        "column_name": ["id", "vendor_id", "tax_expense"],
        "data_type": ["int", "int", "decimal"],
        "is_primary_key": [1, 0, 1],
        "is_foreign_key": [0, 1, 0],
        "referenced_schema": [None, "dbo", None],
        "referenced_table": [None, "vendor", None],
        "referenced_column": [None, "id", None],
        "description": ["Main purchase order records", "Main purchase order records", "Tax details"],
        "keyword": ["purchase, vendor, order", "purchase, vendor, order", "tax, expense"]
    }
    
    test_df = pd.DataFrame(data)
    test_chunks = build_table_chunks(test_df)
    
    print(f"Generated {len(test_chunks)} chunks.\n")
    for i, chunk in enumerate(test_chunks, 1):
        print(f"--- Chunk {i} ---")
        print(f"Chunk ID: {chunk['chunk_id']}")
        print("Content:")
        print(chunk['content'])
        print("-" * 40 + "\n")