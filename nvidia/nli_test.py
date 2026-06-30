from transformers import pipeline
classifier = pipeline(
    "zero-shot-classification",
    model="cross-encoder/nli-deberta-v3-small"
)

question = "what are the products in the pipeline?"
candidate_labels = ["Products", "Users", "Orders"]
result = classifier(question, candidate_labels)
print(result)
