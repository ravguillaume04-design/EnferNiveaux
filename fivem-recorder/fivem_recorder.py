import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pynput import keyboard, mouse

# La touche + (numpad vk=107, ou char='+')
TOGGLE_VK = 107
MOUSE_THROTTLE = 0.05  # 50ms entre enregistrements souris


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
    if not data:
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


def _is_toggle(key):
    """Vérifie si la touche est + (numpad ou clavier)."""
    try:
        return key.char == "+"
    except AttributeError:
        return getattr(key, "vk", None) == TOGGLE_VK


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
        for lst in (self._kb_listener, self._mouse_listener):
            if lst:
                lst.stop()
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
        # Ne pas enregistrer la touche + (toggle du menu)
        if _is_toggle(key) or not self.is_recording:
            return
        s = _serialize_key(key)
        if s:
            with self._lock:
                self.events.append({"type": "key_press", "t": self._ts(), "key": s})

    def _on_key_release(self, key):
        if _is_toggle(key) or not self.is_recording:
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

    def start(self, events, on_cycle=None):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, args=(events, on_cycle), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self, events, on_cycle):
        cycle = 0
        while self._running:
            cycle += 1
            if on_cycle:
                on_cycle(cycle)
            self._play_once(events)

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
        # Relâcher toutes les touches encore pressées en fin de cycle
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
#  Overlay                                                             #
# ------------------------------------------------------------------ #

