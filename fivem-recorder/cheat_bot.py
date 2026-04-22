"""
Bot de farming automatique pour GTA V / FiveM — clavier AZERTY (ZQSD).
Navigation à pied avec détection d'obstacles et glisser-déposer configurable.
"""
import math
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pynput import keyboard as kb, mouse as ms

from gta_memory import GTAMemory

# Numpad hotkeys
HK_ADD_WP  = 96   # Numpad 0 — ajouter waypoint
HK_DRAG_SRC = 97  # Numpad 1 — enregistrer position source du glisser
HK_DRAG_DST = 98  # Numpad 2 — enregistrer position destination du glisser

# ------------------------------------------------------------------ #
#  Paramètres de navigation                                            #
# ------------------------------------------------------------------ #

REACH_DIST   = 2.5    # Mètres pour considérer un WP atteint
CTRL_HZ      = 20     # Fréquence de la boucle de contrôle
CTRL_DT      = 1 / CTRL_HZ
TURN_DEAD    = 0.12   # Radians — zone morte (~7°)
TURN_SPRINT  = 0.5    # Radians — au-delà : tourne sur place sans avancer
STUCK_WINDOW = 3.0    # Secondes sans progrès → blocage
STUCK_MIN_ADV= 0.6    # Mètres minimum de progrès


# ------------------------------------------------------------------ #
#  Waypoint                                                            #
# ------------------------------------------------------------------ #

class Waypoint:
    def __init__(self, name='Waypoint', x=0.0, y=0.0, z=0.0, action=''):
        self.name   = name
        self.x      = x
        self.y      = y
        self.z      = z
        # action : '' | 'e' | 'g' | 'k' | 'drag'
        self.action = action

    def distance_2d(self, x, y):
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    def to_dict(self):
        return {'name': self.name, 'x': self.x, 'y': self.y,
                'z': self.z, 'action': self.action}

    @classmethod
    def from_dict(cls, d):
        return cls(d['name'], d['x'], d['y'], d['z'], d.get('action', ''))

    def __str__(self):
        labels = {'e': 'E', 'g': 'G', 'k': 'K', 'drag': 'GLISSER', '': '—'}
        act = labels.get(self.action, self.action)
        return f'{self.name}  ({self.x:.1f}, {self.y:.1f})  [{act}]'


# ------------------------------------------------------------------ #
#  Navigator — ZQSD, cap mémoire, détection obstacles                 #
# ------------------------------------------------------------------ #

