"""
Bot de farming automatique pour GTA V / FiveM.
Téléporte le joueur de waypoint en waypoint et exécute les interactions.
"""
import math
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pynput import keyboard as kb

from gta_memory import GTAMemory

SAVE_HOTKEY_VK = 96   # Numpad 0 — enregistre la position courante

# ------------------------------------------------------------------ #
#  Waypoint                                                            #
# ------------------------------------------------------------------ #

class Waypoint:
    ACTIONS = ['Aucune', 'E  (interaction)', 'F  (véhicule)', 'G  (arme)', 'Personnalisée']

    def __init__(self, name='Waypoint', x=0.0, y=0.0, z=0.0, action=''):
        self.name   = name
        self.x      = x
        self.y      = y
        self.z      = z
        self.action = action   # Touche à presser à l'arrivée ('' = rien)

    def distance_2d(self, x, y):
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    def to_dict(self):
        return {'name': self.name, 'x': self.x, 'y': self.y,
                'z': self.z, 'action': self.action}

    @classmethod
    def from_dict(cls, d):
        return cls(d['name'], d['x'], d['y'], d['z'], d.get('action', ''))

    def __str__(self):
        act = f' → [{self.action}]' if self.action else ''
        return f'{self.name}  ({self.x:.1f}, {self.y:.1f}){act}'


# ------------------------------------------------------------------ #
#  Bot                                                                 #
# ------------------------------------------------------------------ #

class Bot:
    def __init__(self, memory: GTAMemory):
        self._mem     = memory
        self._kb      = kb.Controller()
        self._running = False
        self._thread  = None

    @property
    def is_running(self):
        return self._running

    def start(self, waypoints, loop=True, delay=2.0, on_status=None, on_done=None):
        if self._running or not waypoints:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            args=(waypoints, loop, delay, on_status, on_done),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    # ---------------------------------------------------------------- #

    def _run(self, waypoints, loop, delay, on_status, on_done):
        cycle = 0
        while self._running:
            cycle += 1
            for i, wp in enumerate(waypoints):
                if not self._running:
                    break
                if on_status:
                    on_status(f'Cycle {cycle}  →  {wp.name}  ({i+1}/{len(waypoints)})')

                ok = self._teleport_to(wp)
                if not ok or not self._running:
                    break

                if wp.action:
                    time.sleep(0.4)
                    self._press(wp.action)

                # Pause entre waypoints
                self._wait(delay)

            if not loop:
                self._running = False

        if on_done:
            on_done()

    def _teleport_to(self, wp):
        for _ in range(10):
            if not self._running:
                return False
            if self._mem.teleport(wp.x, wp.y, wp.z):
                time.sleep(0.3)
                pos = self._mem.get_position()
                if pos and wp.distance_2d(pos[0], pos[1]) < 5.0:
                    return True
            time.sleep(0.2)
        return False

    def _press(self, key):
        try:
            k = kb.KeyCode.from_char(key) if len(key) == 1 else kb.Key[key]
            self._kb.press(k)
            time.sleep(0.2)
            self._kb.release(k)
        except Exception:
            pass

    def _wait(self, seconds):
        end = time.perf_counter() + seconds
        while self._running and time.perf_counter() < end:
            time.sleep(0.05)


# ================================================================== #
#  Fenêtre du bot (tkinter Toplevel)                                   #
# ================================================================== #

