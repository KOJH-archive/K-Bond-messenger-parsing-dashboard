import time
import sys
import csv
import os
import re
import requests # 대시보드 전송을 위한 라이브러리
from collections import deque
import uiautomation as auto
import datetime
import ctypes
from ctypes import wintypes

# Windows API 정의 (Native Message용)
User32 = ctypes.WinDLL('user32', use_last_error=True)
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E

print("--- Debug: Imports complete ---")

# 타겟 채팅방 이름
TARGET_CHAT_NAME = "[채권] 블커본드"
WEBHOOK_URL = "http://127.0.0.1:5000/update"

def get_native_text(hwnd):
    """SendMessage(WM_GETTEXT)를 사용하여 윈도우 핸들로부터 직접 텍스트 추출 (백그라운드/고속)"""
    try:
        length = User32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            User32.SendMessageW(hwnd, WM_GETTEXT, length + 1, ctypes.byref(buffer))
            return buffer.value
    except:
        pass
    return ""

class KBondLogger:
    def __init__(self):
        self.current_date = None
        self.file = None
        self.writer = None

    def get_writer(self):
        date_str = time.strftime('%Y-%m-%d')
        if self.current_date != date_str:
            if self.file: self.file.close()
            self.current_date = date_str
            output_file = f"kbond_messages_{date_str}.csv"
            file_exists = os.path.isfile(output_file)
            self.file = open(output_file, mode='a', encoding='utf-8-sig', newline='', buffering=1)
            self.writer = csv.writer(self.file)
            if not file_exists:
                self.writer.writerow(["수집시간", "송신자", "종목", "만기", "구분", "대화내용"])
            self.file.flush()
        return self.writer

    def log(self, timestamp, message):
        writer = self.get_writer()
        pattern = r"^\s*(.*?)\s*\(\s*(\d{1,2}:\d{1,2}:\d{1,2})\s*\)\s*:\s*(.*)$"
        match = re.match(pattern, message, re.DOTALL)
        
        parsed_data = {"timestamp": timestamp, "raw": message, "sender": "", "msg_time": "", "ticker": "", "maturity": "", "side": "", "content": message}

        if match:
            sender, msg_time, content = [m.strip() for m in match.groups()]
            
            # --- 필터링: 인사말 및 종목정보 없는 메시지 제외 ---
            greetings = ["감사", "수고", "고생", "점심", "퇴근", "좋은", "행복", "즐거운"]
            if any(x in content for x in greetings) and len(content) < 40:
                # 인사말이 들어있고 내용이 짧으면 매매 정보가 아닐 확률이 높음
                return
            
            ticker = ""
            side = ""
            # 매수/매도 구분 로직 개선 (V2): 
            # 1. '팔자', '매도' 등 명시적 키워드를 최우선으로 확인
            # 2. 기호(+, -)는 키워드가 없을 때만 보조적으로 확인
            side = ""
            if re.search(r"(팔자|매도|오퍼|offer)", content):
                side = "매도"
            elif re.search(r"(사자|매수|비드|bid)", content):
                side = "매수"
            elif re.search(r"(확정|Done|체결|거래)", content):
                side = "거래"
            elif "+" in content:
                side = "매수"
            elif "-" in content:
                side = "매도"
            
            if any(x in content for x in ["보류", "취소", "캔슬", "cancel"]): side = f"{side}(중단)" if side else "중단"
            # 종목명(Ticker) 추출 로직 개선 (V5): 
            # 1. MBS(1-6), KTB, CD 등 영문 종목 지원 추가
            # 2. '또는', '교체', '문의' 등 대화 내용 필터링 대거 보완
            ticker = ""
            # 패턴: (통안채 년.월.일통) OR (한글/영문+숫자+괄호) OR (순수 한글+괄호) OR (순수 영문+괄호) OR (숫자-숫자 시리즈)
            ticker_pattern = r"(\d{2,4}(?:\.\d{1,2}){1,2}통|[가-힣a-zA-Z]{1,12}\d+[-\d\w]*(?:\([가-힣\d-]{1,6}\))?|[가-힣]{2,12}(?:\([가-힣\d-]{1,6}\))?|[a-zA-Z]{2,10}(?:\([\d-]{1,6}\))?|\d{2,3}-\d{1,2})"
            
            candidates = []
            for m in re.finditer(ticker_pattern, content):
                cand = m.group(1).strip()
                if len(cand) < 2: continue
                
                # 필터링 1: 날짜 패턴 제외 (27.09 등)
                if re.match(r"^\d{1,2}[\./-]\d{1,2}$", cand) and "." in cand: continue
                
                # 필터링 2: 전화번호 오인식 방지
                if re.match(r"^\d{2,3}-\d{1,2}$", cand):
                    after_text = content[m.end():m.end()+1]
                    if after_text == "-": continue 
                
                # 필터링 3: 노이즈 키워드 블랙리스트 확장
                noise_keywords = [
                    "팔자", "사자", "매도", "매수", "비드", "오퍼", "수반", "민평", "민", "쩜", "끝", "원", 
                    "목", "금", "월", "화", "수", "토", "일", "휴일", "대체휴일", "평일", "당일", "있을까요", "문의", "부탁", "확인",
                    "또는", "유사", "만기", "있는", "상기", "협의", "가능", "교체", "배정", "내역", "기타", "구조", "매체",
                    "거래", "체결", "완료", "확정", "추팔", "done", "후"
                ]
                if cand in noise_keywords: continue
                if any(kw in cand for kw in ["있을까요", "문의", "부탁", "교체가능"]): continue
                
                # '민2', '쩜66' 처럼 지표 단어로 시작하는 짧은 단어 제외
                if any(cand.startswith(kw) for kw in ["민", "쩜", "끝"]) and len(cand) <= 4:
                    continue
                
                candidates.append((m.start(), cand))
            
            if candidates:
                # 가장 앞쪽에 등장하는 후보 선택
                candidates.sort(key=lambda x: x[0])
                ticker = candidates[0][1]
            
            # --- 최종 필터링: 종목명이 없으면 대시보드에서 제외 ---
            if not ticker or len(ticker) < 2:
                return
            maturity = ""
            maturity_match = re.search(r"(\d{2,4}[\./]\d{1,2}(?:[\./]\d{1,2})?)", content)
            if maturity_match:
                found_date = maturity_match.group(1)
                if found_date != ticker: maturity = found_date

            parsed_data.update({"sender": sender, "msg_time": msg_time, "ticker": ticker, "maturity": maturity, "side": side, "content": content})
            writer.writerow([timestamp, sender, ticker, maturity, side, content])
        else:
            writer.writerow([timestamp, "", "", "", "", message])
        
        self.file.flush()
        try:
            requests.post(WEBHOOK_URL, json=parsed_data, timeout=0.5)
        except: pass

    def close(self):
        if self.file: self.file.close()

