import asyncio
import pandas as pd
from analytics.analyzer_v2 import generate_visual_summary
import json

async def main():
    print("Creating dummy dataframe...")
    data = [
        {"Category": "Electronics", "Amount": 1200, "Date": "2023-01-01"},
        {"Category": "Electronics", "Amount": 800, "Date": "2023-01-02"},
        {"Category": "Furniture", "Amount": 500, "Date": "2023-01-01"},
        {"Category": "Furniture", "Amount": 1500, "Date": "2023-01-03"},
        {"Category": "Clothing", "Amount": 300, "Date": "2023-01-02"},
    ]
    df = pd.DataFrame(data)
    
    query = "Show me the total amount spent per category."
    print(f"User Query: {query}")
    print("-" * 50)
    
    result = await generate_visual_summary(df, query)
    
    print("\n" + "=" * 50)
    print("FINAL RESULT FROM V2 ANALYZER:")
    print("=" * 50)
    
    if result["status"] == "success":
        print("\n--- SUMMARY ---")
        print(result["summary"])
        print("\n--- PANDAS CODE ---")
        print(result["code"])
        print("\n--- AGGREGATED CHART DATA (JSON) ---")
        print(json.dumps(result["data"], indent=2))
        print("\n--- VEGA-LITE SPEC ---")
        print(json.dumps(result["vega_spec"], indent=2))
    else:
        print("\nERROR:")
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
