"""One-shot byte-preserving targeted V10.51 fix with source inventory."""
from pathlib import Path
import hashlib,json,shutil,re
R=Path(__file__).resolve().parents[1]
D=R/'.codex-tmp/ai3_hold_reason_v1051_v1239_20261105'
assert not D.exists(),'Review prior patch rather than rerun'
D.mkdir()
inventory={str(p.relative_to(R)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
           for folder in ('PSC330RK-V10-内机','PSC316RK-V12-外机') for p in (R/folder).rglob('*')
           if p.is_file() and p.suffix.lower() in ('.c','.h')}
changes={}
def patch(rel,old,new,count=1):
    p=R/rel;b=p.read_bytes();assert b.count(old)==count,(rel,b.count(old))
    dest=D/'source_before'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():dest.write_bytes(b)
    p.write_bytes(b.replace(old,new));changes[rel]=hashlib.sha256(p.read_bytes()).hexdigest()

patch('PSC330RK-V10-内机/USER/UserSrc/ErrorCheck.c',
      b'(roomHumidityNeeded && ROOMHumidtyErr) ||',
      b'(roomHumidityNeeded && ROOMHumidtyErr) ||\r\n\t\t (SupplyFanModeSet == SUPPLY_FAN_AUTO_AO && AI3Err) ||')
patch('PSC330RK-V10-内机/USER/UserSrc/NergryAdjust.c',
      b'else if(n1000 <= 0)target = (keepOne && (maxComp > 0)) ? 1 : IndoorRunningCompNum();\r\n\telse target = IndoorRunningCompNum();',
      b'else target = IndoorRunningCompNum(); /* Z=0 holds actual count, including N=0 with reheat. */')
patch('PSC330RK-V10-内机/USER/UserSrc/NergryAdjust.c',
      b'OutputForbidReasonDisp=7;',
      b'/* Shared primary diagnostic: auto-switch inhibition has priority when enabled. */\r\n        OutputForbidReasonDisp = AutoCoolHeatEnableSet ? 6 : 7;',2)
p=R/'PSC330RK-V10-内机/USER/UserHead/User.h';raw=p.read_bytes()
old=re.search(rb'#define PSC330_VERSION_MINOR[ \t]+50',raw);assert old
patch(str(p.relative_to(R)).replace('\\','/'),old[0],old[0][:-2]+b'51')
(D/'change_manifest.json').write_text(json.dumps({'scope':'330 only: AI3 automatic-fan sensor fault joins existing partial-load shutdown; Z=0 target equals actual; shared reason6 priority when auto enabled, otherwise7. 316 unchanged.',
    'source_inventory_before':inventory,'changed_common_sources':changes},ensure_ascii=False,indent=2),'utf-8')
print('PATCHED',list(changes))
