"""
Lecture/écriture mémoire GTA V / FiveM.
Utilise ReadProcessMemory / WriteProcessMemory via ctypes (Windows uniquement).
Les patterns et offsets proviennent de sources publiques de modding GTA V.
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

PROCESS_VM_READ       = 0x0010
PROCESS_VM_WRITE      = 0x0020
PROCESS_VM_OPERATION  = 0x0008
PROCESS_QUERY_INFO    = 0x0400
TH32CS_SNAPMODULE     = 0x00000008
TH32CS_SNAPMODULE32   = 0x00000010

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)

class _MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize',       ctypes.c_ulong),
        ('th32ModuleID', ctypes.c_ulong),
        ('th32ProcessID',ctypes.c_ulong),
        ('GlblcntUsage', ctypes.c_ulong),
        ('ProccntUsage', ctypes.c_ulong),
        ('modBaseAddr',  ctypes.c_size_t),
        ('modBaseSize',  ctypes.c_ulong),
        ('hModule',      ctypes.c_void_p),
        ('szModule',     ctypes.c_char * 256),
        ('szExePath',    ctypes.c_char * 260),
    ]

# ------------------------------------------------------------------ #
#  Noms de processus GTA V / FiveM                                     #
# ------------------------------------------------------------------ #

GTA_PROCESSES = [
    'GTA5.exe',
    'FiveM_GTAProcess.exe',
    'FiveM_b2699_GTAProcess.exe',
    'FiveM_b2802_GTAProcess.exe',
    'FiveM_b3095_GTAProcess.exe',
]

# ------------------------------------------------------------------ #
#  Patterns mémoire (sources publiques GTA V modding)                  #
# ------------------------------------------------------------------ #

# Pattern : mov rax, [rip + rel32] — pointe vers le global CPed*
# Sources : GTAForums, unknowncheats.me (documentation publique)
PED_PATTERNS = [
    (b'\x48\x8B\x05\x00\x00\x00\x00\xF3\x0F\x58\x8B', 'xxx????xxxx'),
    (b'\x48\x8B\x05\x00\x00\x00\x00\x45\x00\x00\x00\x00\x0F\x84', 'xxx????x????xx'),
    (b'\x48\x8B\x05\x00\x00\x00\x00\x8B\x50\x18', 'xxx????xxx'),
]

# Offsets CPed → matrice de transformation (colonne-major, Direct3D)
# Documentés publiquement dans les outils de modding GTA V
MATRIX_OFFSET = 0x90           # Début de la matrice dans CPed
# Vecteur forward (2e colonne de la matrice = direction du regard)
FWD_X = MATRIX_OFFSET + 0x10  # forward.x
FWD_Y = MATRIX_OFFSET + 0x14  # forward.y
# Position (4e colonne)
POS_X = MATRIX_OFFSET + 0x30  # pos.x
POS_Y = MATRIX_OFFSET + 0x34  # pos.y
POS_Z = MATRIX_OFFSET + 0x38  # pos.z

SCAN_SIZE = 60 * 1024 * 1024  # 60 Mo de l'exécutable
CHUNK     = 8192


# ================================================================== #
#  Classe principale                                                   #
# ================================================================== #

class GTAMemory:
    def __init__(self):
        self._handle    = None
        self._pid       = None
        self._base      = None
        self._ped_gptr  = None   # Adresse du pointeur global vers le ped

    # ---------------------------------------------------------------- #
    #  Connexion                                                         #
    # ---------------------------------------------------------------- #

    def connect(self):
        if not _PSUTIL:
            raise RuntimeError("psutil manquant — lancez : py -m pip install psutil")

        pid, name = self._find_process()
        if not pid:
            raise RuntimeError(
                "GTA V / FiveM introuvable.\n"
                "Lancez FiveM, chargez une partie, puis réessayez."
            )

        access = (PROCESS_VM_READ | PROCESS_VM_WRITE |
                  PROCESS_VM_OPERATION | PROCESS_QUERY_INFO)
        handle = _k32.OpenProcess(access, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            raise RuntimeError(
                f"Accès refusé (erreur {err}).\n"
                "Relancez lancer.bat en tant qu'Administrateur."
            )

        self._handle = handle
        self._pid    = pid
        self._base   = self._module_base(name)

        if not self._base:
            raise RuntimeError("Base de l'exécutable introuvable.")

        self._ped_gptr = self._find_ped_ptr()
        if not self._ped_gptr:
            raise RuntimeError(
                "Pattern mémoire non trouvé.\n"
                "Assurez-vous d'être en jeu (pas dans le menu principal)."
            )

    def disconnect(self):
        if self._handle:
            _k32.CloseHandle(self._handle)
            self._handle = None

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
        if x == 0.0 and y == 0.0 and z == 0.0:
            return None
        return (x, y, z)

    def get_heading(self):
        """Retourne le cap du joueur en radians (0 = Nord, π/2 = Est)."""
        ped = self._ped()
        if not ped:
            return 0.0
        fx = self._rf(ped + FWD_X)
        fy = self._rf(ped + FWD_Y)
        return math.atan2(fx, fy)

    def teleport(self, x, y, z):
        """Téléporte le joueur. Retourne True si succès."""
        ped = self._ped()
        if not ped:
            return False
        self._wf(ped + POS_X, x)
        self._wf(ped + POS_Y, y)
        self._wf(ped + POS_Z, z + 0.5)  # +0.5 Z pour éviter le sol
        return True

    # ---------------------------------------------------------------- #
    #  Interne — lecture/écriture                                        #
    # ---------------------------------------------------------------- #

    def _rb(self, addr, size):
        buf  = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        _k32.ReadProcessMemory(self._handle, ctypes.c_void_p(addr),
                               buf, size, ctypes.byref(read))
        return buf.raw[:read.value]

    def _wb(self, addr, data):
        buf     = (ctypes.c_byte * len(data))(*data)
        written = ctypes.c_size_t(0)
        _k32.WriteProcessMemory(self._handle, ctypes.c_void_p(addr),
                                buf, len(data), ctypes.byref(written))

    def _ri32(self, addr):
        d = self._rb(addr, 4)
        return struct.unpack('<i', d)[0] if len(d) >= 4 else 0

    def _ru64(self, addr):
        d = self._rb(addr, 8)
        return struct.unpack('<Q', d)[0] if len(d) >= 8 else 0

    def _rf(self, addr):
        d = self._rb(addr, 4)
        return struct.unpack('<f', d)[0] if len(d) >= 4 else 0.0

    def _wf(self, addr, val):
        self._wb(addr, struct.pack('<f', val))

    # ---------------------------------------------------------------- #
    #  Interne — processus & patterns                                    #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _find_process():
        for p in psutil.process_iter(['name', 'pid']):
            name = p.info['name'] or ''
            for gta in GTA_PROCESSES:
                if name.lower() == gta.lower():
                    return p.info['pid'], name
        return None, None

    def _module_base(self, module_name):
        snap = _k32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self._pid)
        me = _MODULEENTRY32()
        me.dwSize = ctypes.sizeof(_MODULEENTRY32)
        try:
            if _k32.Module32First(snap, ctypes.byref(me)):
                while True:
                    if me.szModule.decode(errors='ignore').lower() == module_name.lower():
                        return me.modBaseAddr
                    if not _k32.Module32Next(snap, ctypes.byref(me)):
                        break
        finally:
            _k32.CloseHandle(snap)
        return None

    def _scan(self, pattern, mask, start, size):
        plen = len(pattern)
        for off in range(0, size - plen, CHUNK):
            chunk = self._rb(start + off, min(CHUNK + plen, size - off))
            if not chunk:
                continue
            for i in range(len(chunk) - plen):
                if all(mask[j] == '?' or chunk[i+j] == pattern[j]
                       for j in range(plen)):
                    return start + off + i
        return None

    def _find_ped_ptr(self):
        for pattern, mask in PED_PATTERNS:
            addr = self._scan(pattern, mask, self._base, SCAN_SIZE)
            if addr:
                rel = self._ri32(addr + 3)
                ptr = addr + 7 + rel
                # Validation rapide : le pointeur doit pointer quelque chose de plausible
                candidate = self._ru64(ptr)
                if candidate > 0x10000:
                    return ptr
        return None

    def _ped(self):
        if not self._ped_gptr:
            return None
        addr = self._ru64(self._ped_gptr)
        return addr if addr > 0x10000 else None
