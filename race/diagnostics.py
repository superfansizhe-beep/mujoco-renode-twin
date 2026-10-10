"""Read-only C estimates from the loaded binary's symbols, like a debugger.

No firmware writes or virtual-time advances. Stripped/mismatched binaries
report unavailable; the viewer must never substitute plant truth for estimates.
"""
import ctypes
import hashlib
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


_FLOATS = ("t_now", "psi", "odo_x", "odo_y", "y_pos", "y_ref",
           "w_f", "w_cmd", "w_integ", "tau_d", "lost_t", "v_stop", "tilt_f")
_REQUIRED = (*_FLOATS, "law_seq", "phase")


def _symbols(path, arm):
    candidates = [os.getenv("ARM_NM" if arm else "HOST_NM"),
                  shutil.which("arm-none-eabi-nm" if arm else "nm")]
    nm = next((p for p in candidates if p and Path(p).is_file()), None)
    if nm is None:
        raise ValueError("nm unavailable; set ARM_NM or HOST_NM")
    result = subprocess.run([nm, "-S", "--defined-only", str(path)],
                            capture_output=True, text=True, timeout=10, check=True)
    wanted = {*_REQUIRED, "race_law_cycle"}
    symbols = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) not in (3, 4):
            continue
        address, kind, raw = fields[0], fields[-2], fields[-1]
        # Mach-O prefixes every symbol with an underscore; PE and ELF do not.
        name = raw[1:] if raw.startswith("_") and raw[1:] in wanted else raw
        if name not in wanted:
            continue
        # Apple nm always reports size 0 for Mach-O (see its warning); treat
        # that as "unknown" rather than a real 0-byte symbol.
        size = int(fields[1], 16) if len(fields) == 4 else None
        if name in symbols:
            raise ValueError(f"ambiguous symbol: {name}")
        symbols[name] = (int(address, 16), kind.lower(), size or None)
    for name in _REQUIRED:
        if name not in symbols or symbols[name][1] not in "bBdD":
            raise ValueError(f"missing data symbol: {name}")
        minimum = 1 if name == "phase" else 4
        if symbols[name][2] is not None and symbols[name][2] < minimum:
            raise ValueError(f"unexpected symbol size: {name}")
    return symbols


def _pe_mapping(path):
    """Image base and mapped data bounds, before any ctypes memory read."""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("host symbol inspection currently requires a PE DLL")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE image")
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20b:
        image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10b:
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ValueError("unsupported PE image")
    size = struct.unpack_from("<I", data, optional + 56)[0]
    bounds = []
    for i in range(sections):
        off = optional + optional_size + 40 * i
        virtual_size, rva, raw_size = struct.unpack_from("<III", data, off + 8)
        flags = struct.unpack_from("<I", data, off + 36)[0]
        if flags & 0xc0 and flags & 0x40000000:  # readable initialized/BSS data
            bounds.append((image_base + rva, image_base + rva + max(virtual_size, raw_size)))
    return image_base, size, bounds


# Mach-O (macOS) twin of _pe_mapping: same three values -- image base, total
# image size, and the readable data section bounds -- read from the Mach-O
# load commands instead of the PE headers. hostc compiles the same C core to a
# .dll on Windows and a Mach-O on macOS, and this snapshot must work on both.
# magic -> Mach-O header size (28 for 32-bit, 32 for 64-bit). Byte order
# comes from the file: a Mach-O whose magic reads as feedfacf is
# little-endian, one that reads as cffaedfe is big-endian (stored swapped).
_MACHO_MAGICS = {
    0xfeedface: 28,
    0xfeedfacf: 32,
    0xcffaedfe: 32,
    0xcffaedfc: 28,
}
_MACHO_SEG_SECT = 0x1


def _macho_mapping(path):
    """(image_base, image_size, data_bounds) for a thin Mach-O image."""
    data = path.read_bytes()
    # Read the magic little-endian: a 64-bit LE image stores the bytes
    # ce fa ed fe, which unpack("<I") turns back into feedfacf.
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic not in _MACHO_MAGICS:
        raise ValueError("not a Mach-O image")
    # feedfacf -> little-endian file, cffaedfe -> big-endian (bytes swapped).
    endian = "<" if magic in (0xfeedface, 0xfeedfacf) else ">"
    header_size = _MACHO_MAGICS[magic]
    ncmds = struct.unpack_from(endian + "I", data, 16)[0]
    offset = header_size
    base = size = None
    bounds = []
    is64 = magic in (0xfeedfacf, 0xcffaedfe)
    seg_cmds = (0x19,) if is64 else (0x2, 0x19)
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from(endian + "II", data, offset)
        if cmdsize == 0:          # corrupt header: stop rather than spin
            break
        # In a 64-bit image only LC_SEGMENT_64 is a segment; cmd 0x2 there is
        # LC_SYMTAB and must not be read as one.
        if cmd in seg_cmds:
            segname = data[offset + 8:offset + 24].rstrip(b"\0")
            wide = cmd == 0x19
            if wide:
                vmaddr, vmsize = struct.unpack_from(endian + "QQ", data, offset + 24)
                nsects = struct.unpack_from(endian + "I", data, offset + 64)[0]
                sect_off = offset + 72
            else:
                vmaddr, vmsize = struct.unpack_from(endian + "II", data, offset + 24)
                nsects = struct.unpack_from(endian + "I", data, offset + 48)[0]
                sect_off = offset + 56
            for i in range(nsects):
                soff = sect_off + 80 * i
                s_size = struct.unpack_from(endian + "Q" if wide else endian + "I",
                                            data, soff + 40)[0]
                s_addr = struct.unpack_from(endian + "Q" if wide else endian + "I",
                                            data, soff + 32)[0]
                flags = struct.unpack_from(endian + "I", data, soff + 64)[0]
                # S_REGULAR | S_ZEROFILL data sections: the two the C state lives in.
                if s_size and flags & 0xFF in (0x0, 0x1, 0xC):
                    bounds.append((s_addr, s_addr + s_size))
            if segname == b"__TEXT" or base is None:
                base, size = vmaddr, vmsize
        offset += cmdsize
    if base is None:
        raise ValueError("Mach-O image has no __TEXT segment")
    return base, size, bounds


