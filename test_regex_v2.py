import re
import sys

def test_logic(content):
    pattern = r"([가-힣a-zA-Z]+\d+[-\d]*(?:\([가-힣]\))?|[가-힣]{2,10})"
    match = re.search(pattern, content)
    res = match.group(1) if match else "None"
    return res

test_cases = [
    "현대캐피탈(26.11.19) 팔자 100억(민평 3.007 쩜66, 목) (미래에셋증권 3774-1896)",
    "26.5.28(목) 재정증권 (민2.655 끝60) 민+1.1원 2.603 팔자 <수10> (트래디션FICC 6021-5876)"
]

with open("test_results.txt", "w", encoding="utf-8") as f:
    for case in test_cases:
        res = test_logic(case)
        f.write(f"Input: {case}\nResult: {res}\n\n")

print("Done")
