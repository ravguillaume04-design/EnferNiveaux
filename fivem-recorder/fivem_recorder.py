import time
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from pynput import keyboard, mouse

# ------------------------------------------------------------------ #
#  Constantes                                                          #
# ------------------------------------------------------------------ #

HOTKEYS = {keyboard.Key.f9, keyboard.Key.f10, keyboard.Key.f11}
MOUSE_THROTTLE = 0.05  # 50ms entre chaque enregistrement de mouvement souris


# ------------------------------------------------------------------ #
#  Sérialisation des touches                                           #
# ------------------------------------------------------------------ #

def _serialize_key(key):
    if isinstance(key, keyboard.Key):
        return {"t": "special", "v": key.name}
    if hasattr(key, "char") and key.char is not None:
        return {"t": "char", "v": key.char}
    if hasattr(key, "vk") and key.vk is not None:
        return {"t": "vk", "v": key.vk}
    return None


def _deserialize_key(data):
    if data is None:
        return None
    try:
        t, v = data["t"], data["v"]
        if t == "special":
            return keyboard.Key[v]
        if t == "char":
            return keyboard.KeyCode.from_char(v)
        if t == "vk":
            return keyboard.KeyCode.from_vk(v)
    except Exception:
        pass
    return None


def _parse_button(s):
    if "right" in s:
        return mouse.Button.right
    if "middle" in s:
        return mouse.Button.middle
    return mouse.Button.left


# ------------------------------------------------------------------ #
#  Enregistreur                                                        #
# ------------------------------------------------------------------ #

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
        for l in (self._kb_listener, self._mouse_listener):
            if l:
                l.stop()
        self._kb_listener = None
        self._mouse_listener = None

    def save(self, path):
        with self._lock:
            data = list(self.events)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            self.events = data

    def _ts(self):
        return time.perf_counter() - self._start_time

    def _on_key_press(self, key):
        if key in HOTKEYS or not self.is_recording:
            return
        s = _serialize_key(key)
        if s:
            with self._lock:
                self.events.append({"type": "key_press", "t": self._ts(), "key": s})

    def _on_key_release(self, key):
        if key in HOTKEYS or not self.is_recording:
            return
        s = _serialize_key(key)
        if s:
            with self._lock:
                self.events.append({"type": "key_release", "t": self._ts(), "key": s})

    def _on_mouse_move(self, x, y):
        if not self.is_recording or not self.record_mouse:
            return
        now = time.perf_counter()
        if now - self._last_mouse_move < MOUSE_THROTTLE:
            return
        self._last_mouse_move = now
        with self._lock:
            self.events.append({"type": "mouse_move", "t": self._ts(), "x": x, "y": y})

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "mouse_click", "t": self._ts(),
                "x": x, "y": y, "button": str(button), "pressed": pressed,
            })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.is_recording:
            return
        with self._lock:
            self.events.append({
                "type": "mouse_scroll", "t": self._ts(),
                "x": x, "y": y, "dx": dx, "dy": dy,
            })


# ------------------------------------------------------------------ #
#  Replayer                                                            #
# ------------------------------------------------------------------ #

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
            target=self._run, args=(events, loop, on_cycle), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

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
        pressed_keys, pressed_buttons = set(), set()
        start = time.perf_counter()
        for ev in events:
            if not self._running:
                break
            self._wait_until(start + ev["t"])
            if not self._running:
                break
            self._execute(ev, pressed_keys, pressed_buttons)
        for k in list(pressed_keys):
            try:
                self._kb.release(k)
            except Exception:
                pass
        for b in list(pressed_buttons):
            try:
                self._mouse.release(b)
            except Exception:
                pass

    def _wait_until(self, target):
        while self._running:
            remaining = target - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.02))

    def _execute(self, ev, pressed_keys, pressed_buttons):
        t = ev["type"]
        try:
            if t == "key_press":
                k = _deserialize_key(ev["key"])
                if k:
                    self._kb.press(k)
                    pressed_keys.add(k)
            elif t == "key_release":
                k = _deserialize_key(ev["key"])
                if k:
                    self._kb.release(k)
                    pressed_keys.discard(k)
            elif t == "mouse_move":
                self._mouse.position = (ev["x"], ev["y"])
            elif t == "mouse_click":
                b = _parse_button(ev["button"])
                if ev["pressed"]:
                    self._mouse.press(b)
                    pressed_buttons.add(b)
                else:
                    self._mouse.release(b)
                    pressed_buttons.discard(b)
            elif t == "mouse_scroll":
                self._mouse.scroll(ev["dx"], ev["dy"])
        except Exception:
            pass


# ------------------------------------------------------------------ #
#  Interface graphique                                                 #
# ------------------------------------------------------------------ #

