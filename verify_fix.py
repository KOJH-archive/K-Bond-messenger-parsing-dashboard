import re

def parse_msg(content):
    # 1. Maturity detection
    maturity = ""
    maturity_match = re.search(r"(\d{2,4}[\./]\d{1,2}(?:[\./]\d{1,2})?)", content)
    if maturity_match:
        maturity = maturity_match.group(1)
    
    # 2. Extract content after maturity or strip maturity to avoid confusion
    search_content = content
    if maturity:
        # Avoid stripping the first word if it's not the maturity
        # Just use the whole content but refine the ticker regex
        pass

    # 3. Ticker extraction refined
    # Pattern: 
    # A. [Name]+[Digits]+[Optional Suffix like -2(지)]
    # B. [Pure Korean 2-10 chars]
    # C. Avoid phone numbers (look for - followed by 4 digits at the end of word)
    
    # Let's try to exclude phone-like patterns: 02-37, 010-xxxx, etc.
    # A ticker usually doesn't have 4 digits after a dash unless it's a very specific bond,
    # but phone numbers definitely do.
    
    ticker = ""
    # We look for the bond name. It often starts with Korean.
    # We exclude parts that look like phone numbers [0-9]{2,3}-[0-9]{3,4}-[0-9]{4}
    
    # Improved Regex:
    # (Group 1: Name+Digits+Suffix) | (Group 2: Pure Korean)
    # And we use negative lookahead to avoid phone number fragments like 02-37
    ticker_pattern = r"([가-힣a-zA-Z]+\d+[-\d]*(?:\([가-힣]\))?|[가-힣]{2,10})"
    
    # Find all candidates
    matches = re.finditer(ticker_pattern, content)
    for m in matches:
        cand = m.group(1)
        # Validate candidate
        # 1. Not the maturity string
        if cand == maturity: continue
        # 2. Not a phone number fragment (e.g. 02, 010, or follows a dash with 3+ digits)
        if cand in ["팔자", "사자", "매도", "매수", "비드", "오퍼"]: continue
        
        # Phone number check: if the match is part of something like "02-3772"
        # We can check the context in the original string
        start, end = m.span()
        context_after = content[end:end+10]
        if re.match(r"^-\d{3,4}", context_after): # It's followed by -XXXX, likely a phone number
            continue
            
        # If it's something like "02-37" (the original bug)
        if re.match(r"^\d{2,3}-\d{1,2}$", cand):
            # Check if it's a phone number prefix
            if cand.startswith("02") or cand.startswith("01"): 
                continue

        ticker = cand
        break # Take the first valid one
        
    return ticker, maturity

test_cases = [
    "26.10.30(금) JB우리캐피탈524-2(지) (민 3.056/끝.02/AA-) 팔자 (BNK 채권부 3215-1520)",
    "26.8.20 수출입 +0.25원 2.746% 팔자 (민 2.739 끝.49) 수반 [한화 02-3772-7349]",
    "25.12.01 삼성전자10-1 (사자)",
    "현대카드923-2 팔자"
]

print(f"{'Input':<50} | {'Ticker':<20} | {'Maturity'}")
print("-" * 100)
for case in test_cases:
    t, m = parse_msg(case)
    print(f"{case[:48]:<50} | {t:<20} | {m}")