class CEstimates:
    def __init__(self, path, read_word=None, dll=None):
        self.source = "firmware_symbols" if dll is None else "host_c_symbols"
        self.reason = None
        self.metadata = {}
        self._cache = None
        try:
            path = Path(path).resolve()
            symbols = _symbols(path, arm=dll is None)
            addresses = {name: symbols[name][0] for name in _REQUIRED}
            if dll is None:
                if any(not 0x20000000 <= address <= 0x2001e9fc
                       for address in addresses.values()):
                    raise ValueError("C state symbol outside firmware SRAM")
                self._read = read_word
            else:
                head = path.read_bytes()[:4]
                macho = head in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                                 b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")
                base, size, bounds = (_macho_mapping(path) if macho
                                     else _pe_mapping(path))
                cycle = symbols["race_law_cycle"][0]
                pointer = ctypes.cast(dll.race_law_cycle, ctypes.c_void_p).value
                bias = pointer - cycle
                # The loaded image must be the one we parsed: its load address
                # has to equal the mapped base shifted by the same bias. Only
                # a Windows CDLL carries a real load address in _handle; on
                # macOS the attribute exists but holds a ctypes bookkeeping
                # value, so there compare against the parsed mapping instead.
                if sys.platform == "win32":
                    if bias + base != getattr(dll, "_handle", None):
                        raise ValueError("loaded DLL does not match its symbol map")
                elif not base + bias <= pointer < base + bias + size:
                    raise ValueError("loaded library does not match its symbol map")
                if not base <= cycle < base + size:
                    raise ValueError("loaded DLL does not match its symbol map")
                if any(not any(lo <= address and address + 4 <= hi for lo, hi in bounds)
                       for address in addresses.values()):
                    raise ValueError("C state symbol outside mapped DLL data")
                addresses = {name: address + bias for name, address in addresses.items()}
                self._read = lambda address: ctypes.c_uint32.from_address(address).value
            self._addresses = addresses
            self.metadata = {"artifact": str(path),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        except (OSError, ValueError, KeyError, struct.error, subprocess.SubprocessError) as exc:
            self.reason = str(exc)

    def clear_cache(self):
        self._cache = None

    def snapshot(self, fw_seq, phase):
        if self.reason:
            return {"available": False, "source": self.source, "reason": self.reason}
        if self._cache is not None and self._cache[0] == (fw_seq, phase):
            return self._cache[1]
        try:
            read = lambda name: self._read(self._addresses[name])
            seq = read("law_seq")
            phase_index = read("phase") & 0xff
            if seq != fw_seq or phase_index != ("arm", "run", "brake", "done").index(phase):
                raise ValueError("C state does not match the published control cycle")
            values = {name: struct.unpack("<f", struct.pack("<I", read(name)))[0]
                      for name in _FLOATS}
            if not all(math.isfinite(v) for v in values.values()) or read("law_seq") != seq:
                raise ValueError("incomplete or non-finite C snapshot")
            snapshot = {"available": True, "source": self.source, "fw_seq": seq,
                        "artifact": self.metadata,
                        "control_time_s": values["t_now"],
                        "pitch_deg": math.degrees(values["tilt_f"]),
                        "heading_rad": values["psi"],
                        "odometry_m": [values["odo_x"], values["odo_y"]],
                        "yaw_rate_rad_s": values["w_f"],
                        "yaw_target_rad_s": values["w_cmd"],
                        "yaw_integral_nm": values["w_integ"],
                        "differential_torque_nm": values["tau_d"],
                        "position_error_m": values["y_pos"] - values["y_ref"],
                        "stop_speed_estimate_mps": values["v_stop"],
                        "line_lost_s": values["lost_t"]}
        except (ValueError, OSError) as exc:
            snapshot = {"available": False, "source": self.source, "reason": str(exc)}
        self._cache = ((fw_seq, phase), snapshot)
        return snapshot
