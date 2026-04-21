import time
import json
import threading
from pynput import keyboard, mouse

HOTKEYS = {keyboard.Key.f9, keyboard.Key.f10, keyboard.Key.f11}
MOUSE_THROTTLE = 0.05  # 50ms between mouse move events


class Recorder:
    def __init__(self, record_mouse=True):
        self.events = []
        self.is_recording = False
        self.record_mouse = record_mouse
        self._start_time = None
        self._kb_listener = None
        self._mouse_listener = None
        self._lock = threading.Lock()
        self._last_mouse_move = 0.0

    def start(self):
        with self._lock:
            self.events = []
            self._start_time = time.perf_counter()
            self._last_mouse_move = 0.0
            self.is_recording = True

        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            suppress=False,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self):
        with self._lock:
            self.is_recording = False
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

    def save(self, filepath):
        with self._lock:
            data = list(self.events)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            self.events = data

    # ------------------------------------------------------------------ #
    #  Internal listeners                                                   #
    # ------------------------------------------------------------------ #

    def _timestamp(self):
        return time.perf_counter() - self._start_time

    def _on_key_press(self, key):
        if key in HOTKEYS:
            return
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "key_press",
                "t": self._timestamp(),
                "key": _serialize_key(key),
            })

    def _on_key_release(self, key):
        if key in HOTKEYS:
            return
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "key_release",
                "t": self._timestamp(),
                "key": _serialize_key(key),
            })

    def _on_mouse_move(self, x, y):
        if not self.is_recording or not self.record_mouse:
            return
        now = time.perf_counter()
        if now - self._last_mouse_move < MOUSE_THROTTLE:
            return
        self._last_mouse_move = now
        with self._lock:
            self.events.append({
                "type": "mouse_move",
                "t": self._timestamp(),
                "x": x,
                "y": y,
            })

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "mouse_click",
                "t": self._timestamp(),
                "x": x,
                "y": y,
                "button": str(button),
                "pressed": pressed,
            })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "mouse_scroll",
                "t": self._timestamp(),
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
            })


# ------------------------------------------------------------------ #
#  Key serialization helpers                                           #
# ------------------------------------------------------------------ #

def _serialize_key(key):
    if isinstance(key, keyboard.Key):
        return {"t": "special", "v": key.name}
    if hasattr(key, "char") and key.char is not None:
        return {"t": "char", "v": key.char, "vk": getattr(key, "vk", None)}
    if hasattr(key, "vk") and key.vk is not None:
        return {"t": "vk", "v": key.vk}
    return {"t": "str", "v": str(key)}


def deserialize_key(key_data):
    t = key_data.get("t")
    v = key_data.get("v")
    try:
        if t == "special":
            return keyboard.Key[v]
        if t == "char":
            return keyboard.KeyCode.from_char(v)
        if t == "vk":
            return keyboard.KeyCode.from_vk(v)
    except (KeyError, ValueError):
        pass
    return None
