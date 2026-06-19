import re

def test_new_logic(content):
    print(f"Testing: {content}")
    ticker = ""
    # The regex I just added
    pattern = r"([가-힣a-zA-Z]+\d+[-\d]*(?:\([가-힣]\))?|[가-힣]{2,10})"
    
    match = re.search(pattern, content)
    if match:
        print(f"First match: '{match.group(1)}' at {match.span()}")
        cand = match.group(1).strip()
        if re.match(r"^(0\d{1,2}-\d{1,2})$", cand):
            print("  Rejected: phone prefix")
            ticker = ""
        elif cand in ["팔자", "사자", "매도", "매수", "비드", "오퍼", "수반"]:
            print("  Rejected: keyword")
            ticker = ""
        else:
            ticker = cand
            print(f"  Accepted: {ticker}")
    else:
        print("No match found")
        
    return ticker

case = "현대캐피탈(26.11.19) 팔자 100억(민평 3.007 쩜66, 목) (미래에셋증권 3774-1896)"
result = test_new_logic(case)
print(f"Final Ticker: {result}")
