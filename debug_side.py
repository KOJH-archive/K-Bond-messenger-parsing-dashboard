import re

def identify_side(content):
    side = ""
    # Exact logic from kbond_scraper.py
    if any(x in content for x in ["사자", "매수", "비드", "bid"]): 
        side = "매수"
    elif any(x in content for x in ["팔자", "매도", "오퍼", "offer"]): 
        side = "매도"
    elif any(x in content for x in ["확정", "Done", "체결", "거래"]): 
        side = "거래"
    elif "+" in content: 
        side = "매수"
    elif "-" in content: 
        side = "매도"
    
    if any(x in content for x in ["보류", "취소", "캔슬", "cancel"]): 
        side = f"{side}(중단)" if side else "중단"
    
    return side

test_cases = [
    "수출입 +0.25원 2.746% 팔자 (민 2.739 끝.49) 수반 [한화 02-3772-7349]",
    "국민은행 (민평 2.804%/끝.84) +1.5원 팔자 [케이알 전략금융 2168-7449]"
]

for i, case in enumerate(test_cases):
    side = identify_side(case)
    print(f"Case {i+1}: {case}")
    print(f"Detected Side: {side}")
    print("-" * 20)
