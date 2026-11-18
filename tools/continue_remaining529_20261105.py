"""Continue exclusive COM6 batches after the already-running special sequence.

The predecessor PID is checked through Windows; serial writers never overlap.
Each child owns its normal-stop/parameter-restoration journal.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '测试证据/内机实测_20261105/BENCH_V1052_V1239'


def main():
    predecessor = int(sys.argv[1])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x100000, False, predecessor)
    if handle:
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        print('Waiting for exclusive COM6 predecessor', predecessor, flush=True)
        while kernel.WaitForSingleObject(handle, 1000) == 258:
            pass
        kernel.CloseHandle(handle)
    journal = {'predecessor_pid': predecessor, 'batches': [], 'serial_writers_overlap': False}
    scripts=sys.argv[2:] or ('remaining529_fan_pressure_board_20261105.py',
                           'remaining529_allocation_defrost_board_20261105.py')
    for name in scripts:
        log = ROOT / '.codex-tmp' / (Path(name).stem + '_continuation.log')
        print('BATCH START', name, flush=True)
        with log.open('w', encoding='utf8') as f:
            completed = subprocess.run([sys.executable, '-u', str(ROOT / 'tools' / name)],
                                       cwd=ROOT, env=os.environ, stdout=f, stderr=subprocess.STDOUT)
        journal['batches'].append({'script': name, 'exit_code': completed.returncode,
                                   'log': str(log.relative_to(ROOT))})
        (OUT / ('continuation_batches_'+str(predecessor)+'.json')).write_text(json.dumps(journal, indent=2), 'utf8')
        print('BATCH END', name, completed.returncode, flush=True)
        # A failed cleanup must be inspected before any further serial writes.
        if completed.returncode:
            break


if __name__ == '__main__':
    main()
