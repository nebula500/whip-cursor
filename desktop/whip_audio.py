"""Crack playback. The recordings and the 95 ms separation match the Mac app."""

import shutil
import subprocess
import sys
import threading
import wave
from array import array
from pathlib import Path

from whip_sim import CrackStyle, CrackTiming

AUDIO_DIR = Path(__file__).resolve().parents[1] / "Source" / "Resources"


class CrackAudio:
    def __init__(self, directory=AUDIO_DIR):
        self.directory = Path(directory)
        self.timing = CrackTiming()
        self.available = all(
            (self.directory / f"crack-{style}.wav").is_file() for style in CrackStyle.ALL
        )
        self.note = "" if self.available else "Crack recordings were not found next to the source tree."
        if self.available and sys.platform.startswith("linux"):
            if not any(shutil.which(cmd) for cmd in ("paplay", "pw-play", "aplay")):
                self.available = False
                self.note = "Install paplay, pw-play, or aplay to hear the crack."

    def path_for(self, style):
        return self.directory / f"crack-{style}.wav"

    def play(self, prefs, mouse_click=False):
        if not prefs.sound or not self.available:
            return
        path = self.path_for(prefs.crack_style)
        if not path.is_file():
            return
        delay = 0.0
        if mouse_click:
            import time
            now = time.monotonic()
            delay = max(0.0, self.timing.next_start(now) - now)
        timer = threading.Timer(delay, self._play_file, args=(path, prefs.volume))
        timer.daemon = True
        timer.start()

    def _play_file(self, path, volume):
        try:
            if sys.platform == "win32":
                _play_windows(path, volume)
            else:
                _play_linux(path, volume)
        except Exception:
            return


def _scaled_pcm(path, volume):
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        rate = source.getframerate()
        width = source.getsampwidth()
        frames = source.readframes(source.getnframes())
    if width != 2:
        return None
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    gain = max(0.0, min(1.0, float(volume)))
    if gain < 0.999:
        for i, sample in enumerate(samples):
            samples[i] = int(max(-32767, min(32767, sample * gain)))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes(), channels, rate


def _play_windows(path, volume):
    import ctypes
    from ctypes import wintypes

    decoded = _scaled_pcm(path, volume)
    if decoded is None:
        return
    pcm, channels, rate = decoded
    winmm = ctypes.windll.winmm
    fmt = wintypes.WORD
    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", fmt), ("nChannels", fmt), ("nSamplesPerSec", wintypes.DWORD),
            ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", fmt),
            ("wBitsPerSample", fmt), ("cbSize", fmt),
        ]
    class WAVEHDR(ctypes.Structure):
        _fields_ = [
            ("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
            ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
            ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
            ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t),
        ]
    handle = ctypes.c_void_p()
    form = WAVEFORMATEX(
        1, channels, rate, rate * channels * 2, channels * 2, 16, 0
    )
    if winmm.waveOutOpen(ctypes.byref(handle), ctypes.c_uint(-1), ctypes.byref(form), 0, 0, 0) != 0:
        return
    buf = ctypes.create_string_buffer(pcm)
    header = WAVEHDR(ctypes.cast(buf, ctypes.c_void_p), len(pcm), 0, 0, 0, 0, None, 0)
    if winmm.waveOutPrepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header)) != 0:
        winmm.waveOutClose(handle)
        return
    winmm.waveOutWrite(handle, ctypes.byref(header), ctypes.sizeof(header))
    deadline = len(pcm) / (rate * channels * 2) + 0.2
    import time
    time.sleep(deadline)
    winmm.waveOutUnprepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
    winmm.waveOutClose(handle)


def _play_linux(path, volume):
    volume = max(0.0, min(1.0, float(volume)))
    if shutil.which("paplay"):
        cmd = ["paplay", f"--volume={int(volume * 65536)}", str(path)]
    elif shutil.which("pw-play"):
        cmd = ["pw-play", "--volume", f"{volume:.3f}", str(path)]
    elif shutil.which("aplay"):
        cmd = ["aplay", "-q", str(path)]
    else:
        return
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
