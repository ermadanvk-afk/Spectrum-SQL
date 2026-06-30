import pandas as pd

def get_df(sheet_name: str = "Sheet2") -> pd.DataFrame:
    SHEET_ID = "1kGv0IDY3S5X1sW9kcGvsZJ2fuZukn5hkr6MsHCyK3lM"
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    try:
        df = pd.read_excel(url, sheet_name=sheet_name)
        df = df.where(pd.notnull(df), None)
        return df
    except Exception as e:
        raise RuntimeError(f"Error fetching data from {sheet_name}: {e}")

if __name__ == "__main__":
    print("Fetching Schema (Sheet2)...")
    schema_df = get_df("Sheet2")
    print(schema_df.head(), "\n")
    
    print("Fetching Business Rules (Sheet1)...")
    rules_df = get_df("Sheet1")
    print(rules_df.head(), "\n")
    
    print("Fetching Sample Queries (Sheet3)...")
    queries_df = get_df("Sheet3")
    print(queries_df.head(), "\n")