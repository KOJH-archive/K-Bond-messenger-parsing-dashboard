import uiautomation as auto
import sys

# 윈도우 UI 트리를 탐색하는 도구입니다.
# K-Bond의 내부 컨트롤 ID를 찾기 위해 사용하세요.

def list_windows():
    print("현재 실행 중인 모든 창 목록을 출력합니다...")
    for win in auto.GetRootControl().GetChildren():
        try:
            name = win.Name
            clean_name = name.replace('\u200b', '[ZWS]')
            print(f"이름: {clean_name}, 클래스: {win.ClassName}, Hex: {name.encode('utf-16').hex()}")
        except:
            pass

def explore_window(window_name):
    win = auto.WindowControl(searchDepth=1, Name=window_name)
    if not win.Exists(0):
        print(f"'{window_name}' 창을 찾을 수 없습니다.")
        return

    print(f"창 탐색 중: {win.Name}")
    dump_tree(win, 1)

def dump_tree(control, depth):
    indent = "  " * depth
    for child in control.GetChildren():
        print(f"{indent}이름: {child.Name}, 타입: {child.ControlTypeName}, ID: {child.AutomationId}, 클래스: {child.ClassName}")
        if depth < 3: # 너무 깊게 탐색하지 않도록 제한
            dump_tree(child, depth + 1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        list_windows()
        print("\n사용법: python ui_explorer.py \"탐색할 창 이름\"")
    else:
        explore_window(sys.argv[1])
