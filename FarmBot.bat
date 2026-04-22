@echo off & py --version >nul 2>&1 || (echo ERREUR : Python manquant. Telechargez-le sur python.org & pause & exit /b 1) & py -m pip install pynput psutil --quiet & py -x "%~f0" & pause & exit /b
# -*- coding: utf-8 -*-
# FarmBot - fichier autonome, double-cliquez pour lancer
import sys, os, tempfile, subprocess

_src = open(__file__, 'r', encoding='utf-8', errors='replace').read()
_parts = _src.split('\n' + '# ===FARMBOT_SEP===')

_files = {}
for _part in _parts[1:]:
    _lines = _part.split('\n', 1)
    _name  = _lines[0].strip()
    _code  = _lines[1] if len(_lines) > 1 else ''
    _files[_name] = _code

_d = tempfile.mkdtemp(prefix='farmbot_')
for _name, _code in _files.items():
    with open(os.path.join(_d, _name), 'w', encoding='utf-8') as _f:
        _f.write(_code)

try:
    subprocess.run([sys.executable, os.path.join(_d, 'fivem_recorder.py')], cwd=_d)
finally:
    import shutil
    shutil.rmtree(_d, ignore_errors=True)

# ===FARMBOT_SEP===gta_memory.py
"""
Lecture mémoire FiveM / GTA V — accès lecture seule pour éviter les crashs.
Utilise VirtualQueryEx pour ne scanner que les pages mémoire accessibles.
"""
import ctypes
import ctypes.wintypes
import struct
import math

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ------------------------------------------------------------------ #
#  Constantes Windows                                                  #
# ------------------------------------------------------------------ #

# Lecture seule — pas d'écriture pour éviter la détection FiveM
PROCESS_VM_READ    = 0x0010
PROCESS_QUERY_INFO = 0x0400

TH32CS_SNAPMODULE   = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

MEM_COMMIT   = 0x1000
PAGE_EXECUTE_READ            = 0x20
PAGE_EXECUTE_READWRITE       = 0x40
PAGE_EXECUTE_WRITECOPY       = 0x80
PAGE_READONLY                = 0x02
PAGE_READWRITE               = 0x04
PAGE_WRITECOPY               = 0x08
READABLE_PAGES = (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
                  PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class _MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize',       ctypes.c_ulong),
        ('th32ModuleID', ctypes.c_ulong),
        ('th32ProcessID', ctypes.c_ulong),
        ('GlblcntUsage', ctypes.c_ulong),
        ('ProccntUsage', ctypes.c_ulong),
        ('modBaseAddr',  ctypes.c_size_t),
        ('modBaseSize',  ctypes.c_ulong),
        ('hModule',      ctypes.c_void_p),
        ('szModule',     ctypes.c_char * 256),
        ('szExePath',    ctypes.c_char * 260),
    ]


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress',       ctypes.c_size_t),
        ('AllocationBase',    ctypes.c_size_t),
        ('AllocationProtect', ctypes.c_ulong),
        ('RegionSize',        ctypes.c_size_t),
        ('State',             ctypes.c_ulong),
        ('Protect',           ctypes.c_ulong),
        ('Type',              ctypes.c_ulong),
    ]


# ------------------------------------------------------------------ #
#  Noms de processus — détection partielle pour FiveM                  #
# ------------------------------------------------------------------ #

# FiveM lance GTA V sous différents noms selon le build.
# On teste plusieurs patterns, du plus spécifique au plus large.
GTA_PARTIAL_NAMES = [
    'GTAProcess',   # FiveM_b3095_GTAProcess.exe, FiveM_b2699_GTAProcess.exe
    'GTA5.exe',     # GTA V standalone
    'GTA5',         # variante sans extension
    'FiveM_b',      # certains builds plus récents
]

# Mots-clés pour le diagnostic quand rien n'est trouvé
_DIAG_KEYWORDS = ['gta', 'fivem', 'citizen', 'rage', 'rockstar']

# ------------------------------------------------------------------ #
#  Patterns mémoire (sources publiques GTA V modding)                  #
# ------------------------------------------------------------------ #

