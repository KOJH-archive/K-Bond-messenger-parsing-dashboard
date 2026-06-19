import uiautomation as auto
import sys

def diag():
    print("K-Bond Diagnostic Start")
    target = None
    for win in auto.GetRootControl().GetChildren():
        try:
            name = win.Name.replace('\u200b', '')
            if "[채권]" in name and "블커본드" in name:
                target = win
                print(f"Found window: {name}")
                break
        except: continue
    
    if not target:
        print("Window not found!")
        return

    print(f"Dumping tree for: {target.Name}")
    with open("kbond_diag.txt", "w", encoding="utf-8") as f:
        f.write(f"Window: {target.Name}\n")
        f.write(f"Class: {target.ClassName}\n\n")
        
        def dump(control, depth):
            indent = "  " * depth
            try:
                name = (control.Name or "").replace('\u200b', '[ZWS]')
                line = f"{indent}Type: {control.ControlTypeName}, Name: {name}, ID: {control.AutomationId}, Class: {control.ClassName}\n"
                f.write(line)
                if depth < 10: # Deep search
                    for child in control.GetChildren():
                        dump(child, depth + 1)
            except: pass
        
        dump(target, 0)
    print("Diagnostic complete. Results in kbond_diag.txt")

if __name__ == "__main__":
    diag()
