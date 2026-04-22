import tkinter as tk
from tkinter import filedialog, messagebox
from pynput import keyboard

from recorder import Recorder
from replayer import Replayer


class App:
    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_REPLAYING = "replaying"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FiveM Movement Recorder")
        self.root.resizable(False, False)

        self._mouse_var = tk.BooleanVar(value=True)
        self._delay_var = tk.IntVar(value=5)
        self._status_var = tk.StringVar(value="En attente")
        self._info_var = tk.StringVar(value="")

        self.recorder = Recorder(record_mouse=self._mouse_var.get())
        self.replayer = Replayer()
        self._state = self.STATE_IDLE
        self._cycles = 0

        self._build_ui()
        self._start_hotkey_listener()

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        PAD = dict(padx=10, pady=5)

        # Status
        status_frame = tk.LabelFrame(self.root, text="Statut", **PAD)
        status_frame.pack(fill="x", **PAD)
        self._status_label = tk.Label(
            status_frame,
            textvariable=self._status_var,
            font=("Helvetica", 13, "bold"),
            fg="gray",
        )
        self._status_label.pack()
        tk.Label(status_frame, textvariable=self._info_var, fg="gray").pack()

        # Buttons
        ctrl_frame = tk.LabelFrame(self.root, text="Contrôles", **PAD)
        ctrl_frame.pack(fill="x", **PAD)
        self._record_btn = tk.Button(
            ctrl_frame, text="⏺  Enregistrer  (F9)", width=28,
            command=self.toggle_record,
        )
        self._record_btn.pack(pady=3)
        self._replay_btn = tk.Button(
            ctrl_frame, text="▶  Rejouer en boucle  (F10)", width=28,
            command=self.toggle_replay, state="disabled",
        )
        self._replay_btn.pack(pady=3)

        # Settings
        settings_frame = tk.LabelFrame(self.root, text="Paramètres", **PAD)
        settings_frame.pack(fill="x", **PAD)

        delay_row = tk.Frame(settings_frame)
        delay_row.pack(fill="x", pady=2)
        tk.Label(delay_row, text="Délai avant replay (s) :").pack(side="left")
        tk.Spinbox(delay_row, from_=0, to=30, textvariable=self._delay_var,
                   width=4).pack(side="left", padx=5)

        tk.Checkbutton(
            settings_frame, text="Enregistrer les mouvements de souris",
            variable=self._mouse_var,
        ).pack(anchor="w", pady=2)

        # File
        file_frame = tk.LabelFrame(self.root, text="Fichier", **PAD)
        file_frame.pack(fill="x", **PAD)
        row = tk.Frame(file_frame)
        row.pack()
        tk.Button(row, text="Sauvegarder", command=self.save).pack(side="left", padx=5)
        tk.Button(row, text="Charger", command=self.load).pack(side="left", padx=5)

        # Hotkeys
        help_frame = tk.LabelFrame(self.root, text="Raccourcis globaux", **PAD)
        help_frame.pack(fill="x", **PAD)
        tk.Label(help_frame, text=(
            "F9   —  Démarrer / Arrêter l'enregistrement\n"
            "F10  —  Démarrer / Arrêter le replay\n"
            "F11  —  Arrêt d'urgence"
        ), justify="left", font=("Courier", 9)).pack(anchor="w")

    # ------------------------------------------------------------------ #
    #  Hotkeys (global — fonctionnent même quand FiveM est au premier plan) #
    # ------------------------------------------------------------------ #

    def _start_hotkey_listener(self):
        def on_press(key):
            if key == keyboard.Key.f9:
                self.root.after(0, self.toggle_record)
            elif key == keyboard.Key.f10:
                self.root.after(0, self.toggle_replay)
            elif key == keyboard.Key.f11:
                self.root.after(0, self.emergency_stop)

        self._hotkey_listener = keyboard.Listener(on_press=on_press, suppress=False)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # ------------------------------------------------------------------ #
    #  Actions                                                             #
    # ------------------------------------------------------------------ #

    def toggle_record(self):
        if self._state == self.STATE_REPLAYING:
            return
        if self._state == self.STATE_IDLE:
            self._start_recording()
        else:
            self._stop_recording()

    def toggle_replay(self):
        if self._state == self.STATE_RECORDING:
            return
        if self._state == self.STATE_REPLAYING:
            self._stop_replay()
        elif self.recorder.events:
            self._begin_replay()

    def emergency_stop(self):
        if self._state == self.STATE_RECORDING:
            self._stop_recording()
        elif self._state == self.STATE_REPLAYING:
            self._stop_replay()

    # ------------------------------------------------------------------ #

    def _start_recording(self):
        self.recorder = Recorder(record_mouse=self._mouse_var.get())
        self.recorder.start()
        self._state = self.STATE_RECORDING
        self._set_status("⏺  Enregistrement...", "red")
        self._info_var.set("Jouez normalement — F9 pour arrêter")
        self._record_btn.config(text="⏹  Arrêter  (F9)")
        self._replay_btn.config(state="disabled")

    def _stop_recording(self):
        self.recorder.stop()
        self._state = self.STATE_IDLE
        n = len(self.recorder.events)
        self._set_status("Enregistrement terminé", "green")
        self._info_var.set(f"{n} événements capturés")
        self._record_btn.config(text="⏺  Enregistrer  (F9)")
        self._replay_btn.config(state="normal" if n > 0 else "disabled")

    def _begin_replay(self):
        delay = self._delay_var.get()
        if delay > 0:
            self._set_status(f"Démarrage dans {delay}s...", "orange")
            self._info_var.set("Revenez sur FiveM !")
            self._replay_btn.config(state="disabled")
            self.root.after(delay * 1000, self._start_replay)
        else:
            self._start_replay()

    def _start_replay(self):
        self._state = self.STATE_REPLAYING
        self._cycles = 0
        self._set_status("▶  Replay en boucle...", "blue")
        self._info_var.set("Cycle #0")
        self._replay_btn.config(text="⏹  Arrêter replay  (F10)", state="normal")
        self._record_btn.config(state="disabled")

        def on_cycle(n):
            self._cycles = n
            self.root.after(0, lambda: self._info_var.set(f"Cycle #{n}"))

        self.replayer.start(self.recorder.events, loop=True, on_cycle=on_cycle)

    def _stop_replay(self):
        self.replayer.stop()
        self._state = self.STATE_IDLE
        self._set_status("Replay arrêté", "gray")
        self._info_var.set(f"Cycles complétés : {self._cycles}")
        self._replay_btn.config(text="▶  Rejouer en boucle  (F10)", state="normal")
        self._record_btn.config(state="normal")

    # ------------------------------------------------------------------ #

    def _set_status(self, text, color):
        self._status_var.set(text)
        self._status_label.config(fg=color)

    # ------------------------------------------------------------------ #
    #  File                                                                #
    # ------------------------------------------------------------------ #

    def save(self):
        if not self.recorder.events:
            messagebox.showwarning("Aucun enregistrement", "Enregistrez d'abord un cycle.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
            title="Sauvegarder l'enregistrement",
        )
        if path:
            self.recorder.save(path)
            messagebox.showinfo("Sauvegardé", f"Fichier enregistré :\n{path}")

    def load(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
            title="Charger un enregistrement",
        )
        if path:
            self.recorder.load(path)
            n = len(self.recorder.events)
            self._set_status("Enregistrement chargé", "green")
            self._info_var.set(f"{n} événements")
            self._replay_btn.config(state="normal" if n > 0 else "disabled")

    def on_close(self):
        self.replayer.stop()
        self.recorder.stop()
        self._hotkey_listener.stop()
        self.root.destroy()


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
