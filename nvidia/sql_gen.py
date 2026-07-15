from openai import AsyncOpenAI
import os
import re
import asyncio
from dotenv import load_dotenv
from retriever import fetch_tables, fetch_business_rules, fetch_sample_queries
from logger import log_error_sync, update_log_sync

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
_api_key = os.getenv("GEMINI_API_KEY")

client = AsyncOpenAI(
  base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
  api_key=_api_key,
  timeout=120.0  # Added timeout to prevent infinite hanging
)

class OpenAIChatWrapper:
    def __init__(self, client, messages):
        self.client = client
        self.messages = messages

    async def send_message(self, prompt):
        self.messages.append({"role": "user", "content": prompt})
        
        print("\nRetrying payload(Validation fix)...")
        
        response = await self.client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=self.messages,
            max_tokens=4000,
            # extra_body={"reasoning": {"enabled": True}},
            temperature=0.0
        )
        
        print("Received retry response!")
        
        response_msg = response.choices[0].message
        
        # Keep reasoning_details for conversational context
        self.messages.append({
            "role": "assistant",
            "content": response_msg.content,
            "reasoning_details": getattr(response_msg, "reasoning_details", None)
        })
        
        # Mocking the Gemini response object structure expected by validator.py
        class MockUsage:
            def __init__(self, in_t, out_t):
                self.prompt_token_count = in_t
                self.candidates_token_count = out_t
                
        class MockResponse:
            def __init__(self, text, in_t, out_t):
                self.text = text
                self.usage_metadata = MockUsage(in_t, out_t)
                
        usage = response.usage
        in_t = usage.prompt_tokens if usage else 0
        out_t = usage.completion_tokens if usage else 0
        
        return MockResponse(response_msg.content, in_t, out_t)

