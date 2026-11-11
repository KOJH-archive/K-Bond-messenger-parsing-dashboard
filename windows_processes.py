"""Small Windows process backend for the local launcher; no third-party dependency."""
import ctypes
from ctypes import wintypes as wt
import os
from pathlib import Path
import struct
import time

Error = OSError
NoSuchProcess = ProcessLookupError


class _Windows:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.ntdll = ctypes.WinDLL('ntdll')
        k = self.kernel
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.OpenProcess.restype = wt.HANDLE
        k.CloseHandle.argtypes = [wt.HANDLE]
        k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k.K32EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
        k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        k.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
        k.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
        k.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        k.IsWow64Process.argtypes = [wt.HANDLE, ctypes.POINTER(wt.BOOL)]
        self.ntdll.NtQueryInformationProcess.argtypes = [wt.HANDLE, wt.ULONG, ctypes.c_void_p, wt.ULONG, ctypes.POINTER(wt.ULONG)]
        self.ntdll.NtQueryInformationProcess.restype = ctypes.c_long
        self.shell = ctypes.WinDLL('shell32', use_last_error=True)
        self.shell.CommandLineToArgvW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        self.shell.CommandLineToArgvW.restype = ctypes.POINTER(wt.LPWSTR)
        k.LocalFree.argtypes = [ctypes.c_void_p]

    def open(self, pid, access):
        handle = self.kernel.OpenProcess(access, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def creation(self, handle):
        values = [wt.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

    def parent_pid(self, pid):
        handle = self.open(pid, 0x1000)
        try:
            pointer_size = struct.calcsize('P')
            basic = ctypes.create_string_buffer(pointer_size * 6)
            returned = wt.ULONG()
            if self.ntdll.NtQueryInformationProcess(handle, 0, basic, len(basic), ctypes.byref(returned)) < 0:
                raise OSError('Cannot inspect parent process')
            return int.from_bytes(basic.raw[pointer_size*5:pointer_size*6], 'little')
        finally:
            self.kernel.CloseHandle(handle)

    def read(self, handle, address, size):
        if not address or size > 65536:
            raise OSError('Invalid process memory range')
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not self.kernel.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(count)) or count.value != size:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw

    def command(self, handle):
        class Unicode(ctypes.Structure):
            _fields_ = [('length', wt.USHORT), ('maximum', wt.USHORT), ('buffer', ctypes.c_void_p)]
        length = wt.ULONG()
        self.ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(length))
        if not 0 < length.value <= 131072:
            raise OSError('Cannot inspect process command line')
        buffer = ctypes.create_string_buffer(length.value)
        if self.ntdll.NtQueryInformationProcess(handle, 60, buffer, length.value, ctypes.byref(length)) < 0:
            raise OSError('Cannot inspect process command line')
        value = ctypes.cast(buffer, ctypes.POINTER(Unicode)).contents
        base = ctypes.addressof(buffer)
        if not value.buffer or value.buffer < base or value.buffer + value.length > base + ctypes.sizeof(buffer):
            raise OSError('Invalid command-line buffer')
        command = ctypes.wstring_at(value.buffer, value.length // 2)
        count = ctypes.c_int()
        argv = self.shell.CommandLineToArgvW(command, ctypes.byref(count))
        if not argv:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return [argv[i] for i in range(count.value)]
        finally:
            self.kernel.LocalFree(argv)

    def cwd(self, pid):
        # RTL_USER_PROCESS_PARAMETERS.CurrentDirectory is a UNICODE_STRING.
        # Only same-bitness reads are used; command-line inspection above also handles other processes.
        handle = self.open(pid, 0x0400 | 0x0010)
        try:
            wow = wt.BOOL()
            if not self.kernel.IsWow64Process(handle, ctypes.byref(wow)):
                return None
            bits = struct.calcsize('P')
            if bits == 8 and wow.value:
                return None
            if bits == 4 and not wow.value:
                return None
            basic = ctypes.create_string_buffer(bits * 6)
            returned = wt.ULONG()
            if self.ntdll.NtQueryInformationProcess(handle, 0, basic, len(basic), ctypes.byref(returned)) < 0:
                return None
            peb = int.from_bytes(basic.raw[bits:bits*2], 'little')
            parameters = int.from_bytes(self.read(handle, peb + (0x20 if bits == 8 else 0x10), bits), 'little')
            directory = self.read(handle, parameters + (0x38 if bits == 8 else 0x24), bits * 2)
            length = int.from_bytes(directory[:2], 'little')
            address = int.from_bytes(directory[bits:bits*2], 'little')
            return self.read(handle, address, length).decode('utf-16-le') if length else None
        finally:
            self.kernel.CloseHandle(handle)


_api = None


def api():
    global _api
    if _api is None:
        if os.name != 'nt':
            raise RuntimeError('통합실행은 Windows에서 사용해 주세요.')
        _api = _Windows()
    return _api


def ancestor_pids(pid):
    protected = {pid, os.getppid()} if pid == os.getpid() else {pid}
    cursor = pid
    for _ in range(32):
        try:
            parent = api().parent_pid(cursor)
        except OSError:
            break
        if not parent or parent == cursor:
            break
        protected.add(parent)
        cursor = parent
    return protected


class Process:
    def __init__(self, pid, info, created):
        self.pid, self.info, self.created = pid, info, created

    def terminate(self):
        native = api()
        try:
            handle = native.open(self.pid, 0x1000 | 0x0001)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 87:
                raise NoSuchProcess(self.pid) from exc
            raise
        try:
            if native.creation(handle) != self.created:
                raise NoSuchProcess(self.pid)
            if not native.kernel.TerminateProcess(handle, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            native.kernel.CloseHandle(handle)

    def alive(self):
        native = api()
        try:
            handle = native.open(self.pid, 0x1000 | 0x00100000)
        except OSError:
            return False
        try:
            return native.creation(handle) == self.created and native.kernel.WaitForSingleObject(handle, 0) == 0x102
        finally:
            native.kernel.CloseHandle(handle)


def process_iter(_attributes):
    native = api()
    pids = (wt.DWORD * 65536)()
    returned = wt.DWORD()
    if not native.kernel.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(returned)):
        raise ctypes.WinError(ctypes.get_last_error())
    for pid in pids[:returned.value // ctypes.sizeof(wt.DWORD)]:
        if not pid or pid == os.getpid():
            continue
        handle = None
        try:
            handle = native.open(pid, 0x1000)
            image = ctypes.create_unicode_buffer(32768)
            length = wt.DWORD(len(image))
            if not native.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                continue
            name = Path(image.value).name
            if not name.casefold().startswith('python'):
                continue
            command = native.command(handle)
            try:
                directory = native.cwd(pid)
            except OSError:
                directory = None
            yield Process(pid, dict(pid=pid, name=name, cmdline=command, cwd=directory), native.creation(handle))
        except OSError:
            continue
        finally:
            if handle:
                native.kernel.CloseHandle(handle)


def wait_procs(processes, timeout):
    deadline = time.monotonic() + timeout
    alive = list(processes)
    while alive and time.monotonic() < deadline:
        alive = [p for p in alive if p.alive()]
        if alive:
            time.sleep(.05)
    return [p for p in processes if p not in alive], alive
