import sys
import time
import re
import requests
import numpy as np
import cv2
import pyautogui
from PIL import Image
import easyocr
import uiautomation as auto
from collections import deque

# --- 설정 ---
WEBHOOK_URL = "http://127.0.0.1:5000/update"
CAPTURE_INTERVAL = 1.0  # 초 단위 캡처 간격
DEBUG_SAVE_IMAGE = True # 문제 발생 시 캡처된 이미지를 저장하여 확인 (temp_capture.png)

# --- 정규식 패턴 ---
# [만기일 추출] 27.09, 2027.03.10, 24-12, 25-4, 31.4.3 등
MATURITY_PATTERN = r"(\d{2,4}[./-]\d{1,2}[./-]\d{1,2}|\d{2,4}[./-]\d{1,2}|\d{2}-\d{1,2})"
# [종목명 추출] (V6) 통안채 및 한글/영문+숫자+괄호 조합
TICKER_PATTERN = r"(\d{2,4}(?:\.\d{1,2}){1,2}통|[가-힣a-zA-Z]{1,12}\d+[-\d\w]*(?:\([가-힣\d-]{1,6}\))?|[가-힣]{2,12}(?:\([가-힣\d-]{1,6}\))?|[a-zA-Z]{2,10}(?:\([\d-]{1,6}\))?|\d{2,3}-\d{1,2})"
# [매수/매도 추출] 팔자, 사자, 매도, 매수
SIDE_PATTERN = r"(팔자|사자|매도|매수)"

