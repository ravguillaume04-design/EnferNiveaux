import time
import threading
from pynput import keyboard, mouse
from recorder import deserialize_key


class Replayer:
    def __init__(self):
        self._kb = keyboard.Controller()
        self._mouse = mouse.Controller()
        self._running = False
        self._thread = None

    @property
    def is_running(self):
        return self._running

    def start(self, events, loop=True, on_cycle=None):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(events, loop, on_cycle),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------------ #
    #  Internal replay loop                                                #
    # ------------------------------------------------------------------ #

    def _run(self, events, loop, on_cycle):
        cycle = 0
        while self._running:
            cycle += 1
            if on_cycle:
                on_cycle(cycle)
            self._play_once(events)
            if not loop:
                self._running = False

    def _play_once(self, events):
        pressed_keys = set()
        pressed_buttons = set()

        start = time.perf_counter()
        for event in events:
            if not self._running:
                break
            self._wait_until(start + event["t"])
            if not self._running:
                break
            self._execute(event, pressed_keys, pressed_buttons)

        # Release anything left pressed at end of cycle
        for key in list(pressed_keys):
            try:
                self._kb.release(key)
            except Exception:
                pass
        for btn in list(pressed_buttons):
            try:
                self._mouse.release(btn)
            except Exception:
                pass

    def _wait_until(self, target):
        while self._running:
            remaining = target - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.02))

    def _execute(self, event, pressed_keys, pressed_buttons):
        etype = event["type"]
        try:
            if etype == "key_press":
                key = deserialize_key(event["key"])
                if key:
                    self._kb.press(key)
                    pressed_keys.add(key)
            elif etype == "key_release":
                key = deserialize_key(event["key"])
                if key:
                    self._kb.release(key)
                    pressed_keys.discard(key)
            elif etype == "mouse_move":
                self._mouse.position = (event["x"], event["y"])
            elif etype == "mouse_click":
                btn = _parse_button(event["button"])
                if event["pressed"]:
                    self._mouse.press(btn)
                    pressed_buttons.add(btn)
                else:
                    self._mouse.release(btn)
                    pressed_buttons.discard(btn)
            elif etype == "mouse_scroll":
                self._mouse.scroll(event["dx"], event["dy"])
        except Exception:
            pass


def _parse_button(btn_str):
    if "right" in btn_str:
        return mouse.Button.right
    if "middle" in btn_str:
        return mouse.Button.middle
    return mouse.Button.left
