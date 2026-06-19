import re

def test_extraction(content):
    ticker = ""
    # Current regex in kbond_scraper.py
    ticker_match = re.search(r"(\d{2}-\d{1,2}|[가-힣a-zA-Z]+\d+[-\d]*)", content)
    if ticker_match:
        ticker = ticker_match.group(1).strip()
    return ticker

test_cases = [
    "JB우리캐피탈524-2(지) (민 3.056/끝.02/AA-) 팔자 (BNK 채권부 3215-1520)",
    "수출입 +0.25원 2.746% 팔자 (민 2.739 끝.49) 수반 [한화 02-3772-7349]"
]

for i, case in enumerate(test_cases):
    result = test_extraction(case)
    print(f"Case {i+1}: {case}")
    print(f"Result: '{result}'")
    print("-" * 20)