class BotWindow:
    def __init__(self, parent: tk.Tk):
        self._parent = parent
        self._mem    = GTAMemory()
        self._bot    = Bot(self._mem)
        self._wps: list[Waypoint] = []

        self._win = tk.Toplevel(parent)
        self._win.title('Bot Farming GTA V')
        self._win.attributes('-topmost', True)
        self._win.resizable(False, False)
        self._win.geometry('+270+10')
        self._win.protocol('WM_DELETE_WINDOW', self._on_close)
        try:
            self._win.wm_attributes('-toolwindow', True)
        except Exception:
            pass

        self._status_var  = tk.StringVar(value='Non connecté')
        self._loop_var    = tk.BooleanVar(value=True)
        self._delay_min   = tk.IntVar(value=0)
        self._delay_sec   = tk.IntVar(value=2)
        self._custom_var  = tk.StringVar(value='e')

        self._build_ui()
        self._start_hotkey_listener()

    # ---------------------------------------------------------------- #
    #  UI                                                                #
    # ---------------------------------------------------------------- #

    def _build_ui(self):
        P = dict(padx=8, pady=4)

        # En-tête
        hdr = tk.Frame(self._win, bg='#1a1a2e', pady=6)
        hdr.pack(fill='x')
        tk.Label(hdr, text='Bot Farming GTA V', bg='#1a1a2e', fg='white',
                 font=('Helvetica', 11, 'bold')).pack()
        tk.Label(hdr, text='Numpad 0 — sauvegarder la position courante',
                 bg='#1a1a2e', fg='#888', font=('Helvetica', 8)).pack()

        # Connexion
        cf = tk.LabelFrame(self._win, text='Connexion GTA V', **P)
        cf.pack(fill='x', **P)
        row = tk.Frame(cf)
        row.pack(fill='x')
        self._conn_label = tk.Label(row, textvariable=self._status_var,
                                     fg='red', font=('Helvetica', 9))
        self._conn_label.pack(side='left')
        tk.Button(row, text='Connecter', command=self._connect,
                  relief='flat', bg='#2c3e50', fg='white',
                  padx=6, pady=2).pack(side='right')

        # Waypoints
        wf = tk.LabelFrame(self._win, text='Waypoints  (Numpad 0 pour ajouter)', **P)
        wf.pack(fill='x', **P)

        list_frame = tk.Frame(wf)
        list_frame.pack(fill='x')
        scrollbar = tk.Scrollbar(list_frame, orient='vertical')
        self._listbox = tk.Listbox(list_frame, height=6, width=38,
                                    yscrollcommand=scrollbar.set,
                                    selectmode='single', font=('Courier', 9))
        scrollbar.config(command=self._listbox.yview)
        self._listbox.pack(side='left', fill='x', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Boutons waypoint
        btn_row = tk.Frame(wf)
        btn_row.pack(fill='x', pady=(4, 0))
        tk.Button(btn_row, text='▲ Monter',   command=self._wp_up,     width=9).pack(side='left', padx=2)
        tk.Button(btn_row, text='▼ Descendre',command=self._wp_down,   width=9).pack(side='left', padx=2)
        tk.Button(btn_row, text='✎ Renommer', command=self._wp_rename,  width=9).pack(side='left', padx=2)
        tk.Button(btn_row, text='✕ Supprimer',command=self._wp_delete,  width=9).pack(side='left', padx=2)

        # Action par défaut pour le prochain waypoint
        act_frame = tk.LabelFrame(self._win, text='Action à l\'arrivée (prochain waypoint)', **P)
        act_frame.pack(fill='x', **P)
        self._action_var = tk.StringVar(value='e')
        acts = [('Aucune', ''), ('E  (interaction/récolter)', 'e'),
                ('F  (entrer véhicule)', 'f'), ('G', 'g')]
        act_row = tk.Frame(act_frame)
        act_row.pack(fill='x')
        for label, val in acts:
            tk.Radiobutton(act_row, text=label, variable=self._action_var,
                           value=val, font=('Helvetica', 9)).pack(side='left', padx=3)

        # Sauvegarde des waypoints
        file_row = tk.Frame(self._win)
        file_row.pack(pady=2)
        tk.Button(file_row, text='Sauvegarder waypoints', width=18,
                  command=self._save_wps).pack(side='left', padx=4)
        tk.Button(file_row, text='Charger waypoints', width=16,
                  command=self._load_wps).pack(side='left', padx=4)

        ttk.Separator(self._win).pack(fill='x', padx=8, pady=4)

        # Paramètres bot
        pf = tk.LabelFrame(self._win, text='Paramètres', **P)
        pf.pack(fill='x', **P)

        delay_row = tk.Frame(pf)
        delay_row.pack(anchor='w')
        tk.Label(delay_row, text='Pause entre waypoints :',
                 font=('Helvetica', 9)).pack(side='left')
        tk.Spinbox(delay_row, from_=0, to=59, textvariable=self._delay_min,
                   width=3, font=('Helvetica', 9)).pack(side='left', padx=(4, 0))
        tk.Label(delay_row, text='min', font=('Helvetica', 9)).pack(side='left', padx=(2, 6))
        tk.Spinbox(delay_row, from_=0, to=59, textvariable=self._delay_sec,
                   width=3, font=('Helvetica', 9)).pack(side='left')
        tk.Label(delay_row, text='sec', font=('Helvetica', 9)).pack(side='left', padx=(2, 0))

        tk.Checkbutton(pf, text='Boucle infinie', variable=self._loop_var,
                       font=('Helvetica', 9)).pack(anchor='w', pady=2)

        # Démarrer / Arrêter
        ctrl = tk.Frame(self._win)
        ctrl.pack(pady=8)
        self._start_btn = tk.Button(ctrl, text='▶  Démarrer le bot', width=18,
                                     bg='#1e8449', fg='white', relief='flat',
                                     font=('Helvetica', 11), command=self._start_bot)
        self._start_btn.pack(side='left', padx=4)
        self._stop_btn = tk.Button(ctrl, text='⏹  Arrêter', width=10,
                                    bg='#922b21', fg='white', relief='flat',
                                    font=('Helvetica', 11), command=self._stop_bot,
                                    state='disabled')
        self._stop_btn.pack(side='left', padx=4)

        # Statut bot
        self._bot_status = tk.Label(self._win, text='', fg='#1a5276',
                                     font=('Helvetica', 9))
        self._bot_status.pack(pady=(0, 6))

    # ---------------------------------------------------------------- #
    #  Connexion                                                         #
    # ---------------------------------------------------------------- #

    def _connect(self):
        try:
            self._mem.connect()
            pos = self._mem.get_position()
            if pos:
                self._status_var.set(f'Connecté  •  pos: ({pos[0]:.0f}, {pos[1]:.0f})')
                self._conn_label.config(fg='#1e8449')
            else:
                self._status_var.set('Connecté  •  position illisible (êtes-vous en jeu ?)')
                self._conn_label.config(fg='orange')
        except RuntimeError as e:
            self._status_var.set(str(e).split('\n')[0])
            self._conn_label.config(fg='red')
            messagebox.showerror('Erreur de connexion', str(e), parent=self._win)

    # ---------------------------------------------------------------- #
    #  Waypoints                                                         #
    # ---------------------------------------------------------------- #

    def _add_waypoint_from_memory(self):
        if not self._mem.connected:
            return
        pos = self._mem.get_position()
        if not pos:
            return
        name = f'WP {len(self._wps) + 1}'
        action = self._action_var.get()
        wp = Waypoint(name, pos[0], pos[1], pos[2], action)
        self._wps.append(wp)
        self._refresh_list()
        # Mise à jour statut connexion avec position
        self._status_var.set(f'Connecté  •  WP ajouté ({pos[0]:.1f}, {pos[1]:.1f})')

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for wp in self._wps:
            self._listbox.insert(tk.END, str(wp))

    def _selected_idx(self):
        sel = self._listbox.curselection()
        return sel[0] if sel else None

    def _wp_up(self):
        i = self._selected_idx()
        if i is None or i == 0:
            return
        self._wps[i-1], self._wps[i] = self._wps[i], self._wps[i-1]
        self._refresh_list()
        self._listbox.select_set(i-1)

    def _wp_down(self):
        i = self._selected_idx()
        if i is None or i >= len(self._wps) - 1:
            return
        self._wps[i], self._wps[i+1] = self._wps[i+1], self._wps[i]
        self._refresh_list()
        self._listbox.select_set(i+1)

    def _wp_rename(self):
        i = self._selected_idx()
        if i is None:
            return
        win = tk.Toplevel(self._win)
        win.title('Renommer')
        win.attributes('-topmost', True)
        tk.Label(win, text='Nouveau nom :').pack(padx=10, pady=(10, 2))
        var = tk.StringVar(value=self._wps[i].name)
        entry = tk.Entry(win, textvariable=var, width=20)
        entry.pack(padx=10)
        entry.focus()

        def confirm():
            self._wps[i].name = var.get()
            self._refresh_list()
            win.destroy()

        tk.Button(win, text='OK', command=confirm).pack(pady=8)
        win.bind('<Return>', lambda _: confirm())

    def _wp_delete(self):
        i = self._selected_idx()
        if i is None:
            return
        self._wps.pop(i)
        self._refresh_list()

    def _save_wps(self):
        if not self._wps:
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=[('JSON', '*.json'), ('Tous', '*.*')],
            parent=self._win,
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([wp.to_dict() for wp in self._wps], f, indent=2)

    def _load_wps(self):
        path = filedialog.askopenfilename(
            filetypes=[('JSON', '*.json'), ('Tous', '*.*')],
            parent=self._win,
        )
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._wps = [Waypoint.from_dict(d) for d in data]
            self._refresh_list()

    # ---------------------------------------------------------------- #
    #  Bot                                                               #
    # ---------------------------------------------------------------- #

    def _start_bot(self):
        if not self._mem.connected:
            messagebox.showwarning('Non connecté',
                                   'Connectez-vous à GTA V d\'abord.', parent=self._win)
            return
        if not self._wps:
            messagebox.showwarning('Aucun waypoint',
                                   'Ajoutez au moins un waypoint.', parent=self._win)
            return

        delay = self._delay_min.get() * 60 + self._delay_sec.get()

        self._start_btn.config(state='disabled')
        self._stop_btn.config(state='normal')

        def on_status(msg):
            self._win.after(0, lambda m=msg: self._bot_status.config(text=m))

        def on_done():
            self._win.after(0, self._on_bot_done)

        self._bot.start(
            self._wps,
            loop=self._loop_var.get(),
            delay=delay,
            on_status=on_status,
            on_done=on_done,
        )

    def _stop_bot(self):
        self._bot.stop()
        self._on_bot_done()

    def _on_bot_done(self):
        self._start_btn.config(state='normal')
        self._stop_btn.config(state='disabled')
        self._bot_status.config(text='Arrêté')

    # ---------------------------------------------------------------- #
    #  Hotkey Numpad 0                                                   #
    # ---------------------------------------------------------------- #

    def _start_hotkey_listener(self):
        def on_press(key):
            vk = getattr(key, 'vk', None)
            if vk == SAVE_HOTKEY_VK:
                self._win.after(0, self._add_waypoint_from_memory)

        self._hk = kb.Listener(on_press=on_press, suppress=False)
        self._hk.daemon = True
        self._hk.start()

    # ---------------------------------------------------------------- #

    def _on_close(self):
        self._bot.stop()
        self._mem.disconnect()
        self._hk.stop()
        self._win.destroy()
