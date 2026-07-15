import os
import io
from logger import log_error_sync
import re
import json
import pandas as pd
from openai import AsyncOpenAI
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
_api_key = os.getenv("GEMINI_API_KEY") # reusing the same key from sql_gen.py
client = AsyncOpenAI(
  base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
  api_key=_api_key,
  timeout=120.0
)



async def generate_analytical_summary(df: pd.DataFrame, user_query: str, message_id: int = None):
    """
    Generates pandas code, executes it, and summarizes the output.
    Returns a dictionary with the results.
    """
    dtypes_str = str(df.dtypes)
    prompt1path = os.path.join(os.path.dirname(__file__), "code_prompt.txt")
    with open(prompt1path, "r") as f:
        code_system_prompt = f.read()
    # code_system_prompt = (
    #     "You are a senior data analyst examining procurement data. Your goal is to write advanced pandas code for DataFrame `df` to extract profound, compressed insights. "
    #     "If the user asks a specific question, fulfill that requirement as the very first analytical point. "
    #     "When generating general analytics, limit yourself to a maximum of 5 highly synthesized points, utilizing complex groupby and aggregate functions rather than trivial facts. "
    #     "If your analysis involves ranking or top-k selection, never extract more than 3 items per category. "
    #     "CRITICAL: Never dump raw rows, full columns, or large lists into the dictionary. Only store highly compressed, aggregated metrics and top 2 if required. "
    #     "Ensure the final output is saved as a dictionary in a variable named `result_str`. "
    #     "Do not use print() or read CSVs. Output only the pure ```python block without surrounding text."
    #     "dataframe is preloaded with name 'df'"
    #     "STRICT RULE : When writing the code, ensure the entire script is completed in under 40 lines and strictly contains zero comments. "
    # )

    code_user_prompt = (
        f"DataFrame dtypes:\n{dtypes_str}\n\n"
        "Generate the pandas code"
    )
    

    try:
        code_response = await client.chat.completions.create(
            model="gemini-3.1-flash-lite",
            messages=[
                {"role": "system", "content": code_system_prompt},
                {"role": "user", "content": code_user_prompt}
            ],
            max_tokens=2000,
            temperature=0
        )
        
        full_content = code_response.choices[0].message.content
        code_usage = code_response.usage.total_tokens if code_response.usage else 0
        print(f"\n[ANALYTICS] Pandas Code Generated (Tokens: {code_usage}):\n{full_content}\n")
                
        sql_match = re.search(r"```(?:python)?\s*(.*?)\s*```", full_content, re.DOTALL | re.IGNORECASE)
        if sql_match:
            pandas_code = sql_match.group(1).strip()
        else:
            pandas_code = full_content.replace('```', '').strip()
            if pandas_code.lower().startswith('python'):
                pandas_code = pandas_code[6:].strip()
        
        local_scope = {'df': df, 'pd': pd}
        exec_error = None
        try:
            exec(pandas_code, {}, local_scope)
            result_val = local_scope.get('result', "No result variable 'result' was populated by the generated code.")
        except Exception as e:
            log_error_sync("analyzer", "PANDAS_EXEC_ERROR", e, "Pandas execution failed in analyzer", details={"code": pandas_code})
            exec_error = str(e)
            result_val = f"Execution Error: {exec_error}"

        if exec_error:
            # Skip summary API call — exec failed, nothing useful to summarize
            print(f"\n[ANALYTICS] Exec failed, skipping summary. Error: {exec_error}\n")
            return {
                "status": "error",
                "type": "exec_error",
                "content": exec_error
            }

        result_str_output = str(result_val)
        if len(result_str_output) > 2000:
            result_str_output = result_str_output[:2000] + "\n... [DATA TRUNCATED DUE TO EXCESSIVE LENGTH]"
        
        summary_system_prompt = (
            "You are a procurement data analyst. use the raw data and draw useful insights and predictions "
            "give only summary in 4 to 5 short and concise points. No need for any greeting. "
            "Highlight the most vital points concisely and clearly. Don't sound technical at any point."
        )
        
        summary_user_prompt = (
            f"Analysis Output:\n{result_str_output}\n\n"
            "Provide the short and concise predictive and analytical summary. Do not include anything else."
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
        
        print(f"\n[ANALYTICS] Summary Generated (Tokens: {summary_usage} | Total: {total_usage}):\n{summary_text}\n")
        
        return {
            "status": "success",
            "type": "done",
            "code": full_content,
            "summary": summary_text,
            "tokenUsage": total_usage,
            "cost": cost_info
        }
        
    except Exception as e:
        log_error_sync("analyzer", "UNEXPECTED_ERROR", e, "Unexpected error in run_analysis", message_id=message_id)
        return {
            "status": "error",
            "type": "error",
            "content": str(e)
        }
