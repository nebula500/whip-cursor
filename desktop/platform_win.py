"""Windows overlay: color-key transparency, click-through, global cursor hide."""

import ctypes
import threading
from ctypes import wintypes

KEY_COLOR = "#010203"
KEY_COLORREF = 0x00030201  # COLORREF is 0x00BBGGRR

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_SHIFT = 0x0004
VK_W = 0x57
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
        ("lPrivate", wintypes.DWORD),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class WindowsPlatform:
    name = "windows"

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self._cursor_hidden = False
        self._prepared = False
        self._hotkey_available = False
        self._hotkey_flag = threading.Event()
        self._hotkey_thread_id = None
        self._setup_hotkey()

    def supports_overlay(self):
        return True

    def status_note(self):
        if self._hotkey_available:
            return ""
        return "Alt Shift W is already in use. Pause from the whip button or Settings instead."

    def hotkey_available(self):
        return self._hotkey_available

    def screen_bounds(self):
        x = self.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = self.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = self.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = self.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return int(x), int(y), int(w), int(h)

    def cursor(self):
        point = _POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            return 0, 0
        return int(point.x), int(point.y)

    def buttons(self):
        left = bool(self.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        right = bool(self.user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)
        return left, right

    def prepare_overlay(self, window):
        window.update_idletasks()
        hwnd = self._top_hwnd(window)
        if not hwnd:
            return False
        get_long, set_long = self._long_funcs()
        style = get_long(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        set_long(hwnd, GWL_EXSTYLE, style)
        ok = self.user32.SetLayeredWindowAttributes(hwnd, KEY_COLORREF, 0, LWA_COLORKEY)
        self.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self._prepared = bool(ok)
        return self._prepared

    def raise_overlay(self, window):
        hwnd = self._top_hwnd(window)
        if hwnd:
            self.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def update_shape(self, window, strokes, origin_x, top_y):
        return

    def hide_cursor(self):
        if self._cursor_hidden:
            return True
        while self.user32.ShowCursor(False) >= 0:
            pass
        self._cursor_hidden = True
        return True

    def show_cursor(self):
        if not self._cursor_hidden:
            return
        while self.user32.ShowCursor(True) < 0:
            pass
        self._cursor_hidden = False

    def consume_pause(self):
        if self._hotkey_flag.is_set():
            self._hotkey_flag.clear()
            return True
        return False

    def shutdown(self):
        self.show_cursor()
        if self._hotkey_thread_id:
            self.user32.PostThreadMessageW(self._hotkey_thread_id, WM_QUIT, 0, 0)

    def _top_hwnd(self, window):
        try:
            hwnd = int(window.winfo_id())
        except Exception:
            return 0
        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        name = ctypes.create_unicode_buffer(64)
        for _ in range(4):
            self.user32.GetClassNameW(hwnd, name, 64)
            if name.value == "TkTopLevel":
                return hwnd
            parent = self.user32.GetParent(hwnd)
            if not parent:
                return hwnd
            hwnd = parent
        return hwnd

    def _long_funcs(self):
        try:
            get_long = self.user32.GetWindowLongPtrW
            set_long = self.user32.SetWindowLongPtrW
            get_long.restype = ctypes.c_ssize_t
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            set_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            return get_long, set_long
        except AttributeError:
            get_long = self.user32.GetWindowLongW
            set_long = self.user32.SetWindowLongW
            get_long.restype = ctypes.c_long
            set_long.restype = ctypes.c_long
            return get_long, set_long

    def _setup_hotkey(self):
        def loop():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._hotkey_thread_id = kernel32.GetCurrentThreadId()
            if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_SHIFT, VK_W):
                self._hotkey_available = False
                return
            self._hotkey_available = True
            msg = _MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self._hotkey_flag.set()
            user32.UnregisterHotKey(None, 1)

        thread = threading.Thread(target=loop, name="whip-hotkey", daemon=True)
        thread.start()
        for _ in range(50):
            if self._hotkey_available or self._hotkey_thread_id:
                if self._hotkey_available or not thread.is_alive():
                    break
            thread.join(0.02)
