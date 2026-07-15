import os
import re
import json
import io
import pandas as pd
from openai import AsyncOpenAI
from dotenv import load_dotenv
from logger import log_error_sync

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
_api_key = os.getenv("GEMINI_API_KEY") 
client = AsyncOpenAI(
  base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
  api_key=_api_key,
  timeout=120.0
)

async def generate_visual_summary(df: pd.DataFrame, user_query: str, message_id: int = None):
    """
    Generates pandas code for aggregation and a Vega-Lite spec,
    executes the pandas code, and summarizes the aggregated data.
    """
    if len(df) == 0 or (len(df) == 1 and len(df.columns) <= 2) or (len(df.columns) == 1 and len(df)>1):
        return {"status": "success", "vega_spec": None, "summary": ""}

    buffer = io.StringIO()
    df.info(buf=buffer)
    info_str = buffer.getvalue()
    # Give the AI statistical context so it can make smart scale/chart decisions
    describe_str = df.describe(include='all').to_string()
    prompt_path = os.path.join(os.path.dirname(__file__), "code_prompt_v2.txt")
    with open(prompt_path, "r") as f:
        code_system_prompt = f.read()

    code_user_prompt = (
        f"DataFrame info:\n{info_str}\n\n"
        f"DataFrame describe:\n{describe_str}\n\n"
        f"User Query: {user_query}\n\n"
        "Generate the required JSON output."
    )

    try:
        # Step 1: Generate Code and Vega Spec
        code_response = await client.chat.completions.create(
            model="gemini-3.1-flash-lite",
            messages=[
                {"role": "system", "content": code_system_prompt},
                {"role": "user", "content": code_user_prompt}
            ],
            max_tokens=2500,
            temperature=0
        )
        
        full_content = code_response.choices[0].message.content
        code_usage = code_response.usage.total_tokens if code_response.usage else 0
        print(f"\n[ANALYTICS V2] Raw Response Generated (Tokens: {code_usage}):\n{full_content}\n")
        
        # Extract the JSON block inside <output> tags
        json_match = re.search(r"<output>(.*?)</output>", full_content, re.DOTALL | re.IGNORECASE)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Fallback if tags are missing
            json_str = full_content.replace('```json', '').replace('```', '').strip()
            
        try:
            parsed_json = json.loads(json_str)
            pandas_code = parsed_json.get("pandas_code", "")
            vega_spec = parsed_json.get("vega_spec", {})
        except json.JSONDecodeError as e:
            log_error_sync("analyzer_v2", "JSON_DECODE_ERROR", e, "Failed to parse AI output into JSON", details={"raw_string": json_str})
            print(f"\n[ANALYTICS V2] JSON Decode Error: {e}\nRaw String: {json_str}")
            return {"status": "error", "type": "json_error", "content": "Failed to parse AI output into JSON."}

        # Step 2: Execute pandas code
        local_scope = {'df': df, 'pd': pd}
        exec_error = None
        try:
            # Empty globals as requested, though it's not fully safe
            exec(pandas_code, {}, local_scope)
            chart_df = local_scope.get('chart_df', None)
            
            if chart_df is None:
                raise ValueError("Variable 'chart_df' was not populated by the generated code.")
            
            # SAFEGUARD: Check for empty dataframe
            if chart_df.empty:
                return {
                    "status": "error",
                    "type": "exec_error",
                    "content": "No visual available: The applied filters resulted in an empty dataset."
                }
            
            # SAFEGUARD: Cap rows to prevent browser freeze
            if len(chart_df) > 100:
                chart_df = chart_df.head(100)
                
            # SAFEGUARD: Handle Date/Period objects for JSON serialization
            for col in chart_df.columns:
                if pd.api.types.is_datetime64_any_dtype(chart_df[col]) or pd.api.types.is_period_dtype(chart_df[col]):
                    chart_df[col] = chart_df[col].astype(str)
            
            if isinstance(chart_df.index, (pd.DatetimeIndex, pd.PeriodIndex)):
                chart_df.index = chart_df.index.astype(str)
            
            # Convert chart_df to list of dictionaries safely handling NaNs and Timestamps
            chart_data = json.loads(chart_df.to_json(orient="records", date_format="iso"))
            
        except Exception as e:
            log_error_sync("analyzer_v2", "PANDAS_EXEC_ERROR", e, "Pandas execution failed", details={"code": pandas_code})
            exec_error = str(e)
            chart_data = None

        if exec_error:
            print(f"\n[ANALYTICS V2] Exec failed, Error: {exec_error}\n")
            return {
                "status": "error",
                "type": "exec_error",
                "content": exec_error
            }

        # Step 3: Summarize the aggregated data
        data_str_output = str(chart_data)
        if len(data_str_output) > 3000:
            data_str_output = data_str_output[:3000] + "\n... [DATA TRUNCATED DUE TO EXCESSIVE LENGTH]"
        
        summary_system_prompt = (
            "You are a procurement data analyst. Use the provided aggregated chart data to draw useful insights. "
            "Give the summary in 3 to 4 short and concise bullet points. No need for any greeting. "
            "Highlight the most vital points concisely and clearly. Don't sound technical."
        )
        
        summary_user_prompt = (
            f"Aggregated Chart Data:\n{data_str_output}\n\n"
            "Provide the short and concise analytical summary."
        )
        
        summary_response = await client.chat.completions.create(
            model="gemini-3.1-flash-lite",
            messages=[
                {"role": "system", "content": summary_system_prompt},
                {"role": "user", "content": summary_user_prompt}
            ],
            temperature=0.2,
            max_tokens= 1000
        )
        
        summary_text = summary_response.choices[0].message.content
        summary_usage = summary_response.usage.total_tokens if summary_response.usage else 0
        total_usage = code_usage + summary_usage
        
        code_in = code_response.usage.prompt_tokens if code_response.usage else 0
        code_out = code_response.usage.completion_tokens if code_response.usage else 0
        sum_in = summary_response.usage.prompt_tokens if summary_response.usage else 0
        sum_out = summary_response.usage.completion_tokens if summary_response.usage else 0
        
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from expense import calculate_cost
        cost_info = calculate_cost(code_in + sum_in, code_out + sum_out)
        
        print(f"\n[ANALYTICS V2] Summary Generated (Tokens: {summary_usage} | Total: {total_usage}):\n{summary_text}\n")
        
        return {
            "status": "success",
            "type": "done",
            "code": pandas_code,
            "summary": summary_text,
            "data": chart_data,
            "vega_spec": vega_spec,
            "tokenUsage": total_usage,
            "cost": cost_info
        }
        
    except Exception as e:
        log_error_sync("analyzer_v2", "UNEXPECTED_ERROR", e, "Unexpected error in run_visual_analysis_v2", message_id=message_id)
        return {
            "status": "error",
            "type": "error",
            "content": str(e)
        }