class OverlayApp:
    IDLE = "idle"
    REC  = "recording"
    REP  = "replaying"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FiveM Recorder")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.geometry("240+10+10")
        try:
            self.root.wm_attributes("-toolwindow", True)  # Pas dans la barre des tâches
        except Exception:
            pass

        self._state      = self.IDLE
        self._has_events = False
        self._cycles     = 0
        self._hide_job   = None
        self._mouse_var  = tk.BooleanVar(value=True)

        self.recorder = Recorder()
        self.replayer = Replayer()

        self._build_ui()
        self._start_hotkeys()
        self.root.withdraw()  # Caché au démarrage

    # ---------------------------------------------------------------- #
    #  Construction de l'UI                                             #
    # ---------------------------------------------------------------- #

    def _build_ui(self):
        # En-tête
        header = tk.Frame(self.root, bg="#1a1a2e", pady=8)
        header.pack(fill="x")
        tk.Label(header, text="FiveM Recorder", bg="#1a1a2e", fg="white",
                 font=("Helvetica", 12, "bold")).pack()
        tk.Label(header, text="Touche  +  pour ouvrir / fermer",
                 bg="#1a1a2e", fg="#888888", font=("Helvetica", 8)).pack()

        # Statut
        status_frame = tk.Frame(self.root, pady=6)
        status_frame.pack(fill="x", padx=12)
        self._status_label = tk.Label(status_frame, text="En attente",
                                       font=("Helvetica", 11, "bold"), fg="gray")
        self._status_label.pack()
        self._info_label = tk.Label(status_frame, text="", fg="gray",
                                     font=("Helvetica", 9))
        self._info_label.pack()

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Boutons dynamiques
        self._btn_frame = tk.Frame(self.root)
        self._btn_frame.pack(fill="x", padx=12, pady=8)

        def btn(parent, text, color, cmd):
            return tk.Button(
                parent, text=text, bg=color, fg="white",
                activebackground=color, activeforeground="white",
                relief="flat", padx=6, pady=7, cursor="hand2",
                font=("Helvetica", 10), command=cmd, width=26,
            )

        self._rec_btn      = btn(self._btn_frame, "⏺   Enregistrer",           "#c0392b", self.start_record)
        self._stop_rec_btn = btn(self._btn_frame, "⏹   Arrêter l'enregistrement", "#e67e22", self.stop_record)
        self._rep_btn      = btn(self._btn_frame, "▶   Rejouer en boucle",      "#1e8449", self.start_replay)
        self._stop_rep_btn = btn(self._btn_frame, "⏹   Arrêter le replay",      "#922b21", self.stop_replay)

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Options
        opt = tk.Frame(self.root)
        opt.pack(fill="x", padx=12, pady=4)
        tk.Checkbutton(opt, text="Enregistrer les mouvements de souris",
                       variable=self._mouse_var, font=("Helvetica", 9)).pack(anchor="w")

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Fichier
        file_row = tk.Frame(self.root)
        file_row.pack(pady=6)
        tk.Button(file_row, text="Sauvegarder", width=12,
                  command=self.save).pack(side="left", padx=4)
        tk.Button(file_row, text="Charger", width=12,
                  command=self.load).pack(side="left", padx=4)

        self._update_buttons()

    def _update_buttons(self):
        for w in self._btn_frame.winfo_children():
            w.pack_forget()
        if self._state == self.IDLE:
            self._rec_btn.pack(fill="x", pady=2)
            if self._has_events:
                self._rep_btn.pack(fill="x", pady=2)
        elif self._state == self.REC:
            self._stop_rec_btn.pack(fill="x", pady=2)
        elif self._state == self.REP:
            self._stop_rep_btn.pack(fill="x", pady=2)

    # ---------------------------------------------------------------- #
    #  Overlay toggle                                                    #
    # ---------------------------------------------------------------- #

    def _toggle_overlay(self):
        self._cancel_auto_hide()
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)

    def _schedule_hide(self, ms=1800):
        self._cancel_auto_hide()
        self._hide_job = self.root.after(ms, self.root.withdraw)

    def _cancel_auto_hide(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None

    # ---------------------------------------------------------------- #
    #  Actions                                                           #
    # ---------------------------------------------------------------- #

    def start_record(self):
        self.recorder = Recorder(record_mouse=self._mouse_var.get())
        self.recorder.start()
        self._state = self.REC
        self._status_label.config(text="⏺  Enregistrement...", fg="#c0392b")
        self._info_label.config(text="Jouez — appuyez + pour revoir le menu")
        self._update_buttons()
        self._schedule_hide()  # Cache automatiquement après 1,8s

    def stop_record(self):
        self.recorder.stop()
        self._state = self.IDLE
        self._has_events = bool(self.recorder.events)
        n = len(self.recorder.events)
        self._status_label.config(text="Enregistrement terminé", fg="#1e8449")
        self._info_label.config(text=f"{n} événements capturés")
        self._update_buttons()

    def start_replay(self):
        if not self.recorder.events:
            return
        self._state   = self.REP
        self._cycles  = 0
        self._status_label.config(text="▶  Replay en cours...", fg="#1a5276")
        self._info_label.config(text="Cycle #0")
        self._update_buttons()
        self._schedule_hide()

        def on_cycle(n):
            self._cycles = n
            self.root.after(0, lambda: self._info_label.config(text=f"Cycle #{n}"))

        self.replayer.start(self.recorder.events, on_cycle=on_cycle)

    def stop_replay(self):
        self.replayer.stop()
        self._state = self.IDLE
        self._status_label.config(text="Replay arrêté", fg="gray")
        self._info_label.config(text=f"Cycles complétés : {self._cycles}")
        self._update_buttons()

    # ---------------------------------------------------------------- #
    #  Fichier                                                           #
    # ---------------------------------------------------------------- #

    def save(self):
        if not self.recorder.events:
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
            self._has_events = bool(self.recorder.events)
            n = len(self.recorder.events)
            self._status_label.config(text="Enregistrement chargé", fg="#1e8449")
            self._info_label.config(text=f"{n} événements")
            self._update_buttons()

    # ---------------------------------------------------------------- #
    #  Hotkeys globaux                                                   #
    # ---------------------------------------------------------------- #

    def _start_hotkeys(self):
        def on_press(key):
            if _is_toggle(key):
                self.root.after(0, self._toggle_overlay)

        self._hk = keyboard.Listener(on_press=on_press, suppress=False)
        self._hk.daemon = True
        self._hk.start()

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
    app = OverlayApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