class App:
    IDLE = "idle"
    REC  = "recording"
    REP  = "replaying"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FiveM Recorder")
        self.root.resizable(False, False)

        self._mouse_var  = tk.BooleanVar(value=True)
        self._delay_var  = tk.IntVar(value=5)
        self._status_var = tk.StringVar(value="En attente")
        self._info_var   = tk.StringVar(value="")

        self.recorder = Recorder()
        self.replayer = Replayer()
        self._state   = self.IDLE
        self._cycles  = 0

        self._build_ui()
        self._start_hotkeys()

    # -- UI --------------------------------------------------------- #

    def _build_ui(self):
        P = dict(padx=10, pady=5)

        # Statut
        sf = tk.LabelFrame(self.root, text="Statut", **P)
        sf.pack(fill="x", **P)
        self._slabel = tk.Label(sf, textvariable=self._status_var,
                                font=("Helvetica", 13, "bold"), fg="gray")
        self._slabel.pack()
        tk.Label(sf, textvariable=self._info_var, fg="gray").pack()

        # Boutons
        cf = tk.LabelFrame(self.root, text="Contrôles", **P)
        cf.pack(fill="x", **P)
        self._rec_btn = tk.Button(cf, text="⏺  Enregistrer  (F9)",
                                  width=28, command=self.toggle_record)
        self._rec_btn.pack(pady=3)
        self._rep_btn = tk.Button(cf, text="▶  Rejouer en boucle  (F10)",
                                  width=28, command=self.toggle_replay, state="disabled")
        self._rep_btn.pack(pady=3)

        # Paramètres
        pf = tk.LabelFrame(self.root, text="Paramètres", **P)
        pf.pack(fill="x", **P)
        row = tk.Frame(pf)
        row.pack(fill="x", pady=2)
        tk.Label(row, text="Délai avant replay (s) :").pack(side="left")
        tk.Spinbox(row, from_=0, to=30, textvariable=self._delay_var,
                   width=4).pack(side="left", padx=5)
        tk.Checkbutton(pf, text="Enregistrer les mouvements de souris",
                       variable=self._mouse_var).pack(anchor="w", pady=2)

        # Fichier
        ff = tk.LabelFrame(self.root, text="Fichier", **P)
        ff.pack(fill="x", **P)
        row2 = tk.Frame(ff)
        row2.pack()
        tk.Button(row2, text="Sauvegarder", command=self.save).pack(side="left", padx=5)
        tk.Button(row2, text="Charger",     command=self.load).pack(side="left", padx=5)

        # Aide
        hf = tk.LabelFrame(self.root, text="Raccourcis globaux", **P)
        hf.pack(fill="x", **P)
        tk.Label(hf, text=(
            "F9   —  Démarrer / Arrêter l'enregistrement\n"
            "F10  —  Démarrer / Arrêter le replay\n"
            "F11  —  Arrêt d'urgence"
        ), justify="left", font=("Courier", 9)).pack(anchor="w")

    # -- Hotkeys ---------------------------------------------------- #

    def _start_hotkeys(self):
        def on_press(key):
            if key == keyboard.Key.f9:
                self.root.after(0, self.toggle_record)
            elif key == keyboard.Key.f10:
                self.root.after(0, self.toggle_replay)
            elif key == keyboard.Key.f11:
                self.root.after(0, self.emergency_stop)

        self._hk = keyboard.Listener(on_press=on_press, suppress=False)
        self._hk.daemon = True
        self._hk.start()

    # -- Actions ---------------------------------------------------- #

    def toggle_record(self):
        if self._state == self.REP:
            return
        if self._state == self.IDLE:
            self._start_rec()
        else:
            self._stop_rec()

    def toggle_replay(self):
        if self._state == self.REC:
            return
        if self._state == self.REP:
            self._stop_rep()
        elif self.recorder.events:
            self._begin_rep()

    def emergency_stop(self):
        if self._state == self.REC:
            self._stop_rec()
        elif self._state == self.REP:
            self._stop_rep()

    def _start_rec(self):
        self.recorder = Recorder(record_mouse=self._mouse_var.get())
        self.recorder.start()
        self._state = self.REC
        self._set_status("⏺  Enregistrement...", "red")
        self._info_var.set("Jouez normalement — F9 pour arrêter")
        self._rec_btn.config(text="⏹  Arrêter  (F9)")
        self._rep_btn.config(state="disabled")

    def _stop_rec(self):
        self.recorder.stop()
        self._state = self.IDLE
        n = len(self.recorder.events)
        self._set_status("Enregistrement terminé", "green")
        self._info_var.set(f"{n} événements capturés")
        self._rec_btn.config(text="⏺  Enregistrer  (F9)")
        self._rep_btn.config(state="normal" if n > 0 else "disabled")

    def _begin_rep(self):
        delay = self._delay_var.get()
        if delay > 0:
            self._set_status(f"Démarrage dans {delay}s...", "orange")
            self._info_var.set("Revenez sur FiveM !")
            self._rep_btn.config(state="disabled")
            self.root.after(delay * 1000, self._start_rep)
        else:
            self._start_rep()

    def _start_rep(self):
        self._state = self.REP
        self._cycles = 0
        self._set_status("▶  Replay en boucle...", "blue")
        self._info_var.set("Cycle #0")
        self._rep_btn.config(text="⏹  Arrêter  (F10)", state="normal")
        self._rec_btn.config(state="disabled")

        def on_cycle(n):
            self._cycles = n
            self.root.after(0, lambda: self._info_var.set(f"Cycle #{n}"))

        self.replayer.start(self.recorder.events, loop=True, on_cycle=on_cycle)

    def _stop_rep(self):
        self.replayer.stop()
        self._state = self.IDLE
        self._set_status("Replay arrêté", "gray")
        self._info_var.set(f"Cycles complétés : {self._cycles}")
        self._rep_btn.config(text="▶  Rejouer en boucle  (F10)", state="normal")
        self._rec_btn.config(state="normal")

    def _set_status(self, text, color):
        self._status_var.set(text)
        self._slabel.config(fg=color)

    def save(self):
        if not self.recorder.events:
            messagebox.showwarning("Vide", "Aucun enregistrement à sauvegarder.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
        )
        if path:
            self.recorder.save(path)

    def load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("Tous", "*.*")])
        if path:
            self.recorder.load(path)
            n = len(self.recorder.events)
            self._set_status("Enregistrement chargé", "green")
            self._info_var.set(f"{n} événements")
            self._rep_btn.config(state="normal" if n > 0 else "disabled")

    def on_close(self):
        self.replayer.stop()
        self.recorder.stop()
        self._hk.stop()
        self.root.destroy()


# ------------------------------------------------------------------ #
#  Lancement                                                           #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
