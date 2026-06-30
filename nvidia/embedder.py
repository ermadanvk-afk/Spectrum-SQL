import numpy as np
import torch
from FlagEmbedding import BGEM3FlagModel
from qdrant_client.models import SparseVector
import os
import requests
import json
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

_M3_MODEL = None

def get_m3_model(model_name="BAAI/bge-m3"):
    """Loads the BGEM3FlagModel lazily into GPU memory if available."""
    global _M3_MODEL
    if _M3_MODEL is not None:
        return _M3_MODEL
    print(f"Loading heavy hybrid model: {model_name}...")
    # Automatically use GPU (use_fp16=True speeds up inference on modern GPUs)
    model = BGEM3FlagModel(model_name, use_fp16=True)
    print("Warming up BGE-M3 model...")
    model.encode(["warmup prompt"])
    _M3_MODEL = model
    return _M3_MODEL

def embed_m3(texts):
    """
    Creates BOTH Dense (1024-dim) and Sparse embeddings simultaneously.
    Returns:
        dense_vectors (list of lists)
        sparse_vectors (list of qdrant SparseVector objects)
    """
    model = get_m3_model()
    
    if isinstance(texts, str):
        texts = [texts]
        
    # Get dense and sparse simultaneously (ColBERT vectors disabled to save memory)
    embeddings = model.encode(texts, return_dense=True, return_sparse=True, return_colbert_vecs=False)
    
    dense_vecs = embeddings['dense_vecs'].tolist()
    
    # Parse lexical weights into Qdrant SparseVectors
    sparse_vecs = []
    for weight_dict in embeddings['lexical_weights']:
        # Token IDs are returned as strings (e.g. '104': 0.8), convert to int for Qdrant
        indices = []
        values = []
        for token_str, weight in weight_dict.items():
            indices.append(int(token_str))
            values.append(float(weight))
        sparse_vecs.append(SparseVector(indices=indices, values=values))
        
    return dense_vecs, sparse_vecs

# ==========================================
# OLD FAST-EMBED LOGIC (COMMENTED OUT)
# ==========================================
# from fastembed import TextEmbedding, SparseTextEmbedding
# from sentence_transformers import CrossEncoder

# _DENSE_MODEL = None
# _SPARSE_MODEL = None

# def get_model(model_name="nomic-ai/nomic-embed-text-v1.5"):
#     global _DENSE_MODEL
#     if _DENSE_MODEL is None:
#         _DENSE_MODEL = TextEmbedding(model_name=model_name, threads=2)
#     return _DENSE_MODEL

# def get_sparse_model(model_name="Qdrant/bm25"):
#     global _SPARSE_MODEL
#     if _SPARSE_MODEL is None:
#         _SPARSE_MODEL = SparseTextEmbedding(model_name=model_name, threads=2)
#     return _SPARSE_MODEL

def get_nemotron_reranker_scores(query, documents):
    """
    Calls OpenRouter's rerank API using the NVIDIA Llama Nemotron model.
    """
    # Using the key found in test.py
    API_KEY = os.getenv("OPENROUTER_API_KEY")
    URL = "https://openrouter.ai/api/v1/rerank"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
        "query": query,
        "documents": documents,
        "top_n": len(documents)
    }

    try:
        response = requests.post(URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        
        # OpenRouter returns results as a list of dicts: {"index": 2, "relevance_score": 0.9}
        # We map the scores back to the original index order to match the local model behavior
        scores = [0.0] * len(documents)
        if 'results' in result:
            for item in result['results']:
                scores[item['index']] = item.get('relevance_score', 0.0)
        return scores
    except Exception as e:
        print(f"Error calling Nemotron reranker API: {e}")
        # Fallback to zeros if API fails
        return [0.0] * len(documents)

# def embed_texts(texts, task_type="search_document"):
#     model = get_model()
#     if isinstance(texts, str): texts = [texts]
#     prefixed_texts = [f"{task_type}: {text}" for text in texts]
#     return np.array(list(model.embed(prefixed_texts, batch_size=8)))

# def embed_texts_sparse(texts):
#     model = get_sparse_model()
#     if isinstance(texts, str): texts = [texts]
#     return list(model.embed(texts, batch_size=8))

if __name__ == "__main__":
    print("Testing embedder functions...")
    
    test_data = [
        "What is the capital of France?",
        "Paris is the capital and most populous city of France."
    ]
    
    print("\nGenerating embeddings...")
    dense, sparse = embed_m3(test_data)
    
    print(f"\nNumber of inputs: {len(test_data)}")
    print(f"Dense shape: \nExpected: ({len(test_data)}, 1024)")
    print(f"Sample dense embedding (first 5 values): \n{dense[0][:5]}")
    
    print("\nGenerating sparse embeddings...")
    print(f"\nSparse embeddings length: {len(sparse)}")
    print(f"Sample sparse indices (first text): \n{sparse[0].indices[:5]}")
    
    print("\nEmbedding creation successful!")
