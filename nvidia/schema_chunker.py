import pandas as pd
import uuid

def build_table_chunks(df: pd.DataFrame, rules_df: pd.DataFrame = None) -> list[dict]:
    """
    Input:
        df — dataframe with columns:
             schema_name, table_name, column_name, data_type,
             is_primary_key, is_foreign_key,
             referenced_schema, referenced_table, referenced_column,
             Business Entity, purpose, supports, does not supports
        rules_df — optional Business Rules dataframe to extract table-specific rules.

    Output:
        list of chunk dicts, one per table:
        {
            "chunk_id"  : "schema.table",
            "chunk_type": "table",
            "embedding_text": <rich text for Qdrant embedding>,
            "llm_text": <clean schema string for LLM>
        }
    """

    chunks = []

    # group all rows by schema + table
    grouped = df.groupby(["schema_name", "table_name"])

    for (schema, table), group in grouped:

        full_name = f"{schema}.{table}"
        
        first_row = group.iloc[0]
        business_entity = first_row.get("Business Entity", "")
        purpose = first_row.get("purpose", "")
        supports = first_row.get("supports", "")
        does_not_support = first_row.get("does not supports", "")

        # ── columns and relationships ──────────────────────────────────────────────
        embed_col_lines = []
        llm_col_lines = []
        rel_lines = []
        for _, row in group.iterrows():
            flags = []
            if row.get("is_primary_key") == 1:
                flags.append("PK")
            flag_str = f", {', '.join(flags)}" if flags else ""
            
            # Embedding text (no data type)
            embed_col_lines.append(f"- {row['column_name']} ({flag_str.strip(', ')})")
            
            # LLM text (with data type)
            llm_col_lines.append(f"- {row['column_name']} ({row['data_type']}{flag_str})")
            
            if row.get("is_foreign_key") == 1:
                ref = f"{row['referenced_schema']}.{row['referenced_table']}.{row['referenced_column']}"
                rel_lines.append(f"- {row['column_name']} -> {ref}")

        # ── assemble llm text ────────────────────────────────
        llm_content_lines = [
            f"table_name : {table}",
            f"schema_name : {schema}",
        ]
        
        if pd.notna(purpose) and str(purpose).strip() and str(purpose).strip() != "nan":
            llm_content_lines.append(f"purpose : {str(purpose).strip()}")
            
        llm_content_lines.append("columns :")
        llm_content_lines.extend(llm_col_lines)
        
        if rel_lines:
            llm_content_lines.append("relationships :")
            llm_content_lines.extend(rel_lines)
            
        llm_content = "\n".join(llm_content_lines)

        # ── assemble embedding text ────────────────────────────────
        embed_content_lines = [
            f"table_name : {table}",
            f"schema_name : {schema}",
        ]
        
        if pd.notna(business_entity) and str(business_entity).strip() and str(business_entity).strip() != "nan":
            embed_content_lines.append(f"Business Entity : {str(business_entity).strip()}")
        if pd.notna(purpose) and str(purpose).strip() and str(purpose).strip() != "nan":
            embed_content_lines.append(f"purpose : {str(purpose).strip()}")
        if pd.notna(supports) and str(supports).strip() and str(supports).strip() != "nan":
            embed_content_lines.append(f"supports : {str(supports).strip()}")
        if pd.notna(does_not_support) and str(does_not_support).strip() and str(does_not_support).strip() != "nan":
            embed_content_lines.append(f"does not supports : {str(does_not_support).strip()}")
            
        embed_content_lines.append("columns :")
        embed_content_lines.extend(embed_col_lines)
        
        if rel_lines:
            embed_content_lines.append("relationships :")
            embed_content_lines.extend(rel_lines)

        # Append specific rules from rules_df
        if rules_df is not None:
            # Filter where category == bare table name (case insensitive)
            table_rules = rules_df[
                (rules_df['category'].notna()) & 
                (rules_df['category'].astype(str).str.strip().str.lower() == str(table).strip().lower())
            ]
            if not table_rules.empty:
                embed_content_lines.append("Business Rules :")
                for _, rule_row in table_rules.iterrows():
                    rule_text = str(rule_row.get("Business Rules", "")).strip()
                    if rule_text and rule_text.lower() != "nan":
                        embed_content_lines.append(f"- {rule_text}")

        embed_content = "\n".join(embed_content_lines)

        chunks.append({
            "chunk_id"  : str(uuid.uuid5(uuid.NAMESPACE_DNS, full_name)),
            "original_id": full_name,
            "chunk_type": "table",
            "content": embed_content,
            "embedding_text": embed_content,
            "llm_text": llm_content
        })

    return chunks


def build_business_rule_chunks(df: pd.DataFrame) -> list[dict]:
    """
    Input:
        df — dataframe with column:
             Business Rules, category

    Output:
        list of chunk dicts, one per rule:
        {
            "chunk_id"  : "rule_<index>",
            "chunk_type": "business_rule",
            "content"   : <rule text to embed>,
            "category"  : <category for filtering>
        }
    """
    chunks = []

    for idx, row in df.iterrows():
        if "Business Rules" not in row:
            continue
        rule = str(row["Business Rules"]).strip()
        category = str(row.get("category", "")).strip()

        # skip empty rows
        if not rule or rule.lower() == "nan":
            continue

        rule_id = f"rule_{idx}"
        chunks.append({
            "chunk_id"  : str(uuid.uuid5(uuid.NAMESPACE_DNS, rule_id)),
            "original_id": rule_id,
            "chunk_type": "business_rule",
            "content"   : rule,
            "category"  : category
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
        "keyword": ["purchase, vendor, order", "purchase, vendor, order", "tax, expense"],
        "Business Entity": ["Purchase Order", "Purchase Order", "Tax"],
        "purpose": ["Store main PO info", "Store main PO info", "Store tax info"],
        "supports": ["Reporting, Invoicing", "Reporting, Invoicing", "Accounting"],
        "does not supports": ["Analytics", "Analytics", "Payroll"]
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