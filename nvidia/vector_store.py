import os
import shutil
# pyrefly: ignore [missing-import]
from qdrant_client import QdrantClient
# pyrefly: ignore [missing-import]
from qdrant_client.models import Distance, VectorParams, PointStruct, SparseVectorParams, SparseIndexParams, SparseVector

# Import from our local files
from embedder import embed_m3
from schema_chunker import (
    build_table_chunks, 
    build_business_rule_chunks, 
    build_sample_query_chunks
)
from load_df import get_df

# Store the Qdrant DB locally in the project root directory
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "new_qdrant_db")

def initialize_vector_store() -> QdrantClient:
    """Initializes and returns the QdrantClient."""
    client = QdrantClient(path=DB_PATH)
    
    # Check if collection exists, if not create it
    if not client.collection_exists("schema_chunks"):
        client.create_collection(
            collection_name="schema_chunks",
            vectors_config={
                "dense": VectorParams(size=1024, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(
                        on_disk=False,
                    )
                )
            }
        )
    return client

def store_chunks_to_vector_db() -> None:
    # Completely remove the previous vector db folder to start fresh and avoid orphaned files
    if os.path.exists(DB_PATH):
        try:
            shutil.rmtree(DB_PATH)
            print("Removed previous vector database folder.")
        except Exception as e:
            print(f"Warning: Could not remove old qdrant_db folder: {e}")
    
    # Initialize the client (this will create a fresh qdrant_db folder)
    client = initialize_vector_store()

    print("Fetching data from sheets...")
    schema_df = get_df("Sheet6")
    rules_df = get_df("Sheet7")
    # Switched to Sheet4 to match what load_df.py uses for Sample Queries
    queries_df = get_df("Sheet8")
    
    print("Building chunks...")
    schema_chunks = build_table_chunks(schema_df)
    rule_chunks = build_business_rule_chunks(rules_df)
    query_chunks = build_sample_query_chunks(queries_df)
    
    ALL_CHUNKS = schema_chunks + rule_chunks + query_chunks
    
    if not ALL_CHUNKS:
        print("No chunks to ingest.")
        return
        
    # Prepare batch data
    texts = [chunk["content"] for chunk in ALL_CHUNKS]
    
    metadatas = []
    for chunk in ALL_CHUNKS:
        meta = {
            "chunk_type": chunk["chunk_type"], 
            "original_id": chunk.get("original_id", chunk["chunk_id"])
        }
        if "sql" in chunk:
            meta["sql"] = chunk["sql"]
        metadatas.append(meta)
    
    print(f"Generating embeddings for {len(ALL_CHUNKS)} chunks (Schema: {len(schema_chunks)}, Rules: {len(rule_chunks)}, Queries: {len(query_chunks)})...")
    
    # Create embeddings in a single efficient batch
    # using embed_m3 from embedder.py
    dense_embeddings, sparse_embeddings = embed_m3(texts)
    
    # Upsert into Qdrant
    # Qdrant requires IDs to be either integers or properly formatted UUID strings.
    points = [
        PointStruct(
            id=chunk["chunk_id"],
            vector={
                "dense": dense_embeddings[i],
                "sparse": sparse_embeddings[i]
            },
            payload={
                "text": texts[i],
                **metadatas[i]
            }
        )
        for i, chunk in enumerate(ALL_CHUNKS)
    ]
    
    client.upsert(
        collection_name="schema_chunks",
        points=points
    )
    
    print(f"Done. Successfully stored {len(ALL_CHUNKS)} chunks in the Qdrant database.")

if __name__ == "__main__":
    print("Starting vector store pipeline...")
    store_chunks_to_vector_db()