async def generate_sql(user_query: str, return_response: bool = False, history: list = None, message_id: int = None) -> str:
    """
    Takes a user query, retrieves relevant schema chunks, rules, and samples,
    and uses OpenRouter to construct the final SQL query.
    """
    if history is None:
        history = []
        
    tables, initial_names, final_names = fetch_tables(user_query, top_k=8)
    rules = fetch_business_rules(user_query, top_k=8)
    queries = fetch_sample_queries(user_query, top_k=3)
    
    # Log the RAG retrieval details using update_log_sync
    rules_list = [r.payload.get('text', '') for r in rules]
    queries_list = [{"sql": q.payload.get('sql', ''), "desc": q.payload.get('text', '')} for q in queries]
    
    update_log_sync(
        message_id=message_id,
        module="retriever",
        level="INFO",
        event_type="RAG_RETRIEVAL",
        message="Retrieved context chunks",
        tables_retrieved=initial_names,
        tables_after_reranking=final_names,
        business_rules=rules_list,
        sample_queries=queries_list
    )
    
    # 2. Format context using strict markdown headers to match instructions
    context_parts = []
            
    if rules:
        context_parts.append("# Business Rules")
        for r in rules:
            rule_val = r.payload.get('text')
            rule_text = (rule_val if rule_val is not None else '').strip()
            if not rule_text.startswith("-"):
                rule_text = f"- {rule_text}"
            context_parts.append(rule_text)
        context_parts.append("")
            
    if tables:
        context_parts.append("# Database Schema")
        for t in tables:
            context_parts.append(t.payload.get('text', ''))
        context_parts.append("")
            
    if queries:
        context_parts.append("# Golden Queries")
        for q in queries:
            sql_val = q.payload.get('sql')
            sql_text = (sql_val if sql_val is not None else '').strip()
            desc_val = q.payload.get('text')
            desc = (desc_val if desc_val is not None else '').strip()
            # Clean up the desc if it has tags appended like "Intent: ... | tags" from the older chunker
            if " | " in desc:
                desc = desc.split(" | ")[0]
            context_parts.append(f"Q: {desc}\nA: {sql_text}\n")
            
    if history:
        context_parts.append("# Conversation History (Last 3 Interactions)")
        for item in history:
            q_val = item.get("question")
            q_text = (q_val if q_val is not None else "").strip()
            s_val = item.get("sql")
            s_text = (s_val if s_val is not None else "").strip()
            context_parts.append(f"User: {q_text}\nAssistant SQL:\n```sql\n{s_text}\n```\n")
        context_parts.append("")
            
    context_str = "\n".join(context_parts)
    
    import os
    current_dir = os.path.dirname(__file__)
    system_instruction_path = os.path.join(current_dir, "systemprompt.txt")
    try:
        with open(system_instruction_path, "r", encoding="utf-8") as f:
            system_instruction = f.read()
    except FileNotFoundError:
        system_instruction = "You are an expert SQL assistant."

    # 4. Construct the final user prompt
    prompt = (
        f"{context_str}"
        f"# Target Question\n"
        f"{user_query}\n\n"
        f"SQL:\n"
    )
    
    # 5. Initialize OpenAI client and make the call
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt}
    ]
    
    print("\n[NVIDIA PIPELINE] Sending payload to Gemini Flash lite...")
    print(f"[NVIDIA PIPELINE] Waiting for response...")
    
    try:
        response = await client.chat.completions.create(
          model="gemini-2.5-flash",
          messages=messages,
          max_tokens=4500,
        #   extra_body={"reasoning": {"enabled": True}},
          temperature=0.0
        )
        print("[NVIDIA PIPELINE] Received response from Laguna!")
    except Exception as e:
        print(f"[NVIDIA PIPELINE] Error from OpenRouter: {e}")
        log_error_sync("sql_gen", "LLM_GENERATION_ERROR", e, "Error calling OpenRouter LLM", message_id=message_id)
        raise e
    
    response_msg = response.choices[0].message
    
    messages.append({
        "role": "assistant",
        "content": response_msg.content,
        "reasoning_details": getattr(response_msg, "reasoning_details", None)
    })
    
    chat = OpenAIChatWrapper(client, messages)
    
    # Extract SQL block and explanation using regex
    content = response_msg.content if response_msg.content is not None else ""
    content = content.strip()
    
    sql_match = re.search(r"```sql\n?(.*?)\n?```", content, re.DOTALL)
    
    if sql_match:
        sql_text = sql_match.group(1).strip()
    else:
        # Fallback if the AI fails to use markdown blocks
        sql_text = content.replace('```', '').strip()
        
    # Robustly extract explanation
    exp_match = re.search(r"<explanation>(.*?)</explanation>", content, re.DOTALL | re.IGNORECASE)
    if exp_match:
        explanation = exp_match.group(1).strip()
    else:
        explanation = ""
        
    if return_response:
        # Pass dummy response obj and chat obj
        class MockUsage:
            def __init__(self, in_t, out_t):
                self.prompt_token_count = in_t
                self.candidates_token_count = out_t
        class MockResponse:
            def __init__(self, text, in_t, out_t):
                self.text = text
                self.usage_metadata = MockUsage(in_t, out_t)
        usage = response.usage
        in_t = usage.prompt_tokens if usage else 0
        out_t = usage.completion_tokens if usage else 0
        resp_obj = MockResponse(sql_text, in_t, out_t)
        
        return sql_text, resp_obj, chat, prompt, explanation
    return sql_text

if __name__ == "__main__":
    # Quick test when running sql_gen.py directly
    async def main():
        print("Testing SQL Generator...")
        query = "which items are bought most frequently?"
        print(f"\nQuery: {query}")
        print("\nGenerated SQL:")
        try:
            sql, resp, chat, full_prompt = await generate_sql(query, return_response=True)
            print(sql)
            # Log via db instead of file
            update_log_sync(
                module="sql_gen_test",
                level="INFO",
                event_type="TEST_SUCCESS",
                message="Test query generated successfully",
                details={"query": query, "sql": sql}
            )
        except Exception as e:
            log_error_sync("sql_gen_test", "TEST_ERROR", e, "Error in test run")
            print(f"Error: {e}")
            
    asyncio.run(main())