class Navigator:
    def __init__(self, memory: GTAMemory, sprint: bool = False):
        self._mem    = memory
        self._sprint = sprint
        self._kb     = kb.Controller()
        self._active = False

    def go_to(self, wp: Waypoint, on_info=None) -> bool:
        self._active = True
        result = self._navigate(wp, on_info)
        self._release_all()
        return result

    def stop(self):
        self._active = False

    # ---------------------------------------------------------------- #

    def _navigate(self, wp: Waypoint, on_info) -> bool:
        best_dist       = float('inf')
        stuck_timer     = time.perf_counter()
        avoidance_count = 0
        MAX_AVOID       = 5

        while self._active:
            pos = self._mem.get_position()
            if not pos:
                time.sleep(0.1)
                continue

            dist = wp.distance_2d(pos[0], pos[1])

            if dist < REACH_DIST:
                return True

            # Progrès ?
            if dist < best_dist - STUCK_MIN_ADV:
                best_dist   = dist
                stuck_timer = time.perf_counter()

            # Blocage ?
            if time.perf_counter() - stuck_timer > STUCK_WINDOW:
                avoidance_count += 1
                if avoidance_count > MAX_AVOID:
                    if on_info:
                        on_info(f'Blocage persistant — waypoint ignoré')
                    return False
                if on_info:
                    on_info(f'Obstacle ({avoidance_count}/{MAX_AVOID}) — manœuvre...')
                self._avoid(wp, pos)
                stuck_timer = time.perf_counter()
                best_dist   = float('inf')
                continue

            # Cap voulu
            dx = wp.x - pos[0]
            dy = wp.y - pos[1]
            target_hdg  = math.atan2(dx, dy)
            current_hdg = self._mem.get_heading()

            error = target_hdg - current_hdg
            error = (error + math.pi) % (2 * math.pi) - math.pi

            self._apply_controls(error)

            if on_info:
                on_info(
                    f'→ {wp.name}  |  {dist:.1f} m  |  cap : {math.degrees(error):+.0f}°'
                )
            time.sleep(CTRL_DT)

        return False

    def _apply_controls(self, error: float):
        # Rotation
        if error > TURN_DEAD:
            self._press('d')    # droite = sens horaire = augmente le cap
            self._release('q')
        elif error < -TURN_DEAD:
            self._press('q')    # gauche = sens anti-horaire
            self._release('d')
        else:
            self._release('q')
            self._release('d')

        # Avance seulement si cap acceptable
        if abs(error) < TURN_SPRINT:
            if self._sprint:
                self._press(kb.Key.shift)
            self._press('z')
            self._release('s')
        else:
            self._release('z')
            self._release(kb.Key.shift)

    def _avoid(self, wp: Waypoint, pos):
        dx = wp.x - pos[0]
        dy = wp.y - pos[1]
        target_hdg  = math.atan2(dx, dy)
        current_hdg = self._mem.get_heading()
        error       = (target_hdg - current_hdg + math.pi) % (2 * math.pi) - math.pi
        turn_key    = 'd' if error > 0 else 'q'

        self._release_all()
        self._press('s');  self._sleep(0.6);  self._release('s')
        self._sleep(0.1)
        self._press(turn_key); self._sleep(0.7); self._release(turn_key)
        self._sleep(0.1)
        self._press('z');  self._sleep(1.2);  self._release('z')

    def _press(self, k):
        try:
            self._kb.press(k)
        except Exception:
            pass

    def _release(self, k):
        try:
            self._kb.release(k)
        except Exception:
            pass

    def _release_all(self):
        for k in ('z', 'q', 's', 'd', kb.Key.shift):
            self._release(k)

    def _sleep(self, seconds):
        end = time.perf_counter() + seconds
        while self._active and time.perf_counter() < end:
            time.sleep(0.02)


# ------------------------------------------------------------------ #
#  Bot                                                                 #
# ------------------------------------------------------------------ #

class Bot:
    def __init__(self, memory: GTAMemory):
        self._mem     = memory
        self._kb      = kb.Controller()
        self._mouse   = ms.Controller()
        self._nav     = None
        self._running = False
        self._thread  = None

    @property
    def is_running(self):
        return self._running

    def start(self, waypoints, loop=True, delay=2.0, sprint=False,
              drag_src=None, drag_dst=None, drag_repeat=1,
              on_status=None, on_done=None):
        if self._running or not waypoints:
            return
        self._running   = True
        self._drag_src  = drag_src
        self._drag_dst  = drag_dst
        self._drag_rep  = max(1, drag_repeat)
        self._nav       = Navigator(self._mem, sprint=sprint)
        self._thread    = threading.Thread(
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
                    on_info=lambda m: on_status(m) if on_status else None,
                )
                if not reached or not self._running:
                    break

                time.sleep(0.35)
                self._execute_action(wp.action, on_status)
                self._wait(delay, on_status)

            if not loop:
                self._running = False

        if on_done:
            on_done()

    # ---------------------------------------------------------------- #
    #  Actions                                                           #
    # ---------------------------------------------------------------- #

    def _execute_action(self, action, on_status=None):
        if not action:
            return
        if action == 'drag':
            self._do_drag(on_status)
        else:
            self._tap(action)

    def _tap(self, key: str):
        try:
            k = kb.KeyCode.from_char(key) if len(key) == 1 else kb.Key[key]
            self._kb.press(k)
            time.sleep(0.2)
            self._kb.release(k)
        except Exception:
            pass

    def _do_drag(self, on_status=None):
        """Presse E pour ouvrir le menu puis glisse les items vers l'inventaire."""
        if not self._drag_src or not self._drag_dst:
            if on_status:
                on_status('⚠ Positions de glisser non configurées')
            return

        # Ouvrir le menu de transformation
        self._tap('e')
        time.sleep(1.5)

        for rep in range(self._drag_rep):
            if not self._running:
                break
            if on_status:
                on_status(f'Glisser {rep+1}/{self._drag_rep}...')

            src = self._drag_src
            dst = self._drag_dst

            self._mouse.position = src
            time.sleep(0.2)
            self._mouse.press(ms.Button.left)
            time.sleep(0.1)

            # Glisser en douceur
            steps = 25
            for i in range(steps + 1):
                t   = i / steps
                x   = int(src[0] + (dst[0] - src[0]) * t)
                y   = int(src[1] + (dst[1] - src[1]) * t)
                self._mouse.position = (x, y)
                time.sleep(0.012)

            time.sleep(0.1)
            self._mouse.release(ms.Button.left)
            time.sleep(0.4)

    def _wait(self, seconds, on_status):
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while self._running and time.perf_counter() < end:
            rem = end - time.perf_counter()
            if on_status:
                on_status(f'Pause : {rem:.0f}s...')
            time.sleep(min(rem, 0.5))


