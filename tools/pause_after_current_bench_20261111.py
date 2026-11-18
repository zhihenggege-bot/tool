"""Request queue pause after the specified current child exits, never mid-case."""
import argparse
import ctypes
import json
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--child-pid',type=int,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    evidence=root/'测试证据/台架执行_20261111/pause_after_current_request.json'
    flag=root/'.codex-tmp/continuous_v1055_pause.request'
    entry=dict(requested=time.strftime('%Y-%m-%dT%H:%M:%S%z'),child_pid=args.child_pid,
               instruction='Finish current batch, restore and independently audit, then pause before next batch',
               status='waiting_for_current_batch_exit',hardware_access=False)
    evidence.write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf8')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x00100000,False,args.child_pid)
    if not handle and ctypes.get_last_error()!=87:
        raise OSError(ctypes.get_last_error(),'Could not monitor current child')
    if handle:
        try:
            while kernel.WaitForSingleObject(handle,500)==258:pass
        finally:kernel.CloseHandle(handle)
    flag.write_text('User requested pause after current batch; finish independent restoration audit before queue pause.\n',encoding='utf8')
    entry.update(status='pause_flag_set_after_child_exit',at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    evidence.write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(entry,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
