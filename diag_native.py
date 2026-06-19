import ctypes
import ctypes.wintypes
import time
import uiautomation as auto
import re
import sys

# Windows API 정의
User32 = ctypes.WinDLL('user32', use_last_error=True)
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E

def get_window_text_native(hwnd):
    try:
        length = User32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            User32.SendMessageW(hwnd, WM_GETTEXT, length + 1, ctypes.byref(buffer))
            return buffer.value
    except:
        pass
    return ""

def diag_kbond_native():
    print("\n" + "="*50)
    print("🔍 [필독] K-Bond 실시간 데이터 위치 추적기")
    print("="*50)
    
    try:
        # 1. K-Bond 창 찾기 (더 유연하게)
        kbond_window = None
        for win in auto.GetRootControl().GetChildren():
            try:
                name = win.Name or ""
                if "[채권]" in name or "블커본드" in name:
                    kbond_window = win
                    break
            except: continue
                
        if not kbond_window:
            print("❌ 오류: K-Bond 창을 찾을 수 없습니다. 메신저가 켜져 있는지 확인하세요.")
            return

        print(f"✅ 대상 창 발견: {kbond_window.Name}")
        print("모든 구역을 뒤져서 15시 대화를 찾고 있습니다. 잠시만 기다려 주세요...")
        print("-" * 50)
        
        found_any = False
        
        # 2. 모든 자식 컨트롤 탐색
        def walk_children(control, depth=0):
            nonlocal found_any
            if depth > 12: return
            
            try:
                hwnd = control.NativeWindowHandle
                if hwnd:
                    text = get_window_text_native(hwnd)
                    if text and len(text.strip()) > 5:
                        times = re.findall(r"(\d{1,2}:\d{1,2}:\d{1,2})", text)
                        if times:
                            latest_time = max(times)
                            # 14시 또는 15시 데이터가 발견되었는지 강조
                            star = "⭐⭐⭐ [발견!]" if "14:" in latest_time or "15:" in latest_time else ""
                            
                            print(f"[{depth}] HWND: {hwnd} | Class: {control.ClassName}")
                            print(f"    - 현재 확인된 시간: {latest_time} {star}")
                            if star:
                                print(f"    - 내용 샘플: {text[:80].replace('\n', ' ')}...")
                            print("-" * 30)
                            found_any = True
                
                for child in control.GetChildren():
                    walk_children(child, depth + 1)
            except: pass

        walk_children(kbond_window)
        
        if not found_any:
            print("⚠️ 어떠한 실시간 정보도 찾지 못했습니다. K-Bond의 보안 설정이나 구조가 특이할 수 있습니다.")
        else:
            print("\n위 리스트에서 ⭐⭐⭐ 표시가 된 HWND 번호를 알려주시면 바로 해결이 가능합니다!")

    except Exception as e:
        print(f"❌ 런타임 에러 발생: {e}")

    print("\n" + "="*50)
    input("프로그램이 종료되었습니다. 결과를 확인하신 후 Enter를 누르세요...")

if __name__ == "__main__":
    diag_kbond_native()