# ================================================================== #
#  Fenêtre du bot                                                      #
# ================================================================== #

class BotWindow:
    def __init__(self, parent: tk.Tk):
        self._parent    = parent
        self._mem       = GTAMemory()
        self._bot       = Bot(self._mem)
        self._wps: list[Waypoint] = []
        self._drag_src  = None
        self._drag_dst  = None

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
        self._sprint_var  = tk.BooleanVar(value=False)
        self._delay_min   = tk.IntVar(value=0)
        self._delay_sec   = tk.IntVar(value=2)
        self._action_var  = tk.StringVar(value='e')
        self._drag_rep    = tk.IntVar(value=1)
        self._src_var     = tk.StringVar(value='Non défini')
        self._dst_var     = tk.StringVar(value='Non défini')

        self._build_ui()
        self._start_hotkeys()

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
        tk.Label(hdr,
                 text='Num0=WP   Num1=source glisser   Num2=destination glisser',
                 bg='#1a1a2e', fg='#888', font=('Helvetica', 7)).pack()

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
        wf = tk.LabelFrame(self._win, text='Waypoints', **P)
        wf.pack(fill='x', **P)
        lf = tk.Frame(wf)
        lf.pack(fill='x')
        sb = tk.Scrollbar(lf, orient='vertical')
        self._listbox = tk.Listbox(lf, height=5, width=40, yscrollcommand=sb.set,
                                    selectmode='single', font=('Courier', 9))
        sb.config(command=self._listbox.yview)
        self._listbox.pack(side='left', fill='x', expand=True)
        sb.pack(side='right', fill='y')
        br = tk.Frame(wf)
        br.pack(fill='x', pady=(3, 0))
        for txt, cmd in [('▲', self._wp_up), ('▼', self._wp_down),
                         ('✎ Renommer', self._wp_rename), ('✕ Supprimer', self._wp_delete)]:
            tk.Button(br, text=txt, command=cmd, padx=4).pack(side='left', padx=2)

        # Action à l'arrivée
        af = tk.LabelFrame(self._win, text="Action à l'arrivée (prochain WP ajouté)", **P)
        af.pack(fill='x', **P)
        acts = [
            ('Aucune',              ''),
            ('E  (récolter)',       'e'),
            ('G  (véhicule)',       'g'),
            ('K  (inventaire)',     'k'),
            ('Glisser → inventaire','drag'),
        ]
        ar = tk.Frame(af)
        ar.pack(fill='x')
        for i, (label, val) in enumerate(acts):
            tk.Radiobutton(ar, text=label, variable=self._action_var, value=val,
                           font=('Helvetica', 9)).grid(row=i//3, column=i%3,
                           sticky='w', padx=4)

        # Config glisser-déposer
        df = tk.LabelFrame(self._win, text='Configuration du glisser (pour action GLISSER)', **P)
        df.pack(fill='x', **P)

        for label, var, key_hint in [
            ('Source (item)  :', self._src_var, 'Num 1 en jeu'),
            ('Destination    :', self._dst_var, 'Num 2 en jeu'),
        ]:
            row = tk.Frame(df)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=label, width=16, anchor='w',
                     font=('Helvetica', 9)).pack(side='left')
            tk.Label(row, textvariable=var, fg='#1a5276',
                     font=('Courier', 9)).pack(side='left')
            tk.Label(row, text=f'  ← {key_hint}', fg='gray',
                     font=('Helvetica', 8)).pack(side='left')

        rep_row = tk.Frame(df)
        rep_row.pack(anchor='w', pady=(4, 0))
        tk.Label(rep_row, text='Répétitions du glisser :', font=('Helvetica', 9)).pack(side='left')
        tk.Spinbox(rep_row, from_=1, to=20, textvariable=self._drag_rep,
                   width=3, font=('Helvetica', 9)).pack(side='left', padx=6)

        tk.Button(df, text='Effacer positions', command=self._clear_drag,
                  font=('Helvetica', 8)).pack(anchor='e', pady=2)

        # Fichier
        fr = tk.Frame(self._win)
        fr.pack(pady=3)
        tk.Button(fr, text='Sauvegarder WPs', width=15,
                  command=self._save_wps).pack(side='left', padx=4)
        tk.Button(fr, text='Charger WPs', width=13,
                  command=self._load_wps).pack(side='left', padx=4)

        ttk.Separator(self._win).pack(fill='x', padx=8, pady=4)

        # Paramètres
        pf = tk.LabelFrame(self._win, text='Paramètres', **P)
        pf.pack(fill='x', **P)
        dr = tk.Frame(pf)
        dr.pack(anchor='w')
        tk.Label(dr, text='Pause entre WPs :', font=('Helvetica', 9)).pack(side='left')
        tk.Spinbox(dr, from_=0, to=59, textvariable=self._delay_min,
                   width=3, font=('Helvetica', 9)).pack(side='left', padx=(4, 0))
        tk.Label(dr, text='min', font=('Helvetica', 9)).pack(side='left', padx=(2, 6))
        tk.Spinbox(dr, from_=0, to=59, textvariable=self._delay_sec,
                   width=3, font=('Helvetica', 9)).pack(side='left')
        tk.Label(dr, text='sec', font=('Helvetica', 9)).pack(side='left', padx=(2, 0))
        opts = tk.Frame(pf)
        opts.pack(anchor='w', pady=(4, 0))
        tk.Checkbutton(opts, text='Sprint (Shift)', variable=self._sprint_var,
                       font=('Helvetica', 9)).pack(side='left')
        tk.Checkbutton(opts, text='Boucle infinie', variable=self._loop_var,
                       font=('Helvetica', 9)).pack(side='left', padx=10)

        # Démarrer / Arrêter
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
                                     font=('Helvetica', 9), wraplength=340)
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
                self._status_var.set(f'Connecté  ({pos[0]:.0f}, {pos[1]:.0f})  cap {hdg:.0f}°')
                self._conn_label.config(fg='#1e8449')
            else:
                self._status_var.set('Connecté — position illisible')
                self._conn_label.config(fg='orange')
        except RuntimeError as e:
            self._status_var.set(str(e).split('\n')[0])
            self._conn_label.config(fg='red')
            messagebox.showerror('Erreur', str(e), parent=self._win)

    # ---------------------------------------------------------------- #
    #  Waypoints                                                         #
    # ---------------------------------------------------------------- #

    def _add_wp(self):
        if not self._mem.connected:
            return
        pos = self._mem.get_position()
        if not pos:
            return
        wp = Waypoint(f'WP {len(self._wps)+1}', pos[0], pos[1], pos[2],
                      self._action_var.get())
        self._wps.append(wp)
        self._refresh_list()
        self._status_var.set(f'WP ajouté : {wp.name}  ({pos[0]:.1f}, {pos[1]:.1f})')

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for wp in self._wps:
            self._listbox.insert(tk.END, str(wp))

    def _sel(self):
        s = self._listbox.curselection()
        return s[0] if s else None

    def _wp_up(self):
        i = self._sel()
        if i is None or i == 0:
            return
        self._wps[i-1], self._wps[i] = self._wps[i], self._wps[i-1]
        self._refresh_list(); self._listbox.select_set(i-1)

    def _wp_down(self):
        i = self._sel()
        if i is None or i >= len(self._wps)-1:
            return
        self._wps[i], self._wps[i+1] = self._wps[i+1], self._wps[i]
        self._refresh_list(); self._listbox.select_set(i+1)

    def _wp_rename(self):
        i = self._sel()
        if i is None:
            return
        w = tk.Toplevel(self._win)
        w.title('Renommer'); w.attributes('-topmost', True)
        tk.Label(w, text='Nouveau nom :').pack(padx=10, pady=(10, 2))
        v = tk.StringVar(value=self._wps[i].name)
        e = tk.Entry(w, textvariable=v, width=20); e.pack(padx=10); e.focus()
        def ok():
            self._wps[i].name = v.get(); self._refresh_list(); w.destroy()
        tk.Button(w, text='OK', command=ok).pack(pady=8)
        w.bind('<Return>', lambda _: ok())

    def _wp_delete(self):
        i = self._sel()
        if i is not None:
            self._wps.pop(i); self._refresh_list()

    def _save_wps(self):
        if not self._wps:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json',
                                             filetypes=[('JSON','*.json')],
                                             parent=self._win)
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([wp.to_dict() for wp in self._wps], f, indent=2)

    def _load_wps(self):
        path = filedialog.askopenfilename(filetypes=[('JSON','*.json')], parent=self._win)
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                self._wps = [Waypoint.from_dict(d) for d in json.load(f)]
            self._refresh_list()

    # ---------------------------------------------------------------- #
    #  Glisser-déposer                                                   #
    # ---------------------------------------------------------------- #

    def _record_drag_src(self):
        mouse_ctrl = ms.Controller()
        pos = mouse_ctrl.position
        self._drag_src = pos
        self._src_var.set(f'{pos[0]}, {pos[1]}')

    def _record_drag_dst(self):
        mouse_ctrl = ms.Controller()
        pos = mouse_ctrl.position
        self._drag_dst = pos
        self._dst_var.set(f'{pos[0]}, {pos[1]}')

    def _clear_drag(self):
        self._drag_src = None
        self._drag_dst = None
        self._src_var.set('Non défini')
        self._dst_var.set('Non défini')

    # ---------------------------------------------------------------- #
    #  Bot                                                               #
    # ---------------------------------------------------------------- #

    def _start_bot(self):
        if not self._mem.connected:
            messagebox.showwarning('Non connecté', 'Connectez-vous d\'abord.', parent=self._win)
            return
        if not self._wps:
            messagebox.showwarning('Aucun waypoint', 'Ajoutez au moins un waypoint.', parent=self._win)
            return
        has_drag = any(wp.action == 'drag' for wp in self._wps)
        if has_drag and (not self._drag_src or not self._drag_dst):
            messagebox.showwarning('Glisser non configuré',
                                   'Configurez la source (Num 1) et la destination (Num 2) du glisser.',
                                   parent=self._win)
            return

        delay = self._delay_min.get() * 60 + self._delay_sec.get()
        self._start_btn.config(state='disabled')
        self._stop_btn.config(state='normal')

        def on_status(m):
            self._win.after(0, lambda msg=m: self._info_label.config(text=msg))

        self._bot.start(
            self._wps,
            loop=self._loop_var.get(),
            delay=delay,
            sprint=self._sprint_var.get(),
            drag_src=self._drag_src,
            drag_dst=self._drag_dst,
            drag_repeat=self._drag_rep.get(),
            on_status=on_status,
            on_done=lambda: self._win.after(0, self._on_done),
        )

    def _stop_bot(self):
        self._bot.stop(); self._on_done()

    def _on_done(self):
        self._start_btn.config(state='normal')
        self._stop_btn.config(state='disabled')
        self._info_label.config(text='Arrêté')

    # ---------------------------------------------------------------- #
    #  Hotkeys globaux (Numpad 0/1/2)                                    #
    # ---------------------------------------------------------------- #

    def _start_hotkeys(self):
        def on_press(key):
            vk = getattr(key, 'vk', None)
            if vk == HK_ADD_WP:
                self._win.after(0, self._add_wp)
            elif vk == HK_DRAG_SRC:
                self._win.after(0, self._record_drag_src)
            elif vk == HK_DRAG_DST:
                self._win.after(0, self._record_drag_dst)

        self._hk = kb.Listener(on_press=on_press, suppress=False)
        self._hk.daemon = True
        self._hk.start()

    def _on_close(self):
        self._bot.stop()
        self._mem.disconnect()
        self._hk.stop()
        self._win.destroy()
