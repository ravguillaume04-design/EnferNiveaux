"""
Bot de farming automatique pour GTA V / FiveM.
Navigation à pied par contrôle clavier avec détection d'obstacles.
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
#  Paramètres de navigation                                            #
# ------------------------------------------------------------------ #

REACH_DIST    = 2.5    # Mètres — distance pour considérer un WP atteint
CTRL_HZ       = 20     # Fréquence du boucle de contrôle (Hz)
CTRL_DT       = 1 / CTRL_HZ

TURN_DEAD     = 0.12   # Radians — zone morte avant de tourner (~7°)
TURN_SPRINT   = 0.5    # Radians — au-delà, on tourne sur place sans avancer

STUCK_WINDOW  = 3.0    # Secondes sans progrès → détection de blocage
STUCK_MIN_ADV = 0.6    # Mètres minimum pour ne pas être "bloqué"

# ------------------------------------------------------------------ #
#  Waypoint                                                            #
# ------------------------------------------------------------------ #

class Waypoint:
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
#  Navigator — contrôle clavier avec détection d'obstacles            #
# ------------------------------------------------------------------ #

class Navigator:
    """
    Pilote le joueur vers un waypoint via les touches WASD.
    Lit la position et le cap depuis la mémoire GTA V.
    Détecte les blocages et tente une manœuvre d'évitement.
    """

    def __init__(self, memory: GTAMemory, sprint: bool = False):
        self._mem    = memory
        self._sprint = sprint
        self._kb     = kb.Controller()
        self._active = False

    def go_to(self, wp: Waypoint, on_info=None) -> bool:
        """
        Navigue vers wp. Bloquant jusqu'à l'arrivée ou timeout.
        Retourne True si atteint, False si abandonné.
        """
        self._active = True
        result = self._navigate(wp, on_info)
        self._release_all()
        return result

    def stop(self):
        self._active = False

    # ---------------------------------------------------------------- #
    #  Boucle principale                                                 #
    # ---------------------------------------------------------------- #

    def _navigate(self, wp: Waypoint, on_info) -> bool:
        best_dist        = float('inf')
        stuck_timer      = time.perf_counter()
        avoidance_count  = 0
        MAX_AVOIDANCE    = 5

        while self._active:
            pos = self._mem.get_position()
            if not pos:
                time.sleep(0.1)
                continue

            dist = wp.distance_2d(pos[0], pos[1])

            # Arrivée
            if dist < REACH_DIST:
                return True

            # Progrès
            if dist < best_dist - STUCK_MIN_ADV:
                best_dist   = dist
                stuck_timer = time.perf_counter()

            # Détection de blocage
            if time.perf_counter() - stuck_timer > STUCK_WINDOW:
                avoidance_count += 1
                if avoidance_count > MAX_AVOIDANCE:
                    if on_info:
                        on_info(f'Blocage persistant — abandon après {MAX_AVOIDANCE} tentatives')
                    return False
                if on_info:
                    on_info(f'Obstacle détecté ({avoidance_count}/{MAX_AVOIDANCE}) — manœuvre...')
                self._avoid(wp, pos)
                stuck_timer = time.perf_counter()
                best_dist   = float('inf')
                continue

            # Cap voulu → cible
            dx = wp.x - pos[0]
            dy = wp.y - pos[1]
            target_hdg = math.atan2(dx, dy)   # GTA V : Y = Nord

            # Cap actuel depuis la mémoire
            current_hdg = self._mem.get_heading()

            # Erreur normalisée [-π, π]
            error = target_hdg - current_hdg
            error = (error + math.pi) % (2 * math.pi) - math.pi

            self._apply_controls(error)

            if on_info:
                on_info(f'→ {wp.name}  |  distance : {dist:.1f} m  |  erreur cap : {math.degrees(error):.0f}°')

            time.sleep(CTRL_DT)

        return False

    # ---------------------------------------------------------------- #
    #  Contrôles                                                         #
    # ---------------------------------------------------------------- #

    def _apply_controls(self, heading_error: float):
        """Applique WASD selon l'erreur de cap."""
        # Tourner à gauche / droite
        if heading_error > TURN_DEAD:
            self._press('a')
            self._release('d')
        elif heading_error < -TURN_DEAD:
            self._press('d')
            self._release('a')
        else:
            self._release('a')
            self._release('d')

        # Avancer seulement si l'erreur de cap est raisonnable
        if abs(heading_error) < TURN_SPRINT:
            if self._sprint:
                self._press(kb.Key.shift)
            self._press('w')
            self._release('s')
        else:
            # Trop de déviation → tourne sur place sans avancer
            self._release('w')
            self._release(kb.Key.shift)

    def _avoid(self, wp: Waypoint, current_pos):
        """
        Manœuvre d'évitement réactive :
        1. Reculer 0.6s
        2. Tourner de 60° dans la direction de la cible
        3. Avancer 1.2s
        """
        # Calcul du sens de rotation vers la cible
        dx = wp.x - current_pos[0]
        dy = wp.y - current_pos[1]
        target_hdg  = math.atan2(dx, dy)
        current_hdg = self._mem.get_heading()
        error       = (target_hdg - current_hdg + math.pi) % (2 * math.pi) - math.pi
        turn_key    = 'a' if error > 0 else 'd'

        self._release_all()

        # Reculer
        self._press('s')
        self._sleep(0.6)
        self._release('s')
        self._sleep(0.1)

        # Tourner
        self._press(turn_key)
        self._sleep(0.7)
        self._release(turn_key)
        self._sleep(0.1)

        # Avancer
        self._press('w')
        self._sleep(1.2)
        self._release('w')

    # ---------------------------------------------------------------- #
    #  Helpers clavier                                                   #
    # ---------------------------------------------------------------- #

    def _press(self, key):
        try:
            self._kb.press(key)
        except Exception:
            pass

    def _release(self, key):
        try:
            self._kb.release(key)
        except Exception:
            pass

    def _release_all(self):
        for k in ('w', 'a', 's', 'd', kb.Key.shift):
            self._release(k)

    def _sleep(self, seconds: float):
        end = time.perf_counter() + seconds
        while self._active and time.perf_counter() < end:
            time.sleep(0.02)