class OCRScraper:
    def __init__(self):
        print("OCR 엔진 초기화 중 (최초 실행 시 모델 다운로드로 인해 시간이 소요될 수 있습니다)...")
        self.reader = easyocr.Reader(['ko', 'en'])
        self.region = None
        self.processed_texts = deque(maxlen=50)  # 중복 방지를 위한 최근 텍스트 저장
        print("OCR 엔진 준비 완료.")

    def select_region(self):
        print("\n==================================================")
        print("📢 [중요] 5초 안에 수집하고 싶은 '채팅 내용 영역'을 한 번 클릭해 주세요!")
        print("클릭한 위치의 컨트롤 영역을 자동으로 캡처 범위로 설정합니다.")
        print("==================================================")
        
        for i in range(5, 0, -1):
            print(f"{i}초 대기 중...")
            time.sleep(1)
            
        focused = auto.GetFocusedControl()
        if not focused:
            print("오류: 포커스된 컨트롤을 찾을 수 없습니다. 화면 전체를 대상으로 시도합니다.")
            return None
            
        rect = focused.BoundingRectangle
        print(f"영역 설정 완료: {focused.Name or focused.ClassName} ({rect.left}, {rect.top}, {rect.width()}, {rect.height()})")
        return (rect.left, rect.top, rect.width(), rect.height())

    def parse_text(self, text):
        """OCR로 읽은 텍스트 줄을 분석하여 구조화 데이터 생성"""
        # K-Bond 메시지는 보통 "이름 (시간) : 내용" 형태이지만 
        # OCR 특성상 줄이 끊길 수 있으므로 유연하게 파싱
        
        # 1. 시간 패턴 찾기 (HH:MM:SS)
        time_match = re.search(r"(\d{1,2}:\d{1,2}:\d{1,2})", text)
        msg_time = time_match.group(1) if time_match else time.strftime("%H:%M:%S")
        
        # 2. 만기일
        mat_match = re.search(MATURITY_PATTERN, text)
        maturity = mat_match.group(1) if mat_match else ""
        
        # 3. 매수/매도 (키워드 우선순위 적용)
        side = "정보"
        if re.search(r"(팔자|매도|오퍼|offer)", text):
            side = "매도"
        elif re.search(r"(사자|매수|비드|bid)", text):
            side = "매수"
        elif re.search(r"(확정|Done|체결|거래)", text):
            side = "거래"
        elif "+" in text:
            side = "매수"
        elif "-" in text:
            side = "매도"
        
        if any(x in text for x in ["보류", "취소", "캔슬", "cancel"]): 
            side = f"{side}(중단)" if side != "정보" else "중단"
        
        # 4. 종목 (V5 로직: 필터링 포함)
        ticker = ""
        for m in re.finditer(TICKER_PATTERN, text):
            cand = m.group(1).strip()
            if len(cand) < 2: continue
            
            # 블랙리스트 필터링
            noise = ["팔자", "사자", "매수", "매도", "수반", "민평", "민", "쩜", "끝", "원", "또는", "교체", "가능", "거래", "체결", "완료", "확정", "추팔", "done", "후"]
            if cand in noise or any(kw in cand for kw in ["있을까요", "문의"]): continue
            if any(cand.startswith(kw) for kw in ["민", "쩜", "끝"]) and len(cand) <= 4: continue
            
            ticker = cand
            break
        
        # 5. 이름 (시간 앞의 문자열)
        sender = "알수없음"
        if time_match:
            idx = text.find(time_match.group(1))
            if idx > 0:
                sender_part = text[:idx].strip().replace("(", "").replace(")", "")
                if sender_part:
                    sender = sender_part.split()[-1] # 마지막 단어를 이름으로 간주

        return {
            "time": msg_time,
            "sender": sender,
            "ticker": ticker,
            "maturity": maturity,
            "side": side,
            "content": text
        }

    def run(self):
        self.region = self.select_region()
        if not self.region:
            print("오류: 영역을 설정하지 못했습니다. 프로그램을 종료합니다.")
            return

        print("\n실시간 OCR 모니터링 시작... (그만두려면 Ctrl+C)")
        
        last_capture_time = 0
        
        while True:
            try:
                # 지정된 간격으로 캡처
                if time.time() - last_capture_time < CAPTURE_INTERVAL:
                    time.sleep(0.1)
                    continue
                
                last_capture_time = time.time()
                
                # 1. 화면 캡처
                screenshot = pyautogui.screenshot(region=self.region)
                frame = np.array(screenshot)
                
                # --- [화질 개선 프로세스] ---
                # 1) 그레이스케일 변환 (색상 노이즈 제거)
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                
                # 2) 이미지 크기 2배 확대 (작은 글자 인식률 향상)
                gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                
                # 3) 대비 강화 (선명하게)
                gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                
                if DEBUG_SAVE_IMAGE:
                    cv2.imwrite("temp_capture.png", gray)
                
                # 2. OCR 실행 (paragraph=True로 문맥 파악 강화)
                results = self.reader.readtext(gray, detail=0, paragraph=True)
                
                if not results:
                    continue
                
                # 3. 새로운 텍스트 감지 및 처리
                # OCR 결과는 보통 아래쪽이 최신임
                for raw_text in results:
                    raw_text = raw_text.strip()
                    if len(raw_text) < 5: continue
                    
                    # 중복 체크 (최근 처리한 50개 문장과 비교)
                    is_duplicate = False
                    for p in self.processed_texts:
                        # 80% 이상 유사하면 중복으로 간발 (OCR 오차 대응)
                        if raw_text in p or p in raw_text:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        data = self.parse_text(raw_text)
                        
                        # 대시보드 전송
                        ts = time.strftime('%Y-%m-%d %H:%M:%S')
                        print(f"[{ts}] [OCR감지] {data['sender']} ({data['time']}): {raw_text}")
                        
                        try:
                            requests.post(WEBHOOK_URL, json=data, timeout=1)
                        except:
                            print("대시보드 전송 실패 (서버가 켜져 있는지 확인하세요)")
                            
                        self.processed_texts.append(raw_text)
                
                # 연결 유지용 핑
                requests.post(WEBHOOK_URL, json={"type": "ping"}, timeout=0.1)
                
            except KeyboardInterrupt:
                print("\n중단되었습니다.")
                break
            except Exception as e:
                print(f"에러 발생: {e}")
                time.sleep(1)

if __name__ == "__main__":
    scraper = OCRScraper()
    scraper.run()
