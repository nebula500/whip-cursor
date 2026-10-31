"""Settings window, preview, and the Windows/Linux desktop whip.

Physics and the settings ranges are the macOS ones. The pointer is only hidden
while the whip is on, and clicks are observed rather than swallowed.
"""

import math
import sys
import time
import tkinter as tk
from tkinter import colorchooser

from whip_audio import CrackAudio
from whip_draw import paint_tk, whip_strokes
from whip_prefs import Preferences
from whip_sim import (
    LENGTH_MAX,
    LENGTH_MIN,
    SWATCHES,
    THICKNESS_MAX,
    THICKNESS_MIN,
    CrackStyle,
    HandleShape,
    Point,
    WhipGesture,
    WhipSimulation,
    clamped,
)

BG = "#1b1d21"
PANEL = "#1b1d21"
PREVIEW_BG = "#131618"
INK = "#f4f1ea"
MUTED = "#9aa3ad"
KEY = "#010203"
KEY_BACKDROP = (1 / 255, 2 / 255, 3 / 255)
PREVIEW_BACKDROP = (0.075, 0.085, 0.095)


def rgb_hex(color):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c * 255)))) for c in color))


def stroke_window(strokes):
    xs, ys = [], []
    for stroke in strokes:
        kind = stroke[0]
        if kind == "line":
            xs.extend((stroke[1], stroke[3]))
            ys.extend((stroke[2], stroke[4]))
        elif kind == "fill":
            for x, y in stroke[1]:
                xs.append(x)
                ys.append(y)
        elif kind in ("dot", "arc"):
            radius = stroke[3]
            xs.extend((stroke[1] - radius, stroke[1] + radius))
            ys.extend((stroke[2] - radius, stroke[2] + radius))
    if not xs:
        return None
    pad = 32
    origin_x = math.floor(min(xs) - pad)
    top = math.ceil(max(ys) + pad)
    right = math.ceil(max(xs) + pad)
    bottom = math.floor(min(ys) - pad)
    return origin_x, top, max(1, right - origin_x), max(1, top - bottom)