# ------------------------------------------------------------------ #
#  Bot                                                                 #
# ------------------------------------------------------------------ #

class Bot:
    def __init__(self, memory: GTAMemory):
        self._mem       = memory
        self._kb        = kb.Controller()
        self._nav       = None
        self._running   = False
        self._thread    = None

    @property
    def is_running(self):
        return self._running

    def start(self, waypoints, loop=True, delay=2.0, sprint=False,
              on_status=None, on_done=None):
        if self._running or not waypoints:
            return
        self._running = True
        self._nav     = Navigator(self._mem, sprint=sprint)
        self._thread  = threading.Thread(
            target=self._run,
            args=(waypoints, loop, delay, on_status, on_done),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._nav:
            self._nav.stop()
        if self._thread:
            self._thread.join(timeout=4)
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
                    on_status(f'Cycle {cycle}  —  {wp.name}  ({i+1}/{len(waypoints)})')

                reached = self._nav.go_to(
                    wp,
                    on_info=lambda msg: on_status(msg) if on_status else None,
                )

                if not reached or not self._running:
                    break

                # Action à l'arrivée
                if wp.action:
                    time.sleep(0.35)
                    self._press_key(wp.action)

                # Pause entre waypoints
                self._wait(delay, on_status)

            if not loop:
                self._running = False

        if on_done:
            on_done()

    def _press_key(self, key: str):
        try:
            k = kb.KeyCode.from_char(key) if len(key) == 1 else kb.Key[key]
            self._kb.press(k)
            time.sleep(0.2)
            self._kb.release(k)
        except Exception:
            pass

    def _wait(self, seconds, on_status):
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while self._running and time.perf_counter() < end:
            remaining = end - time.perf_counter()
            if on_status:
                on_status(f'Attente {remaining:.0f}s avant prochain waypoint...')
            time.sleep(min(remaining, 0.5))


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

        self._status_var = tk.StringVar(value='Non connecté')
        self._loop_var   = tk.BooleanVar(value=True)
        self._sprint_var = tk.BooleanVar(value=False)
        self._delay_min  = tk.IntVar(value=0)
        self._delay_sec  = tk.IntVar(value=2)
        self._action_var = tk.StringVar(value='e')

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
        tk.Label(hdr, text='Numpad 0 — sauvegarder position actuelle',
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
        wf = tk.LabelFrame(self._win, text='Waypoints  (Numpad 0 = ajouter)', **P)
        wf.pack(fill='x', **P)

        lf = tk.Frame(wf)
        lf.pack(fill='x')
        sb = tk.Scrollbar(lf, orient='vertical')
        self._listbox = tk.Listbox(lf, height=6, width=38,
                                    yscrollcommand=sb.set,
                                    selectmode='single', font=('Courier', 9))
        sb.config(command=self._listbox.yview)
        self._listbox.pack(side='left', fill='x', expand=True)
        sb.pack(side='right', fill='y')

        br = tk.Frame(wf)
        br.pack(fill='x', pady=(4, 0))
        for text, cmd in [('▲', self._wp_up), ('▼', self._wp_down),
                          ('✎', self._wp_rename), ('✕', self._wp_delete)]:
            tk.Button(br, text=text, command=cmd, width=5).pack(side='left', padx=2)

        # Action à l'arrivée
        af = tk.LabelFrame(self._win, text="Action à l'arrivée (prochain WP)", **P)
        af.pack(fill='x', **P)
        ar = tk.Frame(af)
        ar.pack(fill='x')
        for label, val in [('Aucune', ''), ('E  (récolter/interagir)', 'e'),
                           ('F  (entrer véhicule)', 'f')]:
            tk.Radiobutton(ar, text=label, variable=self._action_var,
                           value=val, font=('Helvetica', 9)).pack(side='left', padx=3)

        # Fichier waypoints
        fr = tk.Frame(self._win)
        fr.pack(pady=2)
        tk.Button(fr, text='Sauvegarder WPs', width=15,
                  command=self._save_wps).pack(side='left', padx=4)
        tk.Button(fr, text='Charger WPs', width=13,
                  command=self._load_wps).pack(side='left', padx=4)

        ttk.Separator(self._win).pack(fill='x', padx=8, pady=4)

        # Paramètres
        pf = tk.LabelFrame(self._win, text='Paramètres de navigation', **P)
        pf.pack(fill='x', **P)

        dr = tk.Frame(pf)
        dr.pack(anchor='w')
        tk.Label(dr, text='Pause entre waypoints :', font=('Helvetica', 9)).pack(side='left')
        tk.Spinbox(dr, from_=0, to=59, textvariable=self._delay_min,
                   width=3, font=('Helvetica', 9)).pack(side='left', padx=(4, 0))
        tk.Label(dr, text='min', font=('Helvetica', 9)).pack(side='left', padx=(2, 6))
        tk.Spinbox(dr, from_=0, to=59, textvariable=self._delay_sec,
                   width=3, font=('Helvetica', 9)).pack(side='left')
        tk.Label(dr, text='sec', font=('Helvetica', 9)).pack(side='left', padx=(2, 0))

        opts = tk.Frame(pf)
        opts.pack(anchor='w', pady=(4, 0))
        tk.Checkbutton(opts, text='Sprint (Shift)',
                       variable=self._sprint_var, font=('Helvetica', 9)).pack(side='left')
        tk.Checkbutton(opts, text='Boucle infinie',
                       variable=self._loop_var, font=('Helvetica', 9)).pack(side='left', padx=10)

        # Contrôles bot
        cr = tk.Frame(self._win)
        cr.pack(pady=8)
        self._start_btn = tk.Button(cr, text='▶  Démarrer', width=14,
                                     bg='#1e8449', fg='white', relief='flat',
                                     font=('Helvetica', 11), command=self._start_bot)
        self._start_btn.pack(side='left', padx=4)
        self._stop_btn = tk.Button(cr, text='⏹  Arrêter', width=12,
                                    bg='#922b21', fg='white', relief='flat',
                                    font=('Helvetica', 11), command=self._stop_bot,
                                    state='disabled')
        self._stop_btn.pack(side='left', padx=4)

        self._info_label = tk.Label(self._win, text='', fg='#1a5276',
                                     font=('Helvetica', 9), wraplength=320)
        self._info_label.pack(pady=(0, 6))

    # ---------------------------------------------------------------- #
    #  Connexion                                                         #
    # ---------------------------------------------------------------- #

    def _connect(self):
        try:
            self._mem.connect()
            pos = self._mem.get_position()
            hdg = math.degrees(self._mem.get_heading())
            if pos:
                self._status_var.set(
                    f'Connecté  •  ({pos[0]:.0f}, {pos[1]:.0f})  cap {hdg:.0f}°')
                self._conn_label.config(fg='#1e8449')
            else:
                self._status_var.set('Connecté  •  position illisible')
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
        name   = f'WP {len(self._wps) + 1}'
        action = self._action_var.get()
        wp     = Waypoint(name, pos[0], pos[1], pos[2], action)
        self._wps.append(wp)
        self._refresh_list()
        self._status_var.set(
            f'Connecté  •  WP ajouté : ({pos[0]:.1f}, {pos[1]:.1f})')

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
            filetypes=[('JSON', '*.json')],
            parent=self._win,
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([wp.to_dict() for wp in self._wps], f, indent=2)

    def _load_wps(self):
        path = filedialog.askopenfilename(
            filetypes=[('JSON', '*.json')],
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
            self._win.after(0, lambda m=msg: self._info_label.config(text=m))

        def on_done():
            self._win.after(0, self._on_bot_done)

        self._bot.start(
            self._wps,
            loop=self._loop_var.get(),
            delay=delay,
            sprint=self._sprint_var.get(),
            on_status=on_status,
            on_done=on_done,
        )

    def _stop_bot(self):
        self._bot.stop()
        self._on_bot_done()

    def _on_bot_done(self):
        self._start_btn.config(state='normal')
        self._stop_btn.config(state='disabled')
        self._info_label.config(text='Arrêté')

    # ---------------------------------------------------------------- #
    #  Hotkey Numpad 0                                                   #
    # ---------------------------------------------------------------- #

    def _start_hotkey_listener(self):
        def on_press(key):
            if getattr(key, 'vk', None) == SAVE_HOTKEY_VK:
                self._win.after(0, self._add_waypoint_from_memory)
        self._hk = kb.Listener(on_press=on_press, suppress=False)
        self._hk.daemon = True
        self._hk.start()

    def _on_close(self):
        self._bot.stop()
        self._mem.disconnect()
        self._hk.stop()
        self._win.destroy()
