import os
import platform
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SISTEMAS = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}
_ARQUITECTURAS = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
}

ES_WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class InfoPlataforma:
    sistema: str
    arquitectura: str
    cpus_logicas: int

    @property
    def es_apple_silicon(self) -> bool:
        return self.sistema == "macos" and self.arquitectura == "arm64"


def detectar_plataforma() -> InfoPlataforma:
    sistema = _SISTEMAS.get(platform.system(), "desconocido")
    maquina = platform.machine().lower()
    arquitectura = _ARQUITECTURAS.get(maquina, maquina or "desconocida")
    return InfoPlataforma(
        sistema=sistema,
        arquitectura=arquitectura,
        cpus_logicas=os.cpu_count() or 1,
    )


# ---------------------------------------------------------------------------
# Bloqueo exclusivo entre procesos.
# El sistema operativo libera el bloqueo cuando el proceso termina, también ante un fallo.
# ---------------------------------------------------------------------------


class BloqueoExclusivo:
    def __init__(self, descriptor: int) -> None:
        self._descriptor: int | None = descriptor

    @classmethod
    def adquirir(cls, ruta: Path) -> "BloqueoExclusivo | None":
        """Devuelve el bloqueo, o None si otro proceso ya lo tiene."""
        ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if ES_WINDOWS:
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            return None
        return cls(descriptor)

    def liberar(self) -> None:
        if self._descriptor is None:
            return
        descriptor, self._descriptor = self._descriptor, None
        try:
            if ES_WINDOWS:
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def __enter__(self) -> "BloqueoExclusivo":
        return self

    def __exit__(self, *_: Any) -> None:
        self.liberar()


# ---------------------------------------------------------------------------
# Identidad de procesos: PID más hora de creación. Evita confundir un PID reutilizado.
# ---------------------------------------------------------------------------


def identidad_proceso(pid: int) -> str | None:
    """Huella de un proceso vivo, o None si no existe o ya terminó."""
    if pid <= 0:
        return None
    if ES_WINDOWS:
        return _identidad_windows(pid)
    return _identidad_posix(pid)


def _identidad_posix(pid: int) -> str | None:
    try:
        resultado = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    salida = resultado.stdout.strip()
    return salida or None


