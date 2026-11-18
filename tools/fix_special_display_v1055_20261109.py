"""Preserve source bytes: clear only stale special-mode phase diagnostic."""
from pathlib import Path
import hashlib,json,re

R=Path(__file__).resolve().parents[1]
D=R/'.codex-tmp/special_display_v1055_v1239_20261109'
assert not D.exists(),'Do not reapply; inspect the existing manifest'
def inventory():
    return {p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for directory in ('PSC330RK-V10-内机','PSC316RK-V12-外机')
        for p in (R/directory).rglob('*') if p.is_file() and p.suffix.lower() in ('.c','.h')}
before=inventory()
action=R/'PSC330RK-V10-内机/User/UserSrc/UserAction.c'
header=R/'PSC330RK-V10-内机/User/UserHead/User.h'
a=action.read_bytes();h=header.read_bytes()
old=b'        IndoorEmergencyStopLoads(); step=0; phase=0; manualStop=0; return;'
new=b'        IndoorEmergencyStopLoads(); step=0; phase=0; manualStop=0; DisinfectStepDisp=0; return;'
assert a.count(old)==1
h,n=re.subn(rb'(#define PSC330_VERSION_MINOR[ \t]+)54\b',rb'\g<1>55',h);assert n==1
h,n=re.subn(rb'(#define PSC330_VERSION_DAY[ \t]+)6\b',rb'\g<1>9',h);assert n==1
D.mkdir()
for path,data in ((action,a.replace(old,new)),(header,h)):
    backup=D/'source_before'/path.relative_to(R);backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_bytes(path.read_bytes());path.write_bytes(data)
after=inventory()
changed={k:dict(before=v,after=after[k]) for k,v in before.items() if v!=after[k]}
assert set(changed)=={p.relative_to(R).as_posix() for p in (action,header)}
(D/'source_change_manifest.json').write_text(json.dumps(dict(
    scope='Only clear DisinfectStepDisp before fault early return; version10.55 dated2026-11-09. No control/timing/316 changes.',
    changed_sources=changed,source_inventory_before=before,source_inventory_after=after),ensure_ascii=False,indent=2),'utf8')
print('Exactly two source files changed:',list(changed))
