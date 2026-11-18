"""Allow the active child to finish; pause only the parent queue at its next boundary."""
import ctypes,json,time,os
from pathlib import Path
R=Path(__file__).resolve().parents[1]
D=R/'测试证据/剩余全队列_20261112'
K=ctypes.WinDLL('kernel32',use_last_error=True)
N=ctypes.WinDLL('ntdll')
K.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];K.OpenProcess.restype=ctypes.c_void_p
K.CloseHandle.argtypes=[ctypes.c_void_p]
K.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
N.NtSuspendProcess.argtypes=[ctypes.c_void_p];N.NtSuspendProcess.restype=ctypes.c_long
N.NtResumeProcess.argtypes=[ctypes.c_void_p];N.NtResumeProcess.restype=ctypes.c_long
P=D/'pause_after_current_batch.json'
def save(q):
 t=P.with_suffix('.tmp');t.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');t.replace(P)
def stamp():return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def active(h):
 c=ctypes.c_uint32();assert K.GetExitCodeProcess(h,ctypes.byref(c));return c.value==259
q=json.loads((D/'controller.json').read_text('utf8'))
a=q.get('active',{});assert q['status']=='running' and a.get('key')=='defrost_matrix_lp-defrost',(q['status'],a)
parent=K.OpenProcess(0x0800|0x1000,False,q['pid']);assert parent
suspended=False;child=None
record=dict(requested=stamp(),instruction='做完第36批暂停',watcher_pid=os.getpid(),parent_pid=q['pid'],child_pid=a['pid'],batch=a['key'],status='arming',hardware_access=False)
try:
 assert N.NtSuspendProcess(parent)==0;suspended=True
 # Recheck after suspending: the already-running child remains fully active.
 latest=json.loads((D/'controller.json').read_text('utf8'))
 assert latest.get('active',{}).get('pid')==a['pid'],'Active batch changed before boundary was armed'
 child=K.OpenProcess(0x1000,False,a['pid'])
 record.update(status='waiting_for_current_child_normal_completion',armed=stamp());save(record)
 while child and active(child):time.sleep(.5)
 marker=R/'.codex-tmp/continuous_v1055_pause.request'
 marker.write_text('User requested pause after batch36; child finished, complete independent restoration audit then pause before next batch.',encoding='utf8')
 record.update(status='child_finished_parent_released_for_restoration_audit',child_finished=stamp());save(record)
finally:
 if suspended:assert N.NtResumeProcess(parent)==0
 if child:K.CloseHandle(child)
 K.CloseHandle(parent)
for _ in range(600):
 latest=json.loads((D/'controller.json').read_text('utf8'))
 if latest['status']!='running':
  record.update(status=latest['status'],finished=stamp(),executed=len(latest['executed']),active=latest.get('active'));save(record);break
 time.sleep(1)
else:
 record.update(status='audit_completion_requires_review');save(record)
