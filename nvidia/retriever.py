import numpy as np
# pyrefly: ignore [missing-import]
from qdrant_client import QdrantClient
# pyrefly: ignore [missing-import]
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Prefetch, FusionQuery, Fusion, SparseVector
from embedder import embed_m3
import os
import json
import re
import nltk
from nltk.stem import WordNetLemmatizer

# Set up local NLTK data directory inside the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NLTK_DATA_DIR = os.path.join(BASE_DIR, 'nltk_data')
os.makedirs(NLTK_DATA_DIR, exist_ok=True)

if NLTK_DATA_DIR not in nltk.data.path:
    nltk.data.path.append(NLTK_DATA_DIR)

# Ensure wordnet is downloaded
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', download_dir=NLTK_DATA_DIR, quiet=True)

try:
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    nltk.download('omw-1.4', download_dir=NLTK_DATA_DIR, quiet=True)

lemmatizer = WordNetLemmatizer()

# Store the Qdrant DB locally in the project root directory
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "new_qdrant_db")
_qdrant_client = None
def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path=DB_PATH)
    return _qdrant_client

def get_table_boosts(query: str) -> dict:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    boosting_path = os.path.join(script_dir, "boosting.json")
    
    if not os.path.exists(boosting_path):
        return {}
        
    try:
        with open(boosting_path, 'r') as f:
            boosting_data = json.load(f)
    except json.JSONDecodeError:
        return {}
        
    # Clean query and lemmatize
    clean_query = re.sub(r'[^a-zA-Z\s]', '', query.lower())
    words = clean_query.split()
    lemmatized_words = [lemmatizer.lemmatize(w) for w in set(words)]
    
    matched_tables = {}
    
    # 1. Process "always pull" tables (wildcard '*')
    for key, entry in boosting_data.items():
        if key == "*":
            tables = entry.get('tables', [])
            score = entry.get('boost_score', 0)
            for t in tables:
                t_lower = t.lower().split('.')[-1]
                matched_tables[t_lower] = max(matched_tables.get(t_lower, 0), score)

    # 2. Process word-based matching
    for word in lemmatized_words:
        for key, entry in boosting_data.items():
            if key == "*":
                continue
            # Match if exact, or if the keyword is a substring of the query word (e.g. "expense" in "expensive")
            if key == word or (len(key) >= 4 and key in word):
                tables = entry.get('tables', [])
                score = entry.get('boost_score', 0)
                for t in tables:
                    # Normalize table name: lowercase and strip schema
                    t_lower = t.lower().split('.')[-1]
                    matched_tables[t_lower] = max(matched_tables.get(t_lower, 0), score)
                
    return matched_tables

