"""Byte-preserving common-source correction, with an exact source inventory."""
from pathlib import Path
import hashlib
import json
import re

R=Path(__file__).resolve().parents[1]
D=R/'.codex-tmp/special_remote_v1054_v1239_20261106'
assert not D.exists(), 'Review the saved change manifest instead of reapplying'
inventory={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('PSC330RK-V10-内机','PSC316RK-V12-外机')
    for p in (R/directory).rglob('*') if p.is_file() and p.suffix.lower() in ('.c','.h')}
action=R/'PSC330RK-V10-内机/User/UserSrc/UserAction.c'
header=R/'PSC330RK-V10-内机/User/UserHead/User.h'
old=(b'        else\r\n        {\r\n'
     b'            HMIOnOffCommandSet=0; TouchScreenONOFF=0; SysStatusLoader=0; SysStatus=NORSTOP;\r\n'
     b'        }\r\n        manualStop=0;')
new=(b'        /* A remote-interlock stop retains its pending automatic restart.\r\n'
     b'           Explicit manual/timer/fault stops clear that intent in Switch. */\r\n'
     b'        else if(!RemoteInterlockResumeFlag)\r\n        {\r\n'
     b'            HMIOnOffCommandSet=0; TouchScreenONOFF=0; SysStatusLoader=0; SysStatus=NORSTOP;\r\n'
     b'        }\r\n        manualStop=0;')
a=action.read_bytes()
h=header.read_bytes()
assert a.count(old)==1
version=re.search(rb'#define PSC330_VERSION_MINOR[ \t]+53\b',h)
assert version
changes={action:a.replace(old,new),header:h[:version.start()]+version[0][:-2]+b'54'+h[version.end():]}
D.mkdir()
for path,data in changes.items():
    before=D/'source_before'/path.relative_to(R)
    before.parent.mkdir(parents=True,exist_ok=True)
    before.write_bytes(path.read_bytes())
    path.write_bytes(data)
after={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('PSC330RK-V10-内机','PSC316RK-V12-外机')
    for p in (R/directory).rglob('*') if p.is_file() and p.suffix.lower() in ('.c','.h')}
changed={k:dict(before=v,after=after[k]) for k,v in inventory.items() if v!=after[k]}
assert set(changed)=={p.relative_to(R).as_posix() for p in changes}
(D/'source_change_manifest.json').write_text(json.dumps(dict(
    scope='Special-mode shutdown completion only: preserve pending remote-interlock automatic restart; version10.54. No 316 changes.',
    changed_sources=changed,source_inventory_before=inventory,board_still_running='10.53 until existing serial queues finish and recovery is confirmed'),
    ensure_ascii=False,indent=2),'utf8')
print('Changed exactly:',list(changed))