PED_PATTERNS = [
    (b'\x48\x8B\x05\x00\x00\x00\x00\xF3\x0F\x58\x8B', 'xxx????xxxx'),
    (b'\x48\x8B\x05\x00\x00\x00\x00\x45\x00\x00\x00\x00\x0F\x84', 'xxx????x????xx'),
    (b'\x48\x8B\x05\x00\x00\x00\x00\x8B\x50\x18', 'xxx????xxx'),
]

# Offsets dans la matrice de transformation CPed (colonne-major)
MATRIX_OFFSET = 0x90
FWD_X = MATRIX_OFFSET + 0x10   # Vecteur forward X
FWD_Y = MATRIX_OFFSET + 0x14   # Vecteur forward Y
POS_X = MATRIX_OFFSET + 0x30   # Position X
POS_Y = MATRIX_OFFSET + 0x34   # Position Y
POS_Z = MATRIX_OFFSET + 0x38   # Position Z

CHUNK = 4096


# ================================================================== #

class GTAMemory:
    def __init__(self):
        self._handle   = None
        self._pid      = None
        self._base     = None
        self._ped_gptr = None

    # ---------------------------------------------------------------- #
    #  Connexion                                                         #
    # ---------------------------------------------------------------- #

    def connect(self):
        if not _PSUTIL:
            raise RuntimeError(
                'psutil manquant.\nLancez : py -m pip install psutil')

        pid, name = self._find_process()
        if not pid:
            # Diagnostic : liste les processus GTA/FiveM visibles
            candidates = self._list_candidates()
            hint = ''
            if candidates:
                hint = ('\n\nProcessus GTA/FiveM detectes sur votre PC :\n'
                        + '\n'.join(f'  - {n}' for n in candidates[:12])
                        + '\n\nCopier ces noms et signaler le probleme.')
            else:
                hint = '\n\nAucun processus GTA ou FiveM detecte.'
            raise RuntimeError(
                'FiveM introuvable.' + hint + '\n\n'
                'Verifiez : FiveM est lance ET vous etes dans un serveur (pas le menu).')

        # Lecture seule uniquement — évite la détection anti-cheat
        handle = _k32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFO, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            raise RuntimeError(
                f'Accès refusé (erreur {err}).\n'
                'Relancez lancer.bat en tant qu\'Administrateur.')

        self._handle = handle
        self._pid    = pid

        self._base = self._module_base(name)
        if not self._base:
            raise RuntimeError(
                'Base du module introuvable.\n'
                'Êtes-vous bien en jeu (pas dans le menu principal) ?')

        self._ped_gptr = self._find_ped_ptr()
        if not self._ped_gptr:
            raise RuntimeError(
                'Pattern mémoire non trouvé.\n'
                'Essayez de charger complètement la partie puis reconnectez.')

    def disconnect(self):
        if self._handle:
            _k32.CloseHandle(self._handle)
            self._handle    = None
            self._ped_gptr  = None

    @property
    def connected(self):
        return self._handle is not None and self._ped_gptr is not None

    # ---------------------------------------------------------------- #
    #  API publique                                                       #
    # ---------------------------------------------------------------- #

    def get_position(self):
        """Retourne (x, y, z) ou None."""
        ped = self._ped()
        if not ped:
            return None
        x = self._rf(ped + POS_X)
        y = self._rf(ped + POS_Y)
        z = self._rf(ped + POS_Z)
        return (x, y, z) if (x or y or z) else None

    def get_heading(self):
        """Retourne le cap en radians (0=Nord, π/2=Est)."""
        ped = self._ped()
        if not ped:
            return 0.0
        fx = self._rf(ped + FWD_X)
        fy = self._rf(ped + FWD_Y)
        return math.atan2(fx, fy)

    # ---------------------------------------------------------------- #
    #  Lecture mémoire                                                    #
    # ---------------------------------------------------------------- #

    def _rb(self, addr, size):
        buf  = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        _k32.ReadProcessMemory(
            self._handle, ctypes.c_void_p(addr),
            buf, size, ctypes.byref(read))
        return buf.raw[:read.value]

    def _ri32(self, addr):
        d = self._rb(addr, 4)
        return struct.unpack('<i', d)[0] if len(d) >= 4 else 0

    def _ru64(self, addr):
        d = self._rb(addr, 8)
        return struct.unpack('<Q', d)[0] if len(d) >= 8 else 0

    def _rf(self, addr):
        d = self._rb(addr, 4)
        return struct.unpack('<f', d)[0] if len(d) >= 4 else 0.0

    # ---------------------------------------------------------------- #
    #  Processus & patterns                                              #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _find_process():
        """Trouve FiveM par correspondance partielle du nom de processus."""
        for p in psutil.process_iter(['name', 'pid']):
            name = p.info.get('name') or ''
            for pattern in GTA_PARTIAL_NAMES:
                if pattern.lower() in name.lower():
                    return p.info['pid'], name
        return None, None

    @staticmethod
    def _list_candidates():
        """Retourne les noms de processus GTA/FiveM détectés (diagnostic)."""
        seen = []
        try:
            for p in psutil.process_iter(['name']):
                name = p.info.get('name') or ''
                if any(kw in name.lower() for kw in _DIAG_KEYWORDS):
                    if name not in seen:
                        seen.append(name)
        except Exception:
            pass
        return seen

    def _module_base(self, module_name):
        snap = _k32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self._pid)
        me = _MODULEENTRY32()
        me.dwSize = ctypes.sizeof(_MODULEENTRY32)
        base = None
        try:
            if _k32.Module32First(snap, ctypes.byref(me)):
                while True:
                    n = me.szModule.decode(errors='ignore')
                    if n.lower() == module_name.lower():
                        base = me.modBaseAddr
                        break
                    # Fallback : premier module dont le nom contient GTAProcess
                    if base is None and 'GTAProcess' in n:
                        base = me.modBaseAddr
                    if not _k32.Module32Next(snap, ctypes.byref(me)):
                        break
        finally:
            _k32.CloseHandle(snap)
        return base

    def _readable_regions(self, start, max_size):
        """Génère les régions mémoire lisibles via VirtualQueryEx."""
        mbi  = _MEMORY_BASIC_INFORMATION()
        addr = start
        end  = start + max_size
        while addr < end:
            sz = _k32.VirtualQueryEx(
                self._handle, ctypes.c_void_p(addr),
                ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not sz:
                break
            if (mbi.State == MEM_COMMIT and
                    mbi.Protect & READABLE_PAGES and
                    not mbi.Protect & 0x100):   # pas PAGE_GUARD
                yield mbi.BaseAddress, mbi.RegionSize
            addr = mbi.BaseAddress + mbi.RegionSize

    def _scan(self, pattern, mask, start, max_size):
        """Scanne uniquement les pages mémoire accessibles."""
        plen = len(pattern)
        for base, region_size in self._readable_regions(start, max_size):
            region_size = min(region_size, max_size - (base - start))
            offset = 0
            while offset < region_size:
                chunk_size = min(CHUNK + plen, region_size - offset)
                chunk = self._rb(base + offset, chunk_size)
                if not chunk:
                    offset += CHUNK
                    continue
                for i in range(len(chunk) - plen):
                    if all(mask[j] == '?' or chunk[i+j] == pattern[j]
                           for j in range(plen)):
                        return base + offset + i
                offset += CHUNK
        return None

    def _find_ped_ptr(self):
        SCAN_MB = 60 * 1024 * 1024
        for pattern, mask in PED_PATTERNS:
            addr = self._scan(pattern, mask, self._base, SCAN_MB)
            if addr:
                rel = self._ri32(addr + 3)
                ptr = addr + 7 + rel
                if self._ru64(ptr) > 0x10000:
                    return ptr
        return None

    def _ped(self):
        if not self._ped_gptr:
            return None
        addr = self._ru64(self._ped_gptr)
        return addr if addr > 0x10000 else None

# ===FARMBOT_SEP===cheat_bot.py
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
        self._conn_btn = tk.Button(row, text='Connecter', command=self._connect,
                                    relief='flat', bg='#2c3e50', fg='white',
                                    padx=6, pady=2)
        self._conn_btn.pack(side='right')

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
        """Lance la connexion dans un thread pour ne pas bloquer l'UI."""
        self._status_var.set('Connexion en cours — scan mémoire...')
        self._conn_label.config(fg='orange')
        self._conn_btn.config(state='disabled')
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        try:
            self._mem.connect()
            pos = self._mem.get_position()
            hdg = math.degrees(self._mem.get_heading())
            if pos:
                msg = f'Connecté  ({pos[0]:.0f}, {pos[1]:.0f})  cap {hdg:.0f}°'
                self._win.after(0, lambda: self._conn_label.config(fg='#1e8449'))
            else:
                msg = 'Connecté — position illisible (êtes-vous en jeu ?)'
                self._win.after(0, lambda: self._conn_label.config(fg='orange'))
            self._win.after(0, lambda m=msg: self._status_var.set(m))
        except RuntimeError as e:
            msg = str(e).split('\n')[0]
            full = str(e)
            self._win.after(0, lambda m=msg: self._status_var.set(m))
            self._win.after(0, lambda: self._conn_label.config(fg='red'))
            self._win.after(0, lambda t=full: messagebox.showerror(
                'Erreur de connexion', t, parent=self._win))
        finally:
            self._win.after(0, lambda: self._conn_btn.config(state='normal'))

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

# ===FARMBOT_SEP===fivem_recorder.py
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pynput import keyboard, mouse

try:
    from cheat_bot import BotWindow
    _BOT_AVAILABLE = True
except ImportError:
    _BOT_AVAILABLE = False

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


def _is_enter_key(key):
    return key in (keyboard.Key.enter, keyboard.Key.num_lock) or \
           getattr(key, "vk", None) in (13, 108)  # Enter + Numpad Enter


def _is_filtered(key):
    """Touches jamais enregistrées : +, -, Entrée, Echap."""
    if _is_toggle(key) or _is_pause_key(key) or _is_enter_key(key):
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
        self._interval_min  = tk.IntVar(value=0)
        self._interval_sec  = tk.IntVar(value=0)

        self.recorder   = Recorder()
        self.replayer   = Replayer()
        self._bot_win   = None

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
        tk.Label(header, text="Entrée  rec/stop     +  menu     −  pause",
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

        tk.Label(opt, text="Intervalle entre cycles :",
                 font=("Helvetica", 9)).pack(anchor="w", pady=(4, 0))
        int_row = tk.Frame(opt)
        int_row.pack(anchor="w")
        tk.Spinbox(int_row, from_=0, to=59, textvariable=self._interval_min,
                   width=3, font=("Helvetica", 9)).pack(side="left")
        tk.Label(int_row, text="min", font=("Helvetica", 9)).pack(side="left", padx=(2, 8))
        tk.Spinbox(int_row, from_=0, to=59, textvariable=self._interval_sec,
                   width=3, font=("Helvetica", 9)).pack(side="left")
        tk.Label(int_row, text="sec", font=("Helvetica", 9)).pack(side="left", padx=(2, 0))

        ttk.Separator(self.root).pack(fill="x", padx=8)

        # Fichier
        file_row = tk.Frame(self.root)
        file_row.pack(pady=6)
        tk.Button(file_row, text="Sauvegarder", width=12,
                  command=self.save).pack(side="left", padx=4)
        tk.Button(file_row, text="Charger", width=12,
                  command=self.load).pack(side="left", padx=4)

        # Bot
        if _BOT_AVAILABLE:
            ttk.Separator(self.root).pack(fill="x", padx=8)
            tk.Button(self.root, text="🤖  Ouvrir le Bot Farming",
                      bg="#4a235a", fg="white", relief="flat",
                      font=("Helvetica", 10), pady=6, cursor="hand2",
                      command=self._open_bot).pack(fill="x", padx=12, pady=6)

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

        interval = self._interval_min.get() * 60 + self._interval_sec.get()
        self.replayer.start(
            self.recorder.events,
            interval=interval,
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

    def _open_bot(self):
        if self._bot_win and self._bot_win._win.winfo_exists():
            self._bot_win._win.lift()
        else:
            self._bot_win = BotWindow(self.root)

    def _toggle_record(self):
        """Lance ou arrête l'enregistrement directement (touche Entrée)."""
        if self._state == self.REP:
            return
        if self._state == self.IDLE:
            self.start_record()
        else:
            self.stop_record()

    def _start_hotkeys(self):
        def on_press(key):
            if _is_toggle(key):
                self.root.after(0, self._toggle_overlay)
            elif _is_pause_key(key):
                self.root.after(0, self._toggle_pause)
            elif _is_enter_key(key):
                self.root.after(0, self._toggle_record)

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