class WhipApp:
    def __init__(self, preview_only=False):
        self.preview_only = preview_only
        self.prefs = Preferences()
        self.prefs.load()
        self.audio = CrackAudio()
        self.preview_sim = WhipSimulation()
        self.preview_gesture = WhipGesture()
        self.desktop_sim = WhipSimulation()
        self.desktop_gesture = WhipGesture()
        self.preview_inside = False
        self.preview_target = Point(190, 140)
        self.preview_time = 0.0
        self.previous_load = self.prefs.load_mode
        self.desktop_buttons = (False, False)
        self.menu_open = False
        self._loading = False
        self._overlay_ready = False
        self.platform = None if preview_only else self._make_platform()
        if self.platform is not None:
            self.prefs.pause_shortcut_available = self.platform.hotkey_available()
            self.prefs.replacement_available = self.platform.supports_overlay()

        self.root = tk.Tk()
        self.root.title("Whip Cursor")
        self.root.configure(bg=BG)
        self.root.minsize(450, 640)
        self.mono = self._font(10, mono=True)
        self.ui = self._font(12)
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close_settings)
        self.root.after(16, self._tick)

    def _font(self, size, mono=False, bold=False):
        families = ("Consolas", "Menlo", "DejaVu Sans Mono") if mono else ("Segoe UI", "Helvetica", "DejaVu Sans")
        weight = "bold" if bold else "normal"
        return (families[0], size, weight)

    def _make_platform(self):
        if sys.platform == "win32":
            from platform_win import WindowsPlatform
            return WindowsPlatform()
        if sys.platform.startswith("linux"):
            from platform_linux import LinuxPlatform
            return LinuxPlatform()
        return None

    def _build(self):
        self._loading = True
        outer = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        outer.pack(fill="both", expand=True)
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        self.kicker = tk.Label(titles, text="WHIP", fg=rgb_hex(self.prefs.color), bg=BG, font=self._font(11, mono=True, bold=True))
        self.kicker.pack(anchor="w")
        tk.Label(titles, text="A little snap.", fg=INK, bg=BG, font=self._font(28, bold=True)).pack(anchor="w")
        tk.Label(titles, text="Give your cursor a wild side.", fg=MUTED, bg=BG, font=self.ui).pack(anchor="w", pady=(2, 0))
        self.live = tk.Label(head, text="PAUSED", fg=INK, bg="#2a3036", padx=10, pady=4, font=self._font(10, mono=True, bold=True))
        self.live.pack(side="right")

        self.preview = tk.Canvas(outer, width=394, height=220, bg=PREVIEW_BG, highlightthickness=1, highlightbackground="#2a3036", cursor="none")
        self.preview.pack(fill="x", pady=(16, 4))
        self.preview.bind("<Map>", lambda _e: self._draw_dots())
        self.preview.bind("<Configure>", lambda _e: self._draw_dots())
        self.preview.bind("<Enter>", self._preview_enter)
        self.preview.bind("<Leave>", self._preview_leave)
        self.preview.bind("<Motion>", self._preview_move)
        self.preview.bind("<ButtonPress-1>", lambda e: self._preview_down(e, 0))
        self.preview.bind("<ButtonRelease-1>", lambda e: self._preview_up(e, 0))
        self.preview.bind("<B1-Motion>", self._preview_move)
        if sys.platform == "darwin":
            self.preview.bind("<ButtonPress-2>", lambda e: self._preview_down(e, 1))
            self.preview.bind("<ButtonRelease-2>", lambda e: self._preview_up(e, 1))
            self.preview.bind("<B2-Motion>", self._preview_move)
        self.preview.bind("<ButtonPress-3>", lambda e: self._preview_down(e, 1))
        self.preview.bind("<ButtonRelease-3>", lambda e: self._preview_up(e, 1))
        self.preview.bind("<B3-Motion>", self._preview_move)
        self.hint = tk.Label(outer, fg="#8e98a3", bg=BG, font=self._font(11))
        self.hint.pack(anchor="w", pady=(0, 12))

        section = tk.Frame(outer, bg=BG)
        section.pack(fill="x")
        tk.Label(section, text="MAKE IT YOURS", fg=MUTED, bg=BG, font=self._font(10, mono=True, bold=True)).pack(side="left")
        tk.Button(section, text="Custom color", command=self._pick_color, bg=BG, fg=INK, activebackground="#2a3036", activeforeground=INK, relief="flat", font=self._font(11)).pack(side="right")
        swatches = tk.Frame(outer, bg=BG)
        swatches.pack(fill="x", pady=(10, 8))
        self.swatch_widgets = []
        for name, color in SWATCHES:
            box = tk.Frame(swatches, bg=BG, highlightthickness=2, highlightbackground=BG)
            chip = tk.Frame(box, width=26, height=26, bg=rgb_hex(color))
            chip.pack(padx=3, pady=3)
            chip.pack_propagate(False)
            box.pack(side="left", padx=(0, 8))
            for widget in (box, chip):
                widget.bind("<Button-1>", lambda _e, color=color: self._set_color(color))
            box.tooltip_name = name
            self.swatch_widgets.append((color, box))

        self.length_scale, self.length_readout = self._slider(outer, "Whip length", LENGTH_MIN, LENGTH_MAX, self.prefs.length, 1, self._on_length)
        self.thick_scale, self.thick_readout = self._slider(outer, "Thickness", THICKNESS_MIN, THICKNESS_MAX, self.prefs.thickness, 0.05, self._on_thickness)
        self._on_length(self.prefs.length)
        self._on_thickness(self.prefs.thickness)

        handles = tk.Frame(outer, bg=BG)
        handles.pack(fill="x", pady=(8, 4))
        tk.Label(handles, text="Handle", fg=INK, bg=BG, font=self.ui, width=10, anchor="w").pack(side="left")
        self.handle_buttons = {}
        for shape in HandleShape.ALL:
            button = tk.Button(
                handles, text=HandleShape.TITLES[shape], relief="flat",
                command=lambda shape=shape: self._set_handle(shape), font=self._font(11), padx=8,
            )
            button.pack(side="left", padx=(0, 4))
            self.handle_buttons[shape] = button

        self.load_var = tk.BooleanVar(value=self.prefs.load_mode)
        self.replace_var = tk.BooleanVar(value=self.prefs.replace_pointer)
        self.sound_var = tk.BooleanVar(value=self.prefs.sound)
        tk.Checkbutton(outer, text="Replace system pointer", variable=self.replace_var, command=self._on_replace, bg=BG, fg=INK, selectcolor="#2a3036", activebackground=BG, activeforeground=INK, font=self.ui).pack(anchor="w", pady=(8, 0))
        self.replace_note = tk.Label(outer, fg=MUTED, bg=BG, font=self._font(10), wraplength=390, justify="left")
        self.replace_note.pack(anchor="w")
        tk.Checkbutton(outer, text="Hold to load the whip", variable=self.load_var, command=self._on_load, bg=BG, fg=INK, selectcolor="#2a3036", activebackground=BG, activeforeground=INK, font=self.ui).pack(anchor="w", pady=(6, 0))
        self.load_note = tk.Label(outer, fg=MUTED, bg=BG, font=self._font(10), wraplength=390, justify="left")
        self.load_note.pack(anchor="w")

        tk.Frame(outer, bg="#2c3238", height=1).pack(fill="x", pady=12)
        sound_row = tk.Frame(outer, bg=BG)
        sound_row.pack(fill="x")
        tk.Label(sound_row, text="Crack on click", fg=INK, bg=BG, font=self._font(12, bold=True)).pack(side="left")
        tk.Checkbutton(sound_row, variable=self.sound_var, command=self._on_sound, bg=BG, fg=INK, selectcolor="#2a3036", activebackground=BG).pack(side="right")
        pick = tk.Frame(outer, bg=BG)
        pick.pack(fill="x", pady=(8, 0))
        tk.Label(pick, text="Sound", fg=INK, bg=BG, font=self.ui, width=8, anchor="w").pack(side="left")
        self.sound_var_name = tk.StringVar(value=CrackStyle.TITLES[self.prefs.crack_style])
        menu = tk.OptionMenu(pick, self.sound_var_name, *[CrackStyle.TITLES[s] for s in CrackStyle.ALL], command=self._on_style)
        menu.configure(bg="#2a3036", fg=INK, highlightthickness=0, font=self._font(11))
        menu.pack(side="left")
        tk.Button(pick, text="Preview", command=lambda: self.audio.play(self.prefs), bg="#2a3036", fg=INK, relief="flat", font=self._font(11)).pack(side="left", padx=8)
        self.sound_detail = tk.Label(outer, fg=MUTED, bg=BG, font=self._font(10), wraplength=390, justify="left")
        self.sound_detail.pack(anchor="w", pady=(4, 0))
        self.volume_scale, _ = self._slider(outer, "Volume", 0, 1, self.prefs.volume, 0.01, self._on_volume, readout=False)
        tk.Button(outer, text="Test", command=lambda: self.audio.play(self.prefs), bg="#2a3036", fg=INK, relief="flat", font=self._font(11)).pack(anchor="e")

        self.toggle = tk.Button(outer, command=self._toggle, relief="flat", font=self._font(13, bold=True), pady=10)
        self.toggle.pack(fill="x", pady=(16, 8))
        self.footer = tk.Label(outer, fg=MUTED, bg=BG, font=self._font(10), wraplength=390, justify="center")
        self.footer.pack()
        self.audio_note = tk.Label(outer, fg=MUTED, bg=BG, font=self._font(10), wraplength=390, justify="center")
        self.audio_note.pack(pady=(4, 0))
        if self.audio.note:
            self.audio_note.configure(text=self.audio.note)

        self._loading = False
        self._refresh_chrome()
        if not self.preview_only:
            self._build_overlay()
            self._build_pill()

    def _slider(self, parent, label, lo, hi, value, resolution, command, readout=True):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, fg=INK, bg=BG, font=self.ui, width=12, anchor="w").pack(side="left")
        scale = tk.Scale(
            row, from_=lo, to=hi, resolution=resolution, orient="horizontal",
            showvalue=False, bg=BG, fg=INK, troughcolor="#2a3036", highlightthickness=0,
            activebackground=rgb_hex(self.prefs.color), command=command, length=230,
        )
        scale.set(value)
        scale.pack(side="left", fill="x", expand=True)
        text = tk.Label(row, fg=MUTED, bg=BG, font=self.mono, width=5, anchor="e")
        if readout:
            text.pack(side="right")
        return scale, text

    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg=KEY)
        try:
            self.overlay.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            self.overlay.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.overlay_canvas = tk.Canvas(self.overlay, bg=KEY, highlightthickness=0, bd=0)
        self.overlay_canvas.pack(fill="both", expand=True)
        self.overlay.withdraw()

    def _build_pill(self):
        self.pill = tk.Toplevel(self.root)
        self.pill.overrideredirect(True)
        self.pill.configure(bg="#242a31")
        try:
            self.pill.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.pill_label = tk.Label(self.pill, text="WHIP OFF", fg=INK, bg="#242a31", font=self._font(10, mono=True, bold=True), padx=14, pady=8)
        self.pill_label.pack()
        self.menu = tk.Menu(self.pill, tearoff=0)
        self.menu.add_command(label="Settings…", command=self.show_settings)
        self.menu.add_command(label="Pause whip", command=self._menu_primary)
        self.menu.add_separator()
        self.menu.add_command(label="Quit Whip Cursor", command=self.quit)
        self.pill_label.bind("<Button-1>", lambda _e: self._toggle())
        self.pill_label.bind("<Button-3>", self._post_menu)
        if sys.platform == "darwin":
            self.pill_label.bind("<Button-2>", self._post_menu)
        self.menu.bind("<Unmap>", lambda _e: self._set_menu_open(False))
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        self.pill.geometry(f"+{max(12, screen_w - 150)}+12")

    def _draw_dots(self):
        self.preview.delete("dots")
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        for x in range(16, max(16, width), 20):
            for y in range(16, max(16, height), 20):
                self.preview.create_oval(x, y, x + 1.5, y + 1.5, fill="#ffffff", outline="", stipple="gray25", tags="dots")

    def _preview_point(self, event):
        return Point(event.x, self.preview.winfo_height() - event.y)

    def _preview_enter(self, event):
        self.preview_inside = True
        self._preview_move(event)

    def _preview_leave(self, _event):
        self.preview_inside = False
        self.preview_gesture.cancel()

    def _preview_move(self, event):
        self.preview_target = self._preview_point(event)

    def _preview_down(self, event, button):
        self._preview_move(event)
        self._sync_load_mode(self.preview_gesture)
        if self.preview_gesture.press(button, time.monotonic(), self.prefs.load_mode):
            self._crack(self.preview_sim, 0, preview=True)

    def _preview_up(self, event, button):
        self._preview_move(event)
        charge = self.preview_gesture.release(button, time.monotonic(), self.prefs.load_mode)
        if charge is not None:
            self._crack(self.preview_sim, charge, preview=True)

    def _crack(self, simulation, charge, preview=False):
        point = self.preview_target if preview else self._desktop_point()
        length = self.prefs.length * (0.72 if preview else 1)
        if point is None:
            return
        simulation.step(point, length)
        simulation.crack(1 + charge * 0.65)

    def _tick(self):
        try:
            self.root.after(16, self._tick)
            self._tick_preview()
            if not self.preview_only:
                self._tick_desktop()
        except tk.TclError:
            return

    def _tick_preview(self):
        self.preview_time += 1 / 60
        width = max(self.preview.winfo_width(), 394)
        height = max(self.preview.winfo_height(), 220)
        if not self.preview_inside:
            self.preview_target = Point(
                width / 2 + math.sin(self.preview_time * 0.8) * 65,
                height - 32 + math.cos(self.preview_time) * 8,
            )
        self._sync_load_mode(self.preview_gesture)
        now = time.monotonic()
        length = self.prefs.length * 0.72
        self.preview_sim.step(
            self.preview_target, length,
            self.preview_gesture.charge(now, self.prefs.load_mode),
        )
        if self.preview_sim.take_pop():
            self.audio.play(self.prefs, mouse_click=True)
        strokes = whip_strokes(self.preview_sim, self.prefs.color, self.prefs.thickness, self.prefs.handle_shape)
        paint_tk(
            self.preview, strokes,
            lambda x: x, lambda y: height - y,
            PREVIEW_BACKDROP,
        )

    def _tick_desktop(self):
        if self.platform and self.platform.consume_pause() and self.prefs.enabled:
            self.pause()
        if not self.prefs.enabled or self.platform is None:
            self._hide_desktop()
            return
        sx, sy = self.platform.cursor()
        over = self.menu_open or self._over_controls(sx, sy)
        visible = (not over) and self._on_screen(sx, sy)
        if not visible:
            self._hide_desktop(keep_enabled=True)
            self.desktop_gesture.cancel()
            return
        self._poll_buttons(sx, sy)
        now = time.monotonic()
        point = Point(sx, -sy)
        self._sync_load_mode(self.desktop_gesture)
        self.desktop_sim.step(point, self.prefs.length, self.desktop_gesture.charge(now, self.prefs.load_mode))
        if self.desktop_sim.take_pop():
            self.audio.play(self.prefs, mouse_click=True)
        strokes = whip_strokes(self.desktop_sim, self.prefs.color, self.prefs.thickness, self.prefs.handle_shape)
        self._show_overlay(strokes)
        if self.prefs.replace_pointer and self.prefs.replacement_available:
            if not self.platform.hide_cursor():
                self.prefs.replacement_available = False
                self._refresh_chrome()
        else:
            self.platform.show_cursor()

    def _poll_buttons(self, sx, sy):
        left, right = self.platform.buttons()
        now = time.monotonic()
        current = (left, right)
        for index, down in enumerate(current):
            was = self.desktop_buttons[index]
            if down and not was:
                self.desktop_sim.step(Point(sx, -sy), self.prefs.length)
                if self.desktop_gesture.press(index, now, self.prefs.load_mode):
                    self.desktop_sim.crack(1)
            elif was and not down:
                charge = self.desktop_gesture.release(index, now, self.prefs.load_mode)
                if charge is not None:
                    self.desktop_sim.step(Point(sx, -sy), self.prefs.length)
                    self.desktop_sim.crack(1 + charge * 0.65)
        self.desktop_buttons = current

    def _show_overlay(self, strokes):
        box = stroke_window(strokes)
        if box is None:
            self.overlay.withdraw()
            return
        origin_x, top, width, height = box
        self.overlay.geometry(f"{width}x{height}+{origin_x}+{-top}")
        if not self.overlay.winfo_viewable():
            self.overlay.deiconify()
            self.overlay.update_idletasks()
            if self.platform and not self._overlay_ready:
                self._overlay_ready = self.platform.prepare_overlay(self.overlay)
        self.overlay_canvas.configure(width=width, height=height)
        paint_tk(
            self.overlay_canvas, strokes,
            lambda x, origin=origin_x: x - origin,
            lambda y, top_y=top: top_y - y,
            KEY_BACKDROP,
        )
        if self.platform:
            self.platform.update_shape(self.overlay, strokes, origin_x, top)
            self.platform.raise_overlay(self.overlay)

    def _hide_desktop(self, keep_enabled=False):
        if not keep_enabled:
            self.desktop_gesture.cancel()
            self.desktop_buttons = (False, False)
        if getattr(self, "overlay", None) is not None:
            self.overlay.withdraw()
        if self.platform:
            self.platform.show_cursor()

    def _desktop_point(self):
        if self.platform is None:
            return None
        sx, sy = self.platform.cursor()
        return Point(sx, -sy)

    def _over_controls(self, x, y):
        for widget in (self.root, getattr(self, "pill", None)):
            if widget is None or not widget.winfo_viewable():
                continue
            left, top = widget.winfo_rootx(), widget.winfo_rooty()
            if left <= x < left + widget.winfo_width() and top <= y < top + widget.winfo_height():
                return True
        return False

    def _on_screen(self, x, y):
        if self.platform is None:
            return False
        left, top, width, height = self.platform.screen_bounds()
        return left <= x < left + width and top <= y < top + height

    def _sync_load_mode(self, gesture):
        if self.previous_load != self.prefs.load_mode:
            gesture.cancel()
            self.previous_load = self.prefs.load_mode

    def _set_color(self, color):
        self.prefs.color = tuple(color)
        self.prefs.touch()
        self._refresh_chrome()

    def _pick_color(self):
        _rgb, chosen = colorchooser.askcolor(color=rgb_hex(self.prefs.color), parent=self.root, title="Whip color")
        if chosen:
            self._set_color(tuple(channel / 255 for channel in _rgb))

    def _set_handle(self, shape):
        self.prefs.handle_shape = shape
        self.prefs.touch()
        self._refresh_chrome()

    def _on_length(self, value):
        self.prefs.length = clamped(float(value), LENGTH_MIN, LENGTH_MAX)
        readout = getattr(self, "length_readout", None)
        if readout:
            readout.configure(text=str(int(round(self.prefs.length))))
        if not self._loading:
            self.prefs.touch()

    def _on_thickness(self, value):
        self.prefs.thickness = clamped(float(value), THICKNESS_MIN, THICKNESS_MAX)
        readout = getattr(self, "thick_readout", None)
        if readout:
            readout.configure(text=f"{int(round(self.prefs.thickness * 100))}%")
        if not self._loading:
            self.prefs.touch()

    def _on_volume(self, value):
        self.prefs.volume = clamped(float(value), 0, 1)
        if not self._loading:
            self.prefs.touch()

    def _on_replace(self):
        self.prefs.replace_pointer = bool(self.replace_var.get())
        self.prefs.touch()
        self._refresh_chrome()

    def _on_load(self):
        self.prefs.load_mode = bool(self.load_var.get())
        self.prefs.touch()
        self._refresh_chrome()

    def _on_sound(self):
        self.prefs.sound = bool(self.sound_var.get())
        self.prefs.touch()

    def _on_style(self, title):
        for style in CrackStyle.ALL:
            if CrackStyle.TITLES[style] == title:
                self.prefs.crack_style = style
                break
        self.prefs.touch()
        self.sound_detail.configure(text=CrackStyle.DETAILS[self.prefs.crack_style])

    def _toggle(self):
        self.prefs.enabled = not self.prefs.enabled
        if not self.prefs.enabled:
            self._hide_desktop()
        self._refresh_chrome()

    def _menu_primary(self):
        if self.prefs.enabled:
            self.pause()
        else:
            self._toggle()

    def pause(self):
        self.prefs.enabled = False
        self._hide_desktop()
        self._refresh_chrome()

    def show_settings(self):
        self.root.deiconify()
        self.root.lift()

    def _close_settings(self):
        if self.preview_only:
            self.quit()
        else:
            self.root.withdraw()

    def _post_menu(self, event):
        self.menu_open = True
        self.menu.entryconfigure(1, label="Pause whip" if self.prefs.enabled else "Enable whip")
        self.menu.tk_popup(event.x_root, event.y_root)

    def _set_menu_open(self, open_):
        self.menu_open = open_

    def _refresh_chrome(self):
        color = rgb_hex(self.prefs.color)
        self.kicker.configure(fg=color)
        self.live.configure(text="LIVE" if self.prefs.enabled else "PAUSED", fg="#d7ffb0" if self.prefs.enabled else INK)
        self.hint.configure(text="Hold to load. Release to crack." if self.prefs.load_mode else "Click to crack. Double-click for two.")
        self.load_note.configure(text="Hold either mouse button to coil the whip; release to crack." if self.prefs.load_mode else "Crack immediately on each left or right click.")
        self.sound_detail.configure(text=CrackStyle.DETAILS[self.prefs.crack_style])
        self.toggle.configure(
            text="Pause desktop whip" if self.prefs.enabled else "Unleash the whip",
            bg=color, fg="#1a120c", activebackground=color, activeforeground="#1a120c",
        )
        for swatch, box in self.swatch_widgets:
            selected = self.prefs.matches_swatch(swatch)
            box.configure(highlightbackground="#f4f1ea" if selected else BG)
        for shape, button in self.handle_buttons.items():
            chosen = shape == self.prefs.handle_shape
            button.configure(bg=color if chosen else "#2a3036", fg="#1a120c" if chosen else INK, activebackground=color)
        if getattr(self, "pill_label", None) is not None:
            self.pill_label.configure(text="WHIP ON" if self.prefs.enabled else "WHIP OFF", fg=color if self.prefs.enabled else INK)
        notes = []
        if self.preview_only:
            notes.append("macOS desktop whip is Whip Cursor.app. This window previews the shared settings.")
        elif self.platform is not None and not self.platform.supports_overlay():
            notes.append(self.platform.status_note() or "Desktop overlay is unavailable in this session.")
        elif self.prefs.replace_pointer and not self.prefs.replacement_available:
            notes.append("Replacement is unavailable here. The normal pointer stays visible.")
        if self.platform is not None and self.platform.status_note() and self.platform.supports_overlay():
            notes.append(self.platform.status_note())
        if not self.preview_only:
            if self.prefs.pause_shortcut_available:
                notes.append("Click the WHIP button to toggle. Right-click it for settings. Pause with Alt Shift W.")
            else:
                notes.append("Alt Shift W is already in use. Pause from the WHIP button or Settings instead.")
        self.replace_note.configure(text="")
        self.footer.configure(text=" ".join(notes))

    def quit(self):
        self.prefs.enabled = False
        self._hide_desktop()
        if self.platform:
            self.platform.shutdown()
        self.root.destroy()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    preview_only = sys.platform == "darwin" or "--preview" in argv
    if sys.platform == "darwin" and "--preview" not in argv and "--self-check-ui" not in argv:
        preview_only = True
    app = WhipApp(preview_only=preview_only or "--preview" in argv or sys.platform == "darwin")
    if "--self-check-ui" in argv:
        app.root.update_idletasks()
        app._draw_dots()
        app._tick_preview()
        app.root.destroy()
        print("PASS: settings window")
        return 0
    app.root.mainloop()
    return 0
