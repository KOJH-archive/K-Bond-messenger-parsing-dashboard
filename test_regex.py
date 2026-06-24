import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

def test_extraction(content):
    ticker = ""
    ticker_pattern = r"(\d{2,4}(?:\.\d{1,2}){1,2}통|[가-힣a-zA-Z]{1,12}\d+[-\d\w]*(?:\([가-힣\d-]{1,6}\))?|[가-힣]{2,12}(?:\([가-힣\d-]{1,6}\))?|[a-zA-Z]{2,10}(?:\([\d-]{1,6}\))?|\d{2,3}-\d{1,2})"
    candidates = []
    for m in re.finditer(ticker_pattern, content):
        cand = m.group(1).strip()
        if len(cand) < 2: continue
        if re.match(r"^\d{1,2}[\./-]\d{1,2}$", cand) and "." in cand: continue
        if re.match(r"^\d{2,3}-\d{1,2}$", cand):
            after_text = content[m.end():m.end()+1]
            if after_text == "-": continue 
        noise_keywords = [
            "팔자", "사자", "매도", "매수", "비드", "오퍼", "수반", "민평", "민", "쩜", "끝", "원", 
            "목", "금", "월", "화", "수", "토", "일", "휴일", "대체휴일", "평일", "당일", "있을까요", "문의", "부탁", "확인",
            "또는", "유사", "만기", "있는", "상기", "협의", "가능", "교체", "배정", "내역", "기타", "구조", "매체",
            "거래", "체결", "완료", "확정", "추팔", "done", "후"
        ]
        if cand in noise_keywords: continue
        if any(kw in cand for kw in ["있을까요", "문의", "부탁", "교체가능"]): continue
        if any(cand.startswith(kw) for kw in ["민", "쩜", "끝"]) and len(cand) <= 4: continue
        candidates.append((m.start(), cand))
    
    if candidates:
        candidates.sort(key=lambda x: x[0])
        ticker = candidates[0][1]
    return ticker

test_cases = [
    "27.7.19 (월, 대체휴일) 산은캐피탈743-4 (민3.928, 끝.07, AA-) 팔자 (IBKS 6915-5385)",
    "JB우리캐피탈524-2(지) (민 3.056/끝.02/AA-) 팔자 (BNK 채권부 3215-1520)",
    "수출입 +0.25원 2.746% 팔자 (민 2.739 끝.49) 수반 [한화 02-3772-7349]"
]

for i, case in enumerate(test_cases):
    result = test_extraction(case)
    print(f"Case {i+1}: {case}")
    print(f"Result: '{result}'")
    print("-" * 20)
