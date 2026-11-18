"""Wait for a known serial writer to exit; require its new journals restored."""
import argparse
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('actions',nargs='+')
    args=p.parse_args()
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    k.OpenProcess.restype=ctypes.c_void_p
    k.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
    k.CloseHandle.argtypes=[ctypes.c_void_p]
    process=k.OpenProcess(0x1000,False,args.pid)
    assert process,('predecessor PID unavailable',args.pid)
    try:
        last=0
        while True:
            code=ctypes.c_uint32();assert k.GetExitCodeProcess(process,ctypes.byref(code))
            if code.value!=259:break
            if time.monotonic()-last>=60:
                print('WAIT SERIAL WRITER',args.pid,flush=True);last=time.monotonic()
            time.sleep(1)
        assert code.value==0,('predecessor failed',code.value)
    finally:k.CloseHandle(process)
    paths=list(BASE.glob('remaining571_heat_dynamic_serial_*_20261106_*.json'))
    assert paths
    for path in paths:
        data=json.loads(path.read_text('utf8'))
        assert data.get('restored') is True and not data.get('cleanup_error'),path
    print('PREDECESSOR EXITED; RESTORED; START',args.actions,flush=True)
    subprocess.run([sys.executable,'-u',str(ROOT/'tools/remaining_serial_only_live_20261106.py'),*args.actions],cwd=ROOT,check=True)


if __name__=='__main__':main()
