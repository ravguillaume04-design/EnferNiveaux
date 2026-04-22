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

# FiveM lance GTA V sous un processus dont le nom contient "GTAProcess"
# Ex : FiveM_b3095_GTAProcess.exe, FiveM_b2699_GTAProcess.exe ...
GTA_PARTIAL_NAMES = ['GTAProcess', 'GTA5.exe']

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
            raise RuntimeError(
                'FiveM introuvable.\n'
                'Assurez-vous que FiveM est lancé et qu\'une partie est chargée.')

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