if ES_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [("bajo", wintypes.DWORD), ("alto", wintypes.DWORD)]

    class _ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    class _ThreadEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    class _LimiteBasico(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ContadoresES(ctypes.Structure):
        _fields_ = [
            (nombre, ctypes.c_uint64)
            for nombre in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _LimiteExtendido(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _LimiteBasico),
            ("IoInfo", _ContadoresES),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLE = wintypes.HANDLE
    _INVALIDO = ctypes.c_void_p(-1).value

    PROCESS_TERMINATE = 0x0001
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    THREAD_SUSPEND_RESUME = 0x0002
    TH32CS_SNAPPROCESS = 0x0002
    TH32CS_SNAPTHREAD = 0x0004
    CREATE_SUSPENDED = 0x00000004
    CREATE_NO_WINDOW = 0x08000000
    STILL_ACTIVE = 259
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def _firma(funcion: Any, argumentos: list[Any], resultado: Any) -> None:
        funcion.argtypes = argumentos
        funcion.restype = resultado

    _firma(_k32.CreateJobObjectW, [ctypes.c_void_p, wintypes.LPCWSTR], _HANDLE)
    _firma(_k32.SetInformationJobObject, [_HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL)
    _firma(_k32.AssignProcessToJobObject, [_HANDLE, _HANDLE], wintypes.BOOL)
    _firma(_k32.TerminateJobObject, [_HANDLE, wintypes.UINT], wintypes.BOOL)
    _firma(_k32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], _HANDLE)
    _firma(_k32.GetProcessTimes, [_HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.GetExitCodeProcess, [_HANDLE, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.TerminateProcess, [_HANDLE, wintypes.UINT], wintypes.BOOL)
    _firma(_k32.CloseHandle, [_HANDLE], wintypes.BOOL)
    _firma(_k32.CreateToolhelp32Snapshot, [wintypes.DWORD, wintypes.DWORD], _HANDLE)
    _firma(_k32.Process32FirstW, [_HANDLE, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.Process32NextW, [_HANDLE, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.Thread32First, [_HANDLE, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.Thread32Next, [_HANDLE, ctypes.c_void_p], wintypes.BOOL)
    _firma(_k32.OpenThread, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], _HANDLE)
    _firma(_k32.ResumeThread, [_HANDLE], wintypes.DWORD)

    def _abrir_windows(pid: int, acceso: int) -> int | None:
        return _k32.OpenProcess(acceso, False, pid) or None

    def _creacion_windows(manejador: int) -> int | None:
        """Hora de creación del proceso, o None si ya terminó."""
        creacion, salida, nucleo, usuario = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not _k32.GetProcessTimes(
            manejador,
            ctypes.byref(creacion),
            ctypes.byref(salida),
            ctypes.byref(nucleo),
            ctypes.byref(usuario),
        ):
            return None
        estado = wintypes.DWORD()
        _k32.GetExitCodeProcess(manejador, ctypes.byref(estado))
        if estado.value != STILL_ACTIVE:
            return None
        return (creacion.alto << 32) | creacion.bajo

    def _identidad_windows(pid: int) -> str | None:
        manejador = _abrir_windows(pid, PROCESS_QUERY_LIMITED_INFORMATION)
        if manejador is None:
            return None
        try:
            creacion = _creacion_windows(manejador)
            return None if creacion is None else str(creacion)
        finally:
            _k32.CloseHandle(manejador)

    def _terminar_windows(pid: int) -> bool:
        manejador = _abrir_windows(pid, PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION)
        if manejador is None:
            return False
        try:
            return bool(_k32.TerminateProcess(manejador, 1))
        finally:
            _k32.CloseHandle(manejador)

    def _procesos_windows() -> list[tuple[int, int]]:
        """Pares (pid, pid_padre) de todos los procesos del sistema."""
        instantanea = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if instantanea in (None, _INVALIDO):
            raise OSError("No se pudo leer la lista de procesos.")
        try:
            entrada = _ProcessEntry()
            entrada.dwSize = ctypes.sizeof(_ProcessEntry)
            pares: list[tuple[int, int]] = []
            if not _k32.Process32FirstW(instantanea, ctypes.byref(entrada)):
                return pares
            while True:
                pares.append((entrada.th32ProcessID, entrada.th32ParentProcessID))
                if not _k32.Process32NextW(instantanea, ctypes.byref(entrada)):
                    return pares
        finally:
            _k32.CloseHandle(instantanea)

    def _descendientes_windows(raiz: int, creacion_minima: int) -> list[int]:
        """Descendientes del proceso raíz creados después de él. Un PID reutilizado no cumple ese criterio."""
        hijos: dict[int, list[int]] = {}
        for pid, padre in _procesos_windows():
            hijos.setdefault(padre, []).append(pid)
        encontrados: list[int] = []
        vistos = {raiz}
        pendientes = [raiz]
        while pendientes:
            actual = pendientes.pop()
            for candidato in hijos.get(actual, []):
                if candidato in vistos:
                    continue
                vistos.add(candidato)
                creacion = _identidad_windows(candidato)
                if creacion is not None and int(creacion) >= creacion_minima:
                    encontrados.append(candidato)
                    pendientes.append(candidato)
        return encontrados

    def _reanudar_hilos_windows(pid: int) -> None:
        instantanea = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if instantanea in (None, _INVALIDO):
            raise OSError("No se pudo listar los hilos del proceso.")
        try:
            entrada = _ThreadEntry()
            entrada.dwSize = ctypes.sizeof(_ThreadEntry)
            if not _k32.Thread32First(instantanea, ctypes.byref(entrada)):
                return
            while True:
                if entrada.th32OwnerProcessID == pid:
                    manejador = _k32.OpenThread(THREAD_SUSPEND_RESUME, False, entrada.th32ThreadID)
                    if manejador:
                        _k32.ResumeThread(manejador)
                        _k32.CloseHandle(manejador)
                if not _k32.Thread32Next(instantanea, ctypes.byref(entrada)):
                    return
        finally:
            _k32.CloseHandle(instantanea)

    def _crear_job_windows() -> int:
        """Job Object con KILL_ON_JOB_CLOSE: al cerrar el último handle, todos sus procesos terminan."""
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limites = _LimiteExtendido()
        limites.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limites),
            ctypes.sizeof(limites),
        ):
            error = ctypes.get_last_error()
            _k32.CloseHandle(job)
            raise ctypes.WinError(error)
        return job


def _matar_grupo_posix(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def terminar_proceso_verificado(pid: int, identidad: str | None) -> bool:
    """Termina el proceso y sus descendientes solo si la identidad coincide. Devuelve True si emitió la orden."""
    if identidad is None or identidad_proceso(pid) != identidad:
        return False
    if ES_WINDOWS:
        for hijo in _descendientes_windows(pid, int(identidad)):
            _terminar_windows(hijo)
        return _terminar_windows(pid)
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return False
    return True


class GrupoProcesos:
    """Un proceso hijo y todo lo que genere.

    Windows: Job Object con KILL_ON_JOB_CLOSE. El proceso se crea suspendido, se asigna al job y luego se reanuda.
    POSIX: grupo de procesos propio (start_new_session) y SIGKILL al grupo completo.
    """

    def __init__(self) -> None:
        self._job: int | None = None
        self._pgid: int | None = None

    def iniciar(
        self,
        argumentos: list[str],
        *,
        cwd: Path,
        stdin: Any = subprocess.DEVNULL,
        stdout: Any = subprocess.DEVNULL,
        stderr: Any = subprocess.DEVNULL,
    ) -> subprocess.Popen:
        comun: dict[str, Any] = {
            "cwd": str(cwd),
            "stdin": stdin,
            "stdout": stdout,
            "stderr": stderr,
            "close_fds": True,
        }
        if ES_WINDOWS:
            self._job = _crear_job_windows()
            proceso = subprocess.Popen(
                argumentos,
                creationflags=CREATE_SUSPENDED | CREATE_NO_WINDOW,
                **comun,
            )
            try:
                manejador = _abrir_windows(proceso.pid, PROCESS_SET_QUOTA | PROCESS_TERMINATE)
                if manejador is None:
                    raise OSError("No se pudo abrir el proceso del trabajo.")
                try:
                    if not _k32.AssignProcessToJobObject(self._job, manejador):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    _k32.CloseHandle(manejador)
                _reanudar_hilos_windows(proceso.pid)
            except OSError:
                proceso.kill()
                proceso.wait()
                self.cerrar()
                raise
            return proceso
        proceso = subprocess.Popen(argumentos, start_new_session=True, **comun)
        self._pgid = proceso.pid
        return proceso

    def terminar(self) -> None:
        """Termina todos los procesos del grupo sin cerrar el contenedor."""
        if ES_WINDOWS:
            if self._job is not None:
                _k32.TerminateJobObject(self._job, 1)
        elif self._pgid is not None:
            _matar_grupo_posix(self._pgid)

    def cerrar(self) -> None:
        """Libera el contenedor. Mata cualquier proceso que siga vivo del grupo."""
        if ES_WINDOWS:
            if self._job is not None:
                _k32.CloseHandle(self._job)
                self._job = None
        elif self._pgid is not None:
            _matar_grupo_posix(self._pgid)
            self._pgid = None


def abortar_proceso(codigo: int) -> None:
    """Termina el proceso actual y, en POSIX, su grupo. Se usa cuando el proceso del trabajo pierde su reclamo."""
    if not ES_WINDOWS:
        _matar_grupo_posix(os.getpgrp())
    os._exit(codigo)
