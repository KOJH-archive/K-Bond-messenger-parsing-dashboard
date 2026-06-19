import time
import sys
import csv
import os
import re
import requests # 대시보드 전송을 위한 라이브러리
from collections import deque
import uiautomation as auto # 누락되었던 임포트 추가

print("--- Debug: Imports complete ---")

# 타겟 채팅방 이름
TARGET_CHAT_NAME = "[채권] 블커본드"

class KBondLogger:
    def __init__(self):
        self.current_date = None
        self.file = None
        self.writer = None

    def get_writer(self):
        date_str = time.strftime('%Y-%m-%d')
        if self.current_date != date_str:
            if self.file:
                self.file.close()
            
            self.current_date = date_str
            output_file = f"kbond_messages_{date_str}.csv"
            file_exists = os.path.isfile(output_file)
            
            self.file = open(output_file, mode='a', encoding='utf-8-sig', newline='', buffering=1)
            self.writer = csv.writer(self.file)
            if not file_exists:
                # 헤더 세분화: 종목명, 만기, 매수/매도, 가격 등 상세 필드 추가
                self.writer.writerow(["Timestamp", "RawMessage", "Sender", "MsgTime", "Ticker", "Maturity", "Side", "Content"])
            self.file.flush()
        
        return self.writer

    def log(self, timestamp, message):
        writer = self.get_writer()
        # 1차 파싱: "이름 (11:32:52) : 내용" (앞뒤 공백 허용 및 유연한 매칭)
        pattern = r"^\s*(.*?)\s*\(\s*(\d{1,2}:\d{1,2}:\d{1,2})\s*\)\s*:\s*(.*)$"
        match = re.match(pattern, message, re.DOTALL)
        
        parsed_data = {
            "timestamp": timestamp,
            "raw": message,
            "sender": "",
            "msg_time": "",
            "ticker": "",
            "maturity": "",
            "side": "",
            "content": message
        }

        if match:
            sender, msg_time, content = [m.strip() for m in match.groups()]
            
            # 전문가 제안 로직을 반영한 세부 파싱
            ticker = ""
            side = ""
            
            # 1. 구분(Side) 판별
            if any(x in content for x in ["사자", "매수", "비드", "bid", "+"]):
                side = "매수"
            elif any(x in content for x in ["팔자", "매도", "오퍼", "offer", "-"]):
                side = "매도"
            elif any(x in content for x in ["확정", "Done", "체결", "거래"]):
                side = "거래"

            # 2. 부정어(보류, 취소) 체크 -> side 무효화
            if any(x in content for x in ["보류", "취소", "캔슬", "cancel"]):
                side = f"{side}(중단)" if side else "중단"

            # 3. 종목(Ticker) 추출
            ticker_match = re.search(r"(\d{2}-\d{1,2}|[가-힣a-zA-Z]+\d+[-\d]*)", content)
            if ticker_match:
                ticker = ticker_match.group(1).strip()
            
            # 4. 만기일(Maturity) 추출
            # - 패턴: 27.09, 27/09, 2027.03.10 등
            maturity = ""
            # 만기일은 보통 . 또는 /를 사용하며, -는 Ticker와 겹칠 가능성이 높으므로 제외하거나 후순위 처리
            maturity_match = re.search(r"(\d{2,4}[\./]\d{1,2}(?:[\./]\d{1,2})?)", content)
            if maturity_match:
                found_date = maturity_match.group(1)
                # Ticker와 겹치는지 확인 (예: 24-7)
                if found_date != ticker:
                    maturity = found_date

            parsed_data.update({
                "sender": sender,
                "msg_time": msg_time,
                "ticker": ticker,
                "maturity": maturity,
                "side": side,
                "content": content
            })
            
            writer.writerow([timestamp, message, sender, msg_time, ticker, maturity, side, content])
        else:
            # 헤더 개수(8개)에 맞춰 빈 필드 추가
            writer.writerow([timestamp, message, "", "", "", "", "", ""])
        
        self.file.flush()

        # 대시보드 서버로 실시간 전송 시도
        try:
            requests.post("http://localhost:5000/update", json=parsed_data, timeout=0.5)
        except:
            pass # 서버가 꺼져있어도 스크래핑은 계속 진행

    def close(self):
        if self.file:
            self.file.close()

