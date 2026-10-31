"""Linux/X11 overlay. The whip is a shaped, click-through window.

Wayland compositors do not allow this. An X11 session, including XWayland,
is required for the desktop whip. Settings and the preview still run without it.
"""

import ctypes
import os
import sys

KEY_COLOR = "#010203"
ShapeBounding = 0
ShapeInput = 2
ShapeSet = 0
Button1Mask = 1 << 8
Button3Mask = 1 << 10
ShiftMask = 1
Mod1Mask = 1 << 3
XK_W = 0x0057
XK_w = 0x0077


class _XineramaScreen(ctypes.Structure):
    _fields_ = [
        ("screen_number", ctypes.c_int),
        ("x_org", ctypes.c_short),
        ("y_org", ctypes.c_short),
        ("width", ctypes.c_short),
        ("height", ctypes.c_short),
    ]


class _XPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]


class LinuxPlatform:
    name = "linux"

    def __init__(self):
        self.x11 = None
        self.xext = None
        self.xfixes = None
        self.dpy = None
        self._cursor_hidden = False
        self._fixes_event = ctypes.c_int()
        self._fixes_error = ctypes.c_int()
        self._w_codes = ()
        self._hot_latched = False
        self.note = ""
        self._open()

    def supports_overlay(self):
        return self.dpy is not None

    def status_note(self):
        return self.note

    def hotkey_available(self):
        return self.dpy is not None

    def _open(self):
        if not os.environ.get("DISPLAY"):
            self.note = "The desktop whip needs an X11 session. Settings and the preview still work."
            return
        if os.environ.get("WAYLAND_DISPLAY"):
            self.note = "On Wayland, the whip covers XWayland windows. Native Wayland apps may keep the system pointer."
        try:
            self.x11 = ctypes.CDLL("libX11.so.6")
            self.xext = ctypes.CDLL("libXext.so.6")
            self.xfixes = ctypes.CDLL("libXfixes.so.6")
        except OSError:
            self.note = "libX11, libXext, and libXfixes are required for the desktop whip."
            return
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.dpy = self.x11.XOpenDisplay(None)
        if not self.dpy:
            self.note = "Could not open the X11 display."
            return
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XKeysymToKeycode.restype = ctypes.c_ubyte
        self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._w_codes = tuple(
            code for code in (
                self.x11.XKeysymToKeycode(self.dpy, XK_w),
                self.x11.XKeysymToKeycode(self.dpy, XK_W),
            ) if code
        )
        self.xfixes.XFixesQueryExtension.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
        ]
        self.xfixes.XFixesHideCursor.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.xfixes.XFixesShowCursor.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        if not self.xfixes.XFixesQueryExtension(self.dpy, ctypes.byref(self._fixes_event), ctypes.byref(self._fixes_error)):
            self.note = "The XFixes extension is missing, so the system pointer cannot be hidden."

    def screen_bounds(self):
        screens = self._xinerama()
        if screens:
            x0 = min(s[0] for s in screens)
            y0 = min(s[1] for s in screens)
            x1 = max(s[0] + s[2] for s in screens)
            y1 = max(s[1] + s[3] for s in screens)
            return x0, y0, x1 - x0, y1 - y0
        if not self.dpy:
            return 0, 0, 1280, 800
        return 0, 0, int(self.x11.XDisplayWidth(self.dpy, 0)), int(self.x11.XDisplayHeight(self.dpy, 0))

    def _xinerama(self):
        if not self.dpy:
            return []
        try:
            xinerama = ctypes.CDLL("libXinerama.so.1")
        except OSError:
            return []
        xinerama.XineramaQueryScreens.restype = ctypes.POINTER(_XineramaScreen)
        xinerama.XineramaQueryScreens.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        count = ctypes.c_int()
        info = xinerama.XineramaQueryScreens(self.dpy, ctypes.byref(count))
        if not info or count.value <= 0:
            return []
        screens = [(int(info[i].x_org), int(info[i].y_org), int(info[i].width), int(info[i].height)) for i in range(count.value)]
        self.x11.XFree(info)
        return screens

    def cursor(self):
        if not self.dpy:
            return 0, 0
        root = child = ctypes.c_ulong()
        root_x = root_y = win_x = win_y = ctypes.c_int()
        mask = ctypes.c_uint()
        self.x11.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.x11.XQueryPointer.restype = ctypes.c_int
        root_window = self.x11.XDefaultRootWindow(self.dpy)
        ok = self.x11.XQueryPointer(
            self.dpy, root_window, ctypes.byref(root), ctypes.byref(child),
            ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(win_x), ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        self._last_mask = int(mask.value) if ok else 0
        if not ok:
            return 0, 0
        return int(root_x.value), int(root_y.value)

    def buttons(self):
        self.cursor()
        mask = getattr(self, "_last_mask", 0)
        return bool(mask & Button1Mask), bool(mask & Button3Mask)

    def prepare_overlay(self, window):
        return self.dpy is not None

    def raise_overlay(self, window):
        if not self.dpy:
            return
        try:
            xid = int(window.winfo_id())
        except Exception:
            return
        self.x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XRaiseWindow(self.dpy, xid)
        self.x11.XFlush(self.dpy)

    def update_shape(self, window, strokes, origin_x, top_y):
        if not self.dpy:
            return
        window.update_idletasks()
        width = max(1, int(window.winfo_width()))
        height = max(1, int(window.winfo_height()))
        try:
            xid = int(window.winfo_id())
        except Exception:
            return
        self.x11.XCreatePixmap.restype = ctypes.c_ulong
        self.x11.XCreatePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        self.x11.XCreateGC.restype = ctypes.c_void_p
        self.x11.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        pixmap = self.x11.XCreatePixmap(self.dpy, xid, width, height, 1)
        gc = self.x11.XCreateGC(self.dpy, pixmap, 0, None)
        self.x11.XSetForeground.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XFillRectangle.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        self.x11.XSetForeground(self.dpy, gc, 0)
        self.x11.XFillRectangle(self.dpy, pixmap, gc, 0, 0, width, height)
        self.x11.XSetForeground(self.dpy, gc, 1)
        self.x11.XSetLineAttributes.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.x11.XDrawLine.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        for stroke in strokes:
            kind = stroke[0]
            if kind == "line":
                self.x11.XSetLineAttributes(self.dpy, gc, max(1, int(round(stroke[5]))), 0, 2, 2)
                self.x11.XDrawLine(
                    self.dpy, pixmap, gc,
                    int(round(stroke[1] - origin_x)), int(round(top_y - stroke[2])),
                    int(round(stroke[3] - origin_x)), int(round(top_y - stroke[4])),
                )
            elif kind in ("fill", "clip") and kind == "fill":
                pts = stroke[1]
                if len(pts) < 3:
                    continue
                array = (_XPoint * len(pts))()
                for i, (x, y) in enumerate(pts):
                    array[i].x = max(-32768, min(32767, int(round(x - origin_x))))
                    array[i].y = max(-32768, min(32767, int(round(top_y - y))))
                self.x11.XFillPolygon.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(_XPoint), ctypes.c_int, ctypes.c_int, ctypes.c_int]
                self.x11.XFillPolygon(self.dpy, pixmap, gc, array, len(pts), 0, 0)
            elif kind == "dot":
                radius = max(1, int(round(stroke[3])))
                cx = int(round(stroke[1] - origin_x))
                cy = int(round(top_y - stroke[2]))
                self.x11.XFillArc.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int]
                self.x11.XFillArc(self.dpy, pixmap, gc, cx - radius, cy - radius, radius * 2, radius * 2, 0, 360 * 64)
            elif kind == "arc":
                radius = max(1, int(round(stroke[3])))
                cx = int(round(stroke[1] - origin_x))
                cy = int(round(top_y - stroke[2]))
                self.x11.XSetLineAttributes(self.dpy, gc, max(2, int(round(stroke[6])) + 2), 0, 2, 2)
                self.x11.XDrawArc.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int]
                self.x11.XDrawArc(self.dpy, pixmap, gc, cx - radius, cy - radius, radius * 2, radius * 2, 0, 360 * 64)
        self.xext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
        self.xext.XShapeCombineMask(self.dpy, xid, ShapeBounding, 0, 0, pixmap, ShapeSet)
        self.x11.XCreateRegion.restype = ctypes.c_void_p
        self.x11.XCreateRegion.argtypes = []
        region = self.x11.XCreateRegion()
        self.xext.XShapeCombineRegion.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self.xext.XShapeCombineRegion(self.dpy, xid, ShapeInput, 0, 0, region, ShapeSet)
        self.x11.XDestroyRegion.argtypes = [ctypes.c_void_p]
        self.x11.XDestroyRegion(region)
        self.x11.XFreeGC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XFreeGC(self.dpy, gc)
        self.x11.XFreePixmap(self.dpy, pixmap)
        self.x11.XFlush(self.dpy)

    def hide_cursor(self):
        if self._cursor_hidden or not self.dpy:
            return self._cursor_hidden
        root = self.x11.XDefaultRootWindow(self.dpy)
        self.xfixes.XFixesHideCursor(self.dpy, root)
        self.x11.XFlush(self.dpy)
        self._cursor_hidden = True
        return True

    def show_cursor(self):
        if not self._cursor_hidden or not self.dpy:
            return
        root = self.x11.XDefaultRootWindow(self.dpy)
        self.xfixes.XFixesShowCursor(self.dpy, root)
        self.x11.XFlush(self.dpy)
        self._cursor_hidden = False

    def consume_pause(self):
        if not self.dpy or not self._w_codes:
            return False
        self.cursor()
        mask = getattr(self, "_last_mask", 0)
        keymap = (ctypes.c_char * 32)()
        self.x11.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.x11.XQueryKeymap(self.dpy, keymap)
        down = False
        for code in self._w_codes:
            byte = keymap[code // 8]
            value = byte[0] if isinstance(byte, (bytes, bytearray)) else byte
            if value & (1 << (code % 8)):
                down = True
                break
        pressed = bool(mask & ShiftMask) and bool(mask & Mod1Mask) and down
        if pressed and not self._hot_latched:
            self._hot_latched = True
            return True
        if not pressed:
            self._hot_latched = False
        return False

    def shutdown(self):
        self.show_cursor()
        if self.dpy:
            self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self.x11.XCloseDisplay(self.dpy)
            self.dpy = None


def running_on_linux():
    return sys.platform.startswith("linux")