def _fetch_chunks(query: str, chunk_type: str, top_k: int = 5, custom_filter: Filter = None):
    """Internal function to fetch chunks using Fast Hybrid Search (Dense + Sparse RRF)."""
    client = get_qdrant_client()
    
    if not client.collection_exists("schema_chunks"):
        print("Error: Collection 'schema_chunks' does not exist.")
        return []
        
    dense_vecs, sparse_vecs = embed_m3(query)
    
    vector_dense = dense_vecs[0]
    vector_sparse = sparse_vecs[0]
    
    must_conditions = [
        FieldCondition(
            key="chunk_type",
            match=MatchValue(value=chunk_type)
        )
    ]
    
    chunk_filter = Filter(must=must_conditions)
    if custom_filter:
        if custom_filter.must:
            chunk_filter.must.extend(custom_filter.must)
        if custom_filter.should:
            chunk_filter.should = custom_filter.should
        if custom_filter.must_not:
            chunk_filter.must_not = custom_filter.must_not
    
    if chunk_type == "table":
        fetch_k = 16
        top_k = 8
    else:
        fetch_k = top_k
    
    # 1. Fast Hybrid Retrieval (Dense + Sparse RRF)
    search_response = client.query_points(
        collection_name="schema_chunks",
        prefetch=[
            Prefetch(
                query=vector_dense,
                using="dense",
                filter=chunk_filter,
                limit=fetch_k
            ),
            Prefetch(
                query=vector_sparse,
                using="sparse",
                filter=chunk_filter,
                limit=fetch_k
            )
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=fetch_k,
        with_payload=True,
        with_vectors=False
    )
    
    points = search_response.points
    if not points:
        return []
        
    if chunk_type == "table":
        print(f"\n{'='*60}")
        print(f"TRACING PIPELINE FOR QUERY: '{query}'")
        print(f"{'='*60}")
        
        merged_names = [p.payload.get('text', '').split('\n')[0].replace('table_name :', '').strip() for p in points]
        print(f"1. HYBRID FUSION [Dense+Sparse RRF] (Top {fetch_k}):")
        print(f"   -> {merged_names}")
        
        # 2. Rerank the fetched points using Nemotron via OpenRouter
        from embedder import get_nemotron_reranker_scores
        
        # The API expects a list of text strings for 'documents'
        documents = [p.payload.get("text", "") for p in points]
        scores = get_nemotron_reranker_scores(query, documents)
        
        # --- KEYWORD BOOSTING ---
        table_boosts = get_table_boosts(query)
        unhandled_boosts = set(table_boosts.keys())
        scored_points_dict = {}
        
        for p, score in zip(points, scores):
            text = p.payload.get("text", "")
            table_name = None
            for line in text.split('\n'):
                if line.strip().startswith("table_name :"):
                    table_name = line.split("table_name :")[1].strip()
                    break
            
            if table_name:
                t_lower = table_name.lower().split('.')[-1]
                if t_lower in table_boosts:
                    score += table_boosts[t_lower]
                    unhandled_boosts.discard(t_lower)
                
            scored_points_dict[str(p.id)] = (p, score)
            
        # Fetch missing tables if any remain (The Union Approach)
        if unhandled_boosts:
            res = client.scroll(
                collection_name="schema_chunks",
                scroll_filter=Filter(must=[FieldCondition(key="chunk_type", match=MatchValue(value="table"))]),
                limit=1000
            )
            all_tables = res[0]
            for p in all_tables:
                text = p.payload.get("text", "")
                table_name = None
                for line in text.split('\n'):
                    if line.strip().startswith("table_name :"):
                        table_name = line.split("table_name :")[1].strip()
                        break
                
                if table_name:
                    t_lower = table_name.lower().split('.')[-1]
                    if t_lower in unhandled_boosts:
                        # Add this chunk with the boost score
                        scored_points_dict[str(p.id)] = (p, table_boosts[t_lower])
                        
        scored_points = list(scored_points_dict.values())
        # ------------------------
        
        scored_points.sort(key=lambda x: x[1], reverse=True)
        
        final_points = [p for p, score in scored_points[:top_k]]
        
        final_names_with_scores = []
        final_tables_for_log = []
        for p, score in scored_points[:top_k]:
            text = p.payload.get("text", "")
            t_name = "Unknown"
            for line in text.split('\n'):
                if line.strip().startswith("table_name :"):
                    t_name = line.split("table_name :")[1].strip()
                    break
            final_names_with_scores.append(f"{t_name} (Score: {score:.3f})")
            final_tables_for_log.append(t_name)
            
        print(f"2. FINAL RERANKED OUTPUT (Top {top_k}):")
        print(f"   -> {final_names_with_scores}")
        print(f"{'='*60}\n")
        

            
        return final_points, merged_names, final_tables_for_log
    else:
        return [p for p in points[:top_k]]

def fetch_tables(query: str, top_k: int = 5):
    """Fetches top k tables based on similarity, returning points, initial names, and final names."""
    results, initial_names, final_names = _fetch_chunks(query, chunk_type="table", top_k=top_k)
    for res in results:
        if hasattr(res, 'payload') and 'text' in res.payload:
            # Reassign text to clean llm_text for downstream tasks
            if 'llm_text' in res.payload:
                res.payload['text'] = res.payload['llm_text']
            
    return results, initial_names, final_names

def fetch_business_rules(query: str, relevant_tables: list = None, top_k_general: int = 5):
    """Fetches business rules based on similarity. Pulls ALL rules for table-specific, and top-k for general."""
    all_rules = []
    
    # 1. Fetch ALL Table-Specific Rules (Bypass Top-K)
    if relevant_tables:
        client = get_qdrant_client() # added for giving all rules
        table_filter = Filter(
            must=[
                FieldCondition(key="chunk_type", match=MatchValue(value="business_rule")),
                FieldCondition(key="category", match=MatchAny(any=relevant_tables))
            ]
        )
        # Scroll pulls everything that matches the filter without vector math
        res = client.scroll(
            collection_name="schema_chunks",
            scroll_filter=table_filter,
            limit=1000  # High enough to get all rules
        )
        specific_rules = res[0]
        all_rules.extend(specific_rules)
        
    # 2. Fetch Top-K General Rules (Still uses semantic search)
    general_filter = Filter(
        must=[
            FieldCondition(
                key="category",
                match=MatchValue(value="general")
            )
        ]
    )
    general_rules = _fetch_chunks(query, chunk_type="business_rule", top_k=top_k_general, custom_filter=general_filter)
    all_rules.extend(general_rules)
    
    return all_rules

def fetch_sample_queries(query: str, top_k: int = 5):
    """Fetches top k sample queries based on similarity."""
    return _fetch_chunks(query, chunk_type="sample_query", top_k=top_k)


def print_results(title: str, results: list):
    print(f"\n{'='*10} {title} ({len(results)} results) {'='*10}")
    for i, res in enumerate(results, 1):
        payload = res.payload
        print(f"\nResult {i}:")
        print(f"Original ID: {payload.get('original_id', 'N/A')}")
        if 'sql' in payload:
            print(f"SQL: {payload['sql']}")
        print(f"Content:\n{payload.get('text', 'N/A')}")
        print("-" * 40)

if __name__ == "__main__":
    print("Type 'exit' or 'quit' to stop.\n")
    
    while True:
        try:
            query = input("Enter your statement (or 'exit' to quit): ").strip()
            if query.lower() in ['exit', 'quit']:
                print("Exiting...")
                break
            if not query:
                continue
                
            print(f"\nProcessing query: '{query}'...")
            
            tables, initial, final_names = fetch_tables(query, top_k=8)
            
            print("\n--- EXACT TABLE CHUNKS SENT TO LLM ---")
            for t in tables:
                print(t.payload.get('text', ''))
                print("---------------------------------------")
                
            print("\n--- FETCHING BUSINESS RULES ---")
            print(f"Filtering rules for tables: {final_names} + 'general'")
            
            rules = fetch_business_rules(query, relevant_tables=final_names, top_k_general=3)
            
            print("\n--- EXACT BUSINESS RULES SENT TO LLM ---")
            for r in rules:
                category = r.payload.get('category', 'unknown')
                print(f"[Category: {category}]")
                print(r.payload.get('text', ''))
                print("---------------------------------------")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            import traceback
            from logger import log_error_sync
            log_error_sync("retriever", "UNEXPECTED_ERROR", e, "Error in manual retriever prompt")
            traceback.print_exc()
            print(f"An error occurred: {e}")