logger = KBondLogger()

def find_best_chat_handle(kbond_window):
    """창 내부에서 실시간 대화가 포함된 최적의 HWND를 탐색 (클래스 기반 정밀 탐색)"""
    best_hwnd = None
    best_time = "00:00:00"
    
    # 우선순위 클래스 목록 (델파이/VCL 기반 메신저에서 주로 사용)
    PRIORITY_CLASSES = ["TJvRichEdit", "TRxRichEdit", "TRichEdit", "TCalcEdit"]
    
    def _search(control, depth=0):
        nonlocal best_hwnd, best_time
        if depth > 15: return # 탐색 깊이 확장
        
        try:
            hwnd = control.NativeWindowHandle
            class_name = control.ClassName
            
            if hwnd:
                text = get_native_text(hwnd)
                if text and len(text.strip()) > 10:
                    # 시간 패턴 검색 (HH:MM:SS)
                    times = re.findall(r"(\d{1,2}:\d{1,2}:\d{1,2})", text)
                    if times:
                        latest = max(times)
                        # 클래스가 우선순위에 해당하면 가점 부여 로직 대신, 
                        # 단순히 최신 시간을 가진 핸들을 찾되 클래스 정보를 로그에 활용
                        if latest >= best_time:
                            best_time = latest
                            best_hwnd = hwnd
                            # print(f"--- Debug: Candidate Found - HWND: {hwnd}, Class: {class_name}, Time: {latest}")
        except: pass
        
        for child in control.GetChildren():
            _search(child, depth + 1)
    
    _search(kbond_window)
    return best_hwnd, best_time

