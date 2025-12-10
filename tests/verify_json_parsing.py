import re
import json
import ast

def parse_response(response_text):
    print(f"--- Testing Response ---\n{response_text}\n------------------------")
    json_str = ""
    
    # 4-1. Markdown Code Block 패턴 우선 검색 (```json ... ```)
    code_block_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if code_block_match:
        print("Match: Markdown JSON")
        json_str = code_block_match.group(1)
    else:
        # 4-2. 일반 Code Block 패턴 검색 (``` ... ```)
        code_block_match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
        if code_block_match:
            print("Match: Generic Code Block")
            json_str = code_block_match.group(1)
        else:
            # 4-3. 최후의 수단: 가장 바깥쪽 중괄호 찾기
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                print("Match: Braces")
                json_str = json_match.group()
    
    if json_str:
        try:
            data = json.loads(json_str)
            print("JSON Parse Success:", data)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            try:
                data = ast.literal_eval(json_str)
                print("AST Parse Success:", data)
                return data
            except:
                print("AST Parse Failed")
                return None
    else:
        print("No JSON found")
        return None

# Test Cases
test_1 = '{"products": [{"name": "Test"}]}'
test_2 = '```json\n{"products": [{"name": "Test"}]}\n```'
test_3 = 'Here is the JSON:\n```json\n{"products": [{"name": "Test"}]}\n```'
test_4 = 'Here is the JSON:\n```\n{"products": [{"name": "Test"}]}\n```'
test_5 = 'Some text {"products": [{"name": "Test"}]} some text'
test_6 = '```json\n{"products": [{"name": "Test"}]\n```' # Invalid JSON (missing closing brace for object, but let's see) -> actually missing } for list is ] but missing } for object. 
# Let's try a broken one that ast might fix? ast.literal_eval is for python syntax, so it might work if it looks like python dict.
test_7 = "{'products': [{'name': 'Test'}]}" # Single quotes (Python style)

print("Test 1 (Standard):")
parse_response(test_1)
print("\nTest 2 (Markdown JSON):")
parse_response(test_2)
print("\nTest 3 (Text + Markdown JSON):")
parse_response(test_3)
print("\nTest 4 (Text + Generic Code Block):")
parse_response(test_4)
print("\nTest 5 (Text + Braces):")
parse_response(test_5)
print("\nTest 7 (Single Quotes - AST):")
parse_response(test_7)
