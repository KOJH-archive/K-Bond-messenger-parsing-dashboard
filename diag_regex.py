import re

def test_logic(content):
    print(f"\n--- Testing: {content} ---")
    # Current code logic
    pattern = r"([가-힣a-zA-Z]+\d+[-\d]*(?:\([가-힣]\))?|[가-힣]{2,10})"
    
    matches = list(re.finditer(pattern, content))
    for i, m in enumerate(matches):
        print(f"Match {i}: '{m.group(1)}' at {m.span()}")

    match = re.search(pattern, content)
    if match:
        cand = match.group(1).strip()
        print(f"Chosen by re.search: '{cand}'")
    
    return ""

test_cases = [
    "현대캐피탈(26.11.19) 팔자 100억(민평 3.007 쩜66, 목) (미래에셋증권 3774-1896)",
    "26.5.28(목) 재정증권 (민2.655 끝60) 민+1.1원 2.603 팔자 <수10> (트래디션FICC 6021-5876)"
]

for case in test_cases:
    test_logic(case)
