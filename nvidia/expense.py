def calculate_cost(input_tokens: int, output_tokens: int) -> dict:
    """
    Calculates the token consumption cost for gemini-2.5-flash in INR.
    
    Approximated Pricing:
    - Input: $0.3 per 1 million tokens
    - Output: $2.5 per 1 million tokens
    - Exchange rate assumed: 1 USD = ~95 inr
    """
    USD_TO_INR = 95
    
    # Cost per 1M tokens in USD
    INPUT_COST_PER_MILLION_USD = 0.25
    OUTPUT_COST_PER_MILLION_USD = 1.50
    
    input_cost_usd = (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION_USD
    output_cost_usd = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION_USD
    
    total_cost_usd = input_cost_usd + output_cost_usd
    total_cost_inr = total_cost_usd * USD_TO_INR
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": total_cost_usd,
        "cost_inr": total_cost_inr
    }

def print_expense(response):
    """
    Parses a Google GenAI response object to extract token usage and print the cost in INR.
    Can be used directly on the `response` object returned by `generate_content`.
    """
    try:
        # Check if usage_metadata exists
        if not hasattr(response, 'usage_metadata') or response.usage_metadata is None:
            print("No usage metadata found in the response.")
            return None
            
        usage = response.usage_metadata
        input_tokens = getattr(usage, 'prompt_token_count', 0)
        output_tokens = getattr(usage, 'candidates_token_count', 0)
        
        cost_info = calculate_cost(input_tokens, output_tokens)
        
        print("\n" + "="*40)
        print(f"Token Expense (Laguna)")
        print("="*40)
        print(f"Input Tokens : {cost_info['input_tokens']:,}")
        print(f"Output Tokens: {cost_info['output_tokens']:,}")
        print(f"Total Tokens : {cost_info['total_tokens']:,}")
        print(f"Total Cost   : ₹ {cost_info['cost_inr']:.6f} INR (approx ${cost_info['cost_usd']:.6f})")
        print("="*40 + "\n")
        
        return cost_info
    except Exception as e:
        print(f"Failed to extract expense from response: {e}")
        return None

if __name__ == "__main__":
    # Test example
    print("Testing token calculation...")
    print(calculate_cost(input_tokens=1500, output_tokens=300))
    print("Expense calculation script ready!")
