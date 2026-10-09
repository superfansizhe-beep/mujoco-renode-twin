"""Renode mailbox-address smoke: is the twin's SRAM window really mapped?

No firmware involved -- this boots the F407 Discovery machine in Renode
and round-trips a write/read through monitor at the twin mailbox
addresses. It pins the address choice BEFORE the C firmware phase
arrives: the radar twin used 0x2003FFF0, which only exists in Renode's
generous sysbus map -- real F407 silicon has no RAM above 0x20020000,
and this twin must run on the bought board.

Run:  python -m twin.renode_smoke
Needs: RENODE_SURVEY_ROOT pointing at the survey checkout
(or RENODE_ROOT pointing at any portable install).
"""
import os
import sys

SURVEY_ROOT = os.environ.get("RENODE_SURVEY_ROOT", "")

from .mailbox import MAGIC, TWIN_BASE  # noqa: E402


def main() -> int:
    sys.path.insert(0, SURVEY_ROOT)
    try:
        from tool.session import RenodeSession
    except ImportError as exc:
        print(f"SKIP: cannot import the survey tool package ({exc})")
        return 0

    renode_root = os.path.join(SURVEY_ROOT, "renode", "renode_1.17.0-portable")
    if not os.path.isdir(renode_root):
        print(f"SKIP: portable Renode not found at {renode_root}")
        return 0

    elf = os.path.join(SURVEY_ROOT, "firmware", "radar.elf")
    rs = RenodeSession(renode_root=renode_root, settle=0.05)
    try:
        rs.start()
        rs.load_stm32f4_discovery(elf if os.path.isfile(elf) else "", mips=4)
        wrote = rs.execute(f"sysbus WriteDoubleWord 0x{TWIN_BASE:08X} 0x{MAGIC:08X}")
        read_back = rs.read_ram(TWIN_BASE)
        ok = read_back == MAGIC
        print(f"mailbox 0x{TWIN_BASE:08X}: wrote MAGIC 0x{MAGIC:08X}, "
              f"read 0x{read_back:08X} -> {'MAPPED OK' if ok else 'NOT MAPPED'}")
        if not ok:
            print("pick a different TWIN_BASE (must lie inside the repl's "
                  "sysbus RAM region AND inside real-chip SRAM)")
        return 0 if ok else 1
    finally:
        rs.close()


if __name__ == "__main__":
    raise SystemExit(main())