def run_scraper():
    print("==================================================")
    print("🚀 K-Bond 네이티브 메시지 수집기 (V2.0)")
    print("전체 선택/복사 없이 백그라운드에서 실시간 수집합니다.")
    print("==================================================")
    
    # 초기 상태 설정
    target_hwnd = None
    last_processed_time = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime("%H:%M:%S")
    processed_at_time = set()
    last_ping_time = 0
    last_refresh_time = 0
    
    def get_kbond_window():
        for win in auto.GetRootControl().GetChildren():
            try:
                name = win.Name or ""
                if "[채권]" in name and "블커본드" in name:
                    return win
            except: continue
        return None

    kbond_window = get_kbond_window()
    if not kbond_window:
        print("⚠️ 안내: K-Bond 창을 찾을 수 없습니다. 메신저를 켜주세요.")

    while True:
        try:
            # 1. 창 연결 확인 및 복구
            if not kbond_window or not kbond_window.Exists(0):
                kbond_window = get_kbond_window()
                if not kbond_window:
                    time.sleep(2)
                    continue
                else:
                    print(f"🔄 창 연결 복구 완료: {kbond_window.Name}")
                    target_hwnd = None # 핸들도 새로 찾아야 함

            # 2. 상테 체크 및 동기화
            now_ts = datetime.datetime.now()
            
            # 10초마다 대시보드 핑
            if time.time() - last_ping_time > 10:
                try: requests.post(WEBHOOK_URL, json={"type": "ping"}, timeout=0.1)
                except: pass
                last_ping_time = time.time()

            # 1분마다 또는 핸들이 없을 때 최적의 구역(HWND) 재탐색
            if not target_hwnd or time.time() - last_refresh_time > 60:
                print("📡 실시간 데이터 구역 동기화 중...")
                found_hwnd, found_time = find_best_chat_handle(kbond_window)
                if found_hwnd:
                    target_hwnd = found_hwnd
                    print(f"🎯 실시간 핸들 확보: {target_hwnd} (발견 시각: {found_time})")
                last_refresh_time = time.time()

            if not target_hwnd:
                time.sleep(1)
                continue

            # 3. 데이터 추출 (Native 방식)
            full_text = get_native_text(target_hwnd)
            if not full_text:
                time.sleep(0.5)
                continue
            
            lines = full_text.splitlines()

            # 4. 신규 메시지 처리
            new_batch = []
            current_max_time = last_processed_time
            new_at_time = set()
            pattern = r"^\s*(.*?)\s*\(\s*(\d{1,2}:\d{1,2}:\d{1,2})\s*\)\s*:\s*(.*)$"

            for line in reversed(lines):
                line = (line or "").strip().replace('\u200b', '')
                if not line: continue
                match = re.match(pattern, line, re.DOTALL)
                if match:
                    sender, msg_time, content = [m.strip() for m in match.groups()]
                    msg_id = f"{sender}_{re.sub(r'\s+', '', content)[:30]}"
                    
                    if msg_time > last_processed_time:
                        new_batch.append(line)
                        if msg_time > current_max_time:
                            current_max_time = msg_time
                            new_at_time = {msg_id}
                        elif msg_time == current_max_time:
                            new_at_time.add(msg_id)
                    elif msg_time == last_processed_time:
                        if msg_id not in processed_at_time:
                            new_batch.append(line)
                            processed_at_time.add(msg_id)
                    else: break

            # 워터마크 업데이트
            if current_max_time > last_processed_time:
                last_processed_time = current_max_time
                processed_at_time = new_at_time

            # 5. 출력 및 로그
            if new_batch:
                print(f"--- 신규 메시지 {len(new_batch)}건 (Native) ---")
                for msg_text in reversed(new_batch):
                    ts = time.strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{ts}] {msg_text[:100]}...")
                    logger.log(ts, msg_text)

            time.sleep(0.5)
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"에러: {e}")
            time.sleep(1)

if __name__ == "__main__":
    run_scraper()
