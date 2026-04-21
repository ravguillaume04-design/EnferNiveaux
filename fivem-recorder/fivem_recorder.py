import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pynput import keyboard, mouse

TOGGLE_VK = 107   # Numpad +
PAUSE_VK  = 109   # Numpad -
MOUSE_THROTTLE = 0.05


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
    try:
        return key.char == "+"
    except AttributeError:
        return getattr(key, "vk", None) == TOGGLE_VK


def _is_pause_key(key):
    try:
        return key.char == "-"
    except AttributeError:
        return getattr(key, "vk", None) == PAUSE_VK


def _is_filtered(key):
    """Touches jamais enregistrées : +, -, Echap."""
    if _is_toggle(key) or _is_pause_key(key):
        return True
    return key == keyboard.Key.esc


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
        if _is_filtered(key) or not self.is_recording:
            return
        s = _serialize_key(key)
        if s:
            with self._lock:
                self.events.append({"type": "key_press", "t": self._ts(), "key": s})

    def _on_key_release(self, key):
        if _is_filtered(key) or not self.is_recording:
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
        self._paused  = False
        self._thread  = None

    @property
    def is_running(self):
        return self._running

    @property
    def is_paused(self):
        return self._paused

    def toggle_pause(self):
        self._paused = not self._paused

    def start(self, events, interval=0, on_cycle=None, on_interval_tick=None):
        if self._running:
            return
        self._running = True
        self._paused  = False
        self._thread  = threading.Thread(
            target=self._run,
            args=(events, interval, on_cycle, on_interval_tick),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._running = False
        self._paused  = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ---------------------------------------------------------------- #

    def _run(self, events, interval, on_cycle, on_interval_tick):
        cycle = 0
        while self._running:
            cycle += 1
            if on_cycle:
                on_cycle(cycle)
            self._play_once(events)
            if not self._running:
                break
            if interval > 0:
                self._wait_interval(interval, on_interval_tick)

    def _play_once(self, events):
        pressed_keys, pressed_buttons = set(), set()
        wall_start  = time.perf_counter()
        total_pause = [0.0]  # liste pour pouvoir modifier depuis _wait_for_event

        for ev in events:
            if not self._running:
                break
            self._wait_for_event(wall_start, total_pause, ev["t"])
            if not self._running:
                break
            self._execute(ev, pressed_keys, pressed_buttons)

        # Relâcher tout ce qui est encore pressé
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

    def _wait_for_event(self, wall_start, total_pause, event_t):
        """
        Attend que le temps virtuel (hors pauses) atteigne event_t.
        Le temps virtuel = temps réel écoulé - temps total en pause.
        """
        while self._running:
            # Accumule la durée de pause
            if self._paused:
                pause_start = time.perf_counter()
                while self._paused and self._running:
                    time.sleep(0.02)
                total_pause[0] += time.perf_counter() - pause_start

            virtual_elapsed = time.perf_counter() - wall_start - total_pause[0]
            if virtual_elapsed >= event_t:
                break
            time.sleep(min(event_t - virtual_elapsed, 0.02))

    def _wait_interval(self, interval, on_tick):
        """Attend `interval` secondes entre deux cycles, avec mise à jour de compteur."""
        deadline = time.perf_counter() + interval
        while self._running:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            if on_tick:
                on_tick(remaining)
            time.sleep(min(remaining, 0.25))

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
        self.root.geometry("+10+10")
        self.root.minsize(240, 0)
        try:
            self.root.wm_attributes("-toolwindow", True)
        except Exception:
            pass

        self._state         = self.IDLE
        self._has_events    = False
        self._cycles        = 0
        self._paused        = False
        self._hide_job      = None
        self._mouse_var     = tk.BooleanVar(value=True)
        self._interval_var  = tk.IntVar(value=0)

        self.recorder = Recorder()
        self.replayer = Replayer()

        self._build_ui()
        self._start_hotkeys()
        self.root.withdraw()

    # ---------------------------------------------------------------- #
    #  UI                                                                #
    # ---------------------------------------------------------------- #

    def _build_ui(self):
        # En-tête
        header = tk.Frame(self.root, bg="#1a1a2e", pady=8)
        header.pack(fill="x")
        tk.Label(header, text="FiveM Recorder", bg="#1a1a2e", fg="white",
                 font=("Helvetica", 12, "bold")).pack()
        tk.Label(header, text="+  ouvrir/fermer     −  pause/reprendre",
                 bg="#1a1a2e", fg="#888888", font=("Helvetica", 8)).pack()

        # Statut
        sf = tk.Frame(self.root, pady=6)
        sf.pack(fill="x", padx=12)
        self._status_label = tk.Label(sf, text="En attente",
                                       font=("Helvetica", 11, "bold"), fg="gray")
        self._status_label.pack()
        self._info_label = tk.Label(sf, text="", fg="gray", font=("Helvetica", 9))
        self._info_label.pack()

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Boutons dynamiques
        self._btn_frame = tk.Frame(self.root)
        self._btn_frame.pack(fill="x", padx=12, pady=8)

        def btn(text, color, cmd):
            return tk.Button(
                self._btn_frame, text=text, bg=color, fg="white",
                activebackground=color, activeforeground="white",
                relief="flat", padx=6, pady=7, cursor="hand2",
                font=("Helvetica", 10), command=cmd, width=26,
            )

        self._rec_btn      = btn("⏺   Enregistrer",              "#c0392b", self.start_record)
        self._stop_rec_btn = btn("⏹   Arrêter l'enregistrement", "#e67e22", self.stop_record)
        self._rep_btn      = btn("▶   Rejouer en boucle",         "#1e8449", self.start_replay)
        self._stop_rep_btn = btn("⏹   Arrêter le replay",         "#922b21", self.stop_replay)

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Options
        opt = tk.Frame(self.root)
        opt.pack(fill="x", padx=12, pady=5)

        tk.Checkbutton(opt, text="Enregistrer les mouvements de souris",
                       variable=self._mouse_var, font=("Helvetica", 9)).pack(anchor="w")

        int_row = tk.Frame(opt)
        int_row.pack(fill="x", pady=(4, 0))
        tk.Label(int_row, text="Intervalle entre cycles (s) :",
                 font=("Helvetica", 9)).pack(side="left")
        tk.Spinbox(int_row, from_=0, to=300, textvariable=self._interval_var,
                   width=4, font=("Helvetica", 9)).pack(side="left", padx=6)

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
        self._schedule_hide()

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
        self._state  = self.REP
        self._cycles = 0
        self._paused = False
        self._status_label.config(text="▶  Replay en cours...", fg="#1a5276")
        self._info_label.config(text="Cycle #0")
        self._update_buttons()
        self._schedule_hide()

        def on_cycle(n):
            self._cycles = n
            self.root.after(0, lambda: self._info_label.config(text=f"Cycle #{n}"))

        def on_interval_tick(remaining):
            self.root.after(0, lambda r=remaining: self._info_label.config(
                text=f"Prochain cycle dans {r:.0f}s..."
            ))

        self.replayer.start(
            self.recorder.events,
            interval=self._interval_var.get(),
            on_cycle=on_cycle,
            on_interval_tick=on_interval_tick,
        )

    def stop_replay(self):
        self.replayer.stop()
        self._state  = self.IDLE
        self._paused = False
        self._status_label.config(text="Replay arrêté", fg="gray")
        self._info_label.config(text=f"Cycles complétés : {self._cycles}")
        self._update_buttons()

    def _toggle_pause(self):
        if self._state != self.REP:
            return
        self._paused = not self._paused
        self.replayer.toggle_pause()
        if self._paused:
            self._status_label.config(text="⏸  En pause", fg="#e67e22")
            self._info_label.config(text="Appuyez − pour reprendre")
            # Afficher le menu pour confirmer la pause
            self._cancel_auto_hide()
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        else:
            self._status_label.config(text="▶  Replay en cours...", fg="#1a5276")
            self._info_label.config(text=f"Cycle #{self._cycles}")
            self._schedule_hide()

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
            elif _is_pause_key(key):
                self.root.after(0, self._toggle_pause)

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
