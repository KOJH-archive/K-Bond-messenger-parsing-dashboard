"""Small native, non-activating popup on the primary Windows work area's lower left."""
import ctypes
from ctypes import wintypes
import json
import queue
import sys
import threading
import tkinter as tk


def main():
    # Piped stdin otherwise uses the Windows locale (often CP949), while the sender writes UTF-8.
    sys.stdin.reconfigure(encoding='utf-8')
    inbox = queue.Queue(maxsize=20)
    def receive():
        try:
            for line in sys.stdin:
                try:
                    inbox.put_nowait(json.loads(line))
                except (ValueError, queue.Full):
                    pass
        finally:
            inbox.put(None)
    threading.Thread(target=receive, daemon=True).start()
    root = tk.Tk()
    root.withdraw()
    popups = []

    def dismiss(window):
        if window in popups:
            popups.remove(window)
            window.destroy()

    def show(message):
        for old in list(popups):
            dismiss(old)
        window = tk.Toplevel(root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes('-topmost', True)
        window.configure(bg='#f0a000')
        panel = tk.Frame(window, bg='#fffdf5', padx=16, pady=13)
        panel.pack(padx=(5, 1), pady=1, fill='both', expand=True)
        tk.Button(panel, text='×', command=lambda: dismiss(window), bg='#fffdf5', relief='flat', takefocus=False).pack(anchor='e')
        tk.Label(panel, text=str(message.get('title', 'K-Bond'))[:140], font=('맑은 고딕', 11, 'bold'),
                 bg='#fffdf5', fg='#825500', wraplength=370, justify='left').pack(anchor='w')
        tk.Label(panel, text=str(message.get('content', ''))[:350], font=('맑은 고딕', 10),
                 bg='#fffdf5', fg='#273449', wraplength=370, justify='left').pack(anchor='w', pady=8)
        tk.Label(panel, text=str(message.get('detail', ''))[:140], font=('맑은 고딕', 8),
                 bg='#fffdf5', fg='#657187', wraplength=370, justify='left').pack(anchor='w')
        window.update_idletasks()
        area = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
        width, height = 420, window.winfo_reqheight()
        x, y = area.left + 16, max(area.top, area.bottom - height - 16)
        window.geometry(f'{width}x{height}+{x}+{y}')
        # Native non-activation keeps typing focus in the messenger/trading application.
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(window.winfo_id())
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)
        window.deiconify()
        popups.append(window)
        window.after(12000, lambda: dismiss(window))

    def drain():
        try:
            while True:
                message = inbox.get_nowait()
                if message is None:
                    root.destroy()
                    return
                show(message)
        except queue.Empty:
            pass
        root.after(100, drain)
    root.after(100, drain)
    root.mainloop()


if __name__ == '__main__':
    main()