logger = KBondLogger()

def run_scraper():
    print("==================================================")
    print("📢 [중요] 5초 안에 수집하고 싶은 '메신저 채팅창'을 한 번 클릭해 주세요!")
    print("사용자가 클릭한 창을 기반으로 자동 추적을 시작합니다.")
    print("==================================================")
    
    # 5초간 대기하며 포커스된 창 감시
    target_window = None
    target_control = None
    
    for i in range(5, 0, -1):
        print(f"{i}초 대기 중...")
        time.sleep(1)
        
    focused = auto.GetFocusedControl()
    if focused:
        # 포커스된 컨트롤로부터 상위 창(WindowControl) 찾기
        curr = focused
        while curr and curr.ControlTypeName != "WindowControl":
            # 동시에 채팅 영역(RichEdit 등)인지 확인
            cls = curr.ClassName
            if any(c in cls for c in ["RichEdit", "Panel", "ListBox"]):
                target_control = curr
            curr = curr.GetParentControl()
        target_window = curr
        
    if not target_window or "[채권]" not in (target_window.Name or ""):
        print("경고: 클릭한 창이 K-Bond 채팅창이 아닌 것 같습니다. 자동 클래스 탐색으로 전환합니다.")
        # 자동 탐색 폴백 (기존 로직)
        kbond_window = None
        for win in auto.GetRootControl().GetChildren():
            try:
                name = win.Name.replace('\u200b', '')
                if "[채권]" in name and "블커본드" in name:
                    kbond_window = win
                    break
            except: continue
        target_window = kbond_window

    if not target_window:
        print("오류: 타겟 창을 찾을 수 없습니다.")
        return
    
    print(f"창 잠금 완료: {target_window.Name}")
    kbond_window = target_window

    # 창이 최소화되어 있는지 확인하고 '필요할 때만' 활성화
    try:
        # WindowPattern을 통해 최소화 상태(2) 확인
        if kbond_window.GetWindowPattern().WindowVisualState == 2:
            print("창이 최소화되어 있습니다. 수집을 위해 복구합니다.")
            kbond_window.Restore()
    except:
        # 속성 접근에 실패할 경우 안전하게 복구 시도 (이미 활성 상태면 영향 없음)
        pass
    
    # 처음 딱 한 번만 포커스를 줍니다 (사용자 방해 최소화)
    try:
        kbond_window.SetFocus()
    except:
        pass
    
    print(f"'{TARGET_CHAT_NAME}' 창 감지 성공. 모니터링을 시작합니다.")
    print("팁: 창이 다른 프로그램에 가려져 있어도 수집되므로 최소화만 하지 말아주세요.")

    # K-Bond의 채팅방은 구형 Delphi/VCL 기반인 경우가 많아 리스트가 아닌 텍스트 영역(RichEdit)인 경우가 많습니다.
    search_classes = ["TJvRichEdit", "TRxRichEdit", "TTntPanel", "TElMSListBox", "TRichEdit", "TEdit"]
    
    print("채팅 영역 전수 탐색 중...")
    
    candidates = []
    def find_all_candidates(control, depth=0):
        if depth > 12: return
        try:
            cls = control.ClassName
            text = control.Name or (control.GetValuePattern().Value if hasattr(control, "GetValuePattern") else "")
            
            # 패턴 1: 자신이 메시지 내용을 포함하고 있는 경우
            if "(" in text and ") :" in text:
                candidates.append(control)
                return # 하위는 더 안 봐도 됨 (보통 RichEdit가 말단이므로)
            
            # 패턴 2: 자식들이 메시지 형태인 경우 (Container)
            # 자식들을 샘플링하여 확인
            children = control.GetChildren()
            if children:
                if any("(" in (c.Name or "") and ") :" in (c.Name or "") for c in children[:5]):
                    candidates.append(control)
                    # 컨테이너는 자식들을 더 뒤져볼 필요가 있을 수 있으므로 리턴하지 않음
        except: pass
        
        for child in control.GetChildren():
            find_all_candidates(child, depth + 1)

    find_all_candidates(kbond_window)
    
    if not candidates:
        print("오류: 채팅 리스트 컨트롤을 찾을 수 없습니다.")
        return

    # [고도화] 후보들 중 진짜 '현재' 대화가 있는 컨트롤을 정밀 선정
    print(f"후보 컨트롤 {len(candidates)}개 발견. 최신성 검사 중...")
    target_control = None
    scraping_mode = "text"
    max_time_found = "00:00:00"
    
    pattern = r"(\d{1,2}:\d{1,2}:\d{1,2})"
    
    for cand in candidates:
        try:
            cand_mode = "text"
            children = cand.GetChildren()
            sample_text = ""
            
            # 자식 기반인지 텍스트 기반인지 판별 및 샘플 추출
            if children and any("(" in (c.Name or "") and ") :" in (c.Name or "") for c in children[:10]):
                cand_mode = "children"
                # 자식들 중 마지막 5개의 시간을 확인
                sample_text = " ".join([c.Name for c in children[-5:] if c.Name])
            else:
                cand_mode = "text"
                full = cand.Name or (cand.GetValuePattern().Value if hasattr(cand, "GetValuePattern") else "")
                sample_text = full[-500:] if full else ""
            
            # 해당 샘플에서 가장 늦은 시간 추출
            times = re.findall(pattern, sample_text)
            if times:
                latest = max(times)
                print(f"  - [{cand.ClassName}] 최신 시간: {latest} ({cand_mode})")
                if latest >= max_time_found:
                    max_time_found = latest
                    target_control = cand
                    scraping_mode = cand_mode
        except: continue
    
    if not target_control:
        print("오류: 유효한 수집 영역을 찾지 못했습니다.")
        return

    # [최후의 수단] 만약 수집된 시간이 현재 시간과 너무 차이난다면 (1시간 이상)
    # 사용자에게 수동 스크롤을 한 번 요청하거나 강제로 Ctrl+End 시도
    import datetime
    try:
        sys_time = datetime.datetime.now()
        found_time = datetime.datetime.strptime(max_time_found, "%H:%M:%S").replace(year=sys_time.year, month=sys_time.month, day=sys_time.day)
        
        diff = (sys_time - found_time).total_seconds()
        if diff > 3600: # 1시간 이상 차이남
            print("⚠️ 경고: 수집된 최신 대화가 현재 시각과 1시간 이상 차이가 납니다.")
            print("   (메신저 창을 한 번 클릭하고 가장 아래로 스크롤 해주시면 해결됩니다!)")
            # 강제 시도
            target_control.SetFocus()
            auto.SendKeys("{Ctrl}{End}")
            time.sleep(0.5)
    except: pass

    # 처리된 메시지를 식별하기 위한 고유 해시값 저장

    # 처리된 메시지를 식별하기 위한 고유 해시값 저장
    # NativeWindowHandle이 0일 수 있으므로 (내용+시간+이름)의 조합 사용
    processed_hashes = deque(maxlen=300)
    
    # 초기화
    initial_messages = target_control.GetChildren()
    for msg in initial_messages:
        try:
            msg_text = msg.Name or ""
            if msg_text:
                # 텍스트만으로 해시 생성 (충돌 방지를 위해 핸들도 있다면 추가)
                msg_id = hash(f"{msg_text}_{msg.NativeWindowHandle}")
                processed_hashes.append(msg_id)
        except: continue
    
    print(f"초기 설정 완료. (모니터링 주기: 0.2초)")
    
    # 워터마크 (마지막으로 처리한 메시지의 시간과 내용들)
    last_processed_time = "00:00:00"
    processed_at_time = set()
    
    # [설정] 스크래퍼 실행 시점의 최신 데이터를 가져옴 (is_initial=True 모드에서 워터마크만 설정)
    print("초기 워터마크 설정 중...")
    
    # 한 번 읽어서 현재 바닥에 있는 시간을 last_processed_time으로 설정
    try:
        import datetime
        sys_now = datetime.datetime.now()
        
        # 현재 화면의 줄들 가져오기
        initial_lines = []
        if scraping_mode == "children":
            initial_lines = [el.Name for el in target_control.GetChildren() if el.Name]
        else:
            txt = target_control.GetTextPattern().DocumentRange.GetText(-1) if hasattr(target_control, "GetTextPattern") else (target_control.Name or "")
            initial_lines = txt.splitlines()
        
        pattern = r"(\d{1,2}:\d{1,2}:\d{1,2})"
        found_times = []
        for line in initial_lines:
            match = re.search(pattern, line.strip())
            if match:
                found_times.append(match.group(1))
        
        if found_times:
            # 1. 일단 현재 보이는 것 중 가장 최신 시간 설정
            latest_in_view = max(found_times)
            last_processed_time = latest_in_view
            
            # 2. 만약 현재 시스템 시각(14:15)보다 너무 과거(09:34)라면, 
            #    K-Bond의 시간이 시스템 시간과 동기화되어 있다고 가정하고 워터마크를 현재 시각 근처로 강제 점프
            #    (단, K-Bond 시간이 아예 다른 대륙 시간인 경우를 대비해 5분 여유만 둠)
            sys_time_str = sys_now.strftime("%H:%M:%S")
            if sys_time_str > latest_in_view:
                # 시스템 시각이 메시지 시각보다 미래인 경우에만 (정상 상황)
                # 메시지가 30분 이상 과거라면 강제 점프
                t_latest = datetime.datetime.strptime(latest_in_view, "%H:%M:%S")
                t_sys = datetime.datetime.strptime(sys_time_str, "%H:%M:%S")
                if (t_sys - t_latest).total_seconds() > 1800: # 30분 차이
                    print(f"⏰ 현재 시각({sys_time_str})에 비해 발견된 메시지({latest_in_view})가 너무 과거입니다.")
                    print(f"   시스템 시각 기준으로 {sys_time_str} 이전의 모든 과거 내역을 스킵합니다...")
                    last_processed_time = (sys_now - datetime.timedelta(minutes=2)).strftime("%H:%M:%S")
    except Exception as e: 
        print(f"워터마크 설정 중 오류: {e}")
        pass

    print(f"초기 워터마크 완료: {last_processed_time} 이후 메시지부터 수집합니다.")
    is_initial = False 
    last_full_text = ""
    last_ping_time = 0
    
    # 127.0.0.1로 고정하여 localhost 이슈 방지
    WEBHOOK_URL = "http://127.0.0.1:5000/update"
    
    try:
        while True:
            # 0. 주기적 핑 (대시보드 연결 확인용)
            if time.time() - last_ping_time > 10:
                try:
                    requests.post(WEBHOOK_URL, json={"type": "ping"}, timeout=0.1)
                    last_ping_time = time.time()
                except: pass

            try:
                # 1. 선정된 모드에 따라 데이터 가져오기
                lines = []
                # 현재 시간 확인
                import datetime
                sys_now = datetime.datetime.now()
                sys_time_str = sys_now.strftime("%H:%M:%S")

                if scraping_mode == "children":
                    current_elements = target_control.GetChildren()
                    lines = [el.Name for el in current_elements if el.Name]
                else:
                    # 통합 텍스트 모드
                    full_text = ""
                    try:
                        if hasattr(target_control, "GetTextPattern"):
                            full_text = target_control.GetTextPattern().DocumentRange.GetText(-1)
                    except: pass
                    if not full_text:
                        try:
                            val = target_control.GetValuePattern().Value
                            if val: full_text = val
                        except: pass
                    if not full_text:
                        full_text = target_control.Name or ""
                    
                    if full_text:
                        lines = full_text.splitlines()

                # 버퍼 상태 체크: 만약 여전히 너무 과거 데이터만 보인다면 강제 스크롤 시도
                if lines:
                    pattern_t = r"(\d{1,2}:\d{1,2}:\d{1,2})"
                    # 마지막 5줄에서 시간 추출
                    sample_end = " ".join(lines[-5:])
                    times_in_buffer = re.findall(pattern_t, sample_end)
                    if times_in_buffer:
                        latest_in_buffer = max(times_in_buffer)
                        # 시스템 시각과 30분 이상 차이 나면 '고착' 상태로 간주
                        try:
                            t_latest = datetime.datetime.strptime(latest_in_buffer, "%H:%M:%S")
                            t_sys = datetime.datetime.strptime(sys_time_str, "%H:%M:%S")
                            if (t_sys - t_latest).total_seconds() > 1800:
                                # 10초마다 한 번씩 강한 갱신 시도
                                if int(time.time()) % 10 == 0:
                                    print(f"🔄 버퍼 고착 감지 ({latest_in_buffer}). UI 강제 갱신(Ctrl+A, End) 시도 중...")
                                    target_control.SetFocus()
                                    # [핵심] 전체 선택 후 방향키로 해제하면 UI Automation 버퍼가 갱신되는 경우가 많음
                                    auto.SendKeys("{Ctrl}a{End}") 
                                    time.sleep(0.3)
                                    auto.SendKeys("{Ctrl}{End}")
                        except: pass

                if not lines:
                    time.sleep(0.5)
                    continue

                # 2. 새로운 메시지 스캔 (최신 메시지가 아래에 있음)
                new_batch = []
                pattern = r"^\s*(.*?)\s*\(\s*(\d{1,2}:\d{1,2}:\d{1,2})\s*\)\s*:\s*(.*)$"
                
                # 이번 스캔에서 발견된 가장 최근 시간 (업데이트용)
                current_max_time = last_processed_time
                new_at_time = set()

                for line in reversed(lines):
                    line = (line or "").replace('\u200b', '').strip()
                    if not line: continue
                    
                    match = re.match(pattern, line, re.DOTALL)
                    if match:
                        sender, msg_time, content = [m.strip() for m in match.groups()]
                        # 고유 식별자 (내용 공백 제거 등으로 안정화)
                        clean_content = re.sub(r'\s+', '', content)[:30]
                        msg_id = f"{sender}_{clean_content}"
                        
                        # [핵심 로직] 시간 기반 워터마크 필터링
                        if msg_time > last_processed_time:
                            # 완전히 새로운 시간대의 메시지
                            if not is_initial:
                                new_batch.append(line)
                            
                            # 워터마크 갱신 준비
                            if msg_time > current_max_time:
                                current_max_time = msg_time
                                new_at_time = {msg_id}
                            elif msg_time == current_max_time:
                                new_at_time.add(msg_id)

                        elif msg_time == last_processed_time:
                            # 같은 시간대라면 내용 확인 (중복 제거)
                            if msg_id not in processed_at_time:
                                if not is_initial:
                                    new_batch.append(line)
                                # 현재 최대 시간대의 세트에도 추가 (메모리상 유지)
                                processed_at_time.add(msg_id)
                        else:
                            # 과거 시간대의 메시지면 더 이상 볼 필요 없음
                            break
                
                # 워터마크 최종 갱신
                if current_max_time > last_processed_time:
                    last_processed_time = current_max_time
                    processed_at_time = new_at_time
                
                is_initial = False # 초기 1회 처리 후 모드로 전환
                
                # 3. 새로운 메시지 저장 및 출력
                if new_batch:
                    print(f"--- 신규 메시지 {len(new_batch)}건 처리 중 ---")
                    for msg_text in reversed(new_batch):
                        ts = time.strftime('%Y-%m-%d %H:%M:%S')
                        try:
                            # 콘솔 출력 시 인코딩 오류(☎ 등) 방지
                            clean_text = msg_text.replace('\n', ' ')
                            print(f"[{ts}] {clean_text}")
                        except:
                            print(f"[{ts}] (인코딩 문제로 출력할 수 없는 메시지)")
                        
                        logger.log(ts, msg_text)
            except Exception as e:
                # COMError 등 예외 발생 시 잠시 대기 후 루프 재개
                if "COMError" in str(type(e)) or "-2146233083" in str(e):
                    print("--- 스캔 중 UI 요소 유실 감지 (재시도 중...) ---")
                    target_control = None # 다음 루프에서 재탐색 유도
                else:
                    print(f"--- 예외 발생: {e} ---")
            
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n중단 요청 수신. 안전하게 종료합니다.")
        logger.close()

if __name__ == "__main__":
    run_scraper()
