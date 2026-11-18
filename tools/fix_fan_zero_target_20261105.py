"""One-shot byte-preserving V10.52 patch: only fan target/range boundaries."""
from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[1]
D=R/'.codex-tmp/fan_zero_target_v1052_v1239_20261105'
assert not D.exists(),'Preserve original inventory and patch only once'
D.mkdir()
inventory={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('PSC330RK-V10-内机','PSC316RK-V12-外机') for p in (R/folder).rglob('*')
    if p.is_file() and p.suffix.lower() in ('.c','.h')}
changes={}
def patch(rel,old,new):
    p=R/rel;raw=p.read_bytes();assert raw.count(old)==1,(rel,raw.count(old))
    dst=D/'source_before'/rel;dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():dst.write_bytes(raw)
    p.write_bytes(raw.replace(old,new));changes[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
patch('PSC330RK-V10-内机/USER/UserSrc/FanControl.c',
    b'if((AirVolumeSet > 0) && (DuctAreaSet > 0))',
    b'if((AirVolumeSet >= 0) && (DuctAreaSet > 0))')
patch('PSC330RK-V10-内机/USER/UserSrc/FanControl.c',
    b'if(AirPressureSet > 0)return FanSpecLimitValue(AirPressureSet, 0, 9999);\r\n\treturn Fan_Ctrl_PA1;',
    b'/* Zero is a valid specification setpoint, not a legacy selector. */\r\n\treturn FanSpecLimitValue(AirPressureSet, 0, 9999);')
patch('PSC330RK-V10-内机/USER/UserSrc/UserAction.c',
    b'return IndoorLimitValue(fanDemand, SupplyFanMinVoltSet * 10, SupplyFanMaxVoltSet * 10);',
    b'/* Match FanAction: inverted limits collapse to the configured minimum. */\r\n\treturn IndoorLimitValue(fanDemand, SupplyFanMinVoltSet * 10,\r\n\t\t((SupplyFanMaxVoltSet < SupplyFanMinVoltSet) ?\r\n\t\t SupplyFanMinVoltSet : SupplyFanMaxVoltSet) * 10);')
p=R/'PSC330RK-V10-内机/USER/UserHead/User.h';raw=p.read_bytes()
old=re.search(rb'#define PSC330_VERSION_MINOR[ \t]+51',raw);assert old
patch(p.relative_to(R).as_posix(),old[0],old[0][:-2]+b'52')
(D/'change_manifest.json').write_text(json.dumps({'scope':'330 fan automatic targets: valid zero never falls back to legacy; final automatic fan clamp uses same inverted-limit rule as FanAction. Manual AO path and 316 unchanged.',
    'source_inventory_before':inventory,'changed_common_sources':changes},ensure_ascii=False,indent=2),'utf-8')
print('PATCHED',list(changes),flush=True)
