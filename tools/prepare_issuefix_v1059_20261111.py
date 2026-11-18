"""Apply narrowly scoped byte-preserving fixes; retain the previous source inventory."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.codex-tmp/issuefix_v1059_v1241_20261111'
OUT.mkdir(parents=True, exist_ok=True)
old = json.loads((ROOT / '.codex-tmp/shared_type_v1058_20261110/PRODUCTION/manifest.json').read_text('utf8'))
before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in old['source_inventory']}
assert before == old['source_inventory'], 'Source baseline changed; inspect before applying'
(OUT / 'source_before.json').write_text(json.dumps(before, indent=2)+'\n', 'utf8')

def edit(path, transform):
    p = ROOT / path
    data = p.read_bytes()
    backup = OUT / 'source_backup' / path
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(data)
    # Latin1 is a reversible byte mapping, not a source encoding conversion.
    text = data.decode('latin1').replace('\r\n', '\n')
    changed = transform(text)
    assert changed != text, path
    p.write_bytes(changed.replace('\n', '\r\n').encode('latin1'))

def replace(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def display(s):
    s = s.replace('PSC316PageShadow[18]', 'PSC316PageShadow[14]')
    s = s.replace('i<18', 'i<14')
    s = s.replace('cache=i<14 ? UnitWriteStatus[unit].TempCheck[i] : UnitWriteStatus[unit].ELEMODSET1[i-14];',
                  'cache=UnitWriteStatus[unit].TempCheck[i];')
    s = s.replace('value=i<14 ? Parameter[CHECK+i] : Parameter[ParameterSaveSize+EMODSET+1+i-14];',
                  'value=Parameter[CHECK+i];')
    s = re.sub(r'if\(i<14\)Parameter\[CHECK\+i\]=cache;\n\s*else Parameter\[ParameterSaveSize\+EMODSET\+1\+i-14\]=cache;',
               'Parameter[CHECK+i]=cache;', s)
    s = replace(s, 'if(i<14)PSC316Gateway_LegacyCalibrationWrite((unsigned char)unit,(unsigned char)i,value);\n            else PSC316Gateway_LegacyEEVWrite((unsigned char)unit,(unsigned char)(i-14),value);',
                'PSC316Gateway_LegacyCalibrationWrite((unsigned char)unit,(unsigned char)i,value);')
    return replace(s, 'static short PSC316PageShadow[14];',
                   '/* V10.59: 881..884 are diagnostics; EEV manual uses 220..235. */\nstatic short PSC316PageShadow[14];')

def modbus(s):
    start=s.index('    if(addr>=ParameterSaveSize+EMODSET+1')
    end=s.index('\t/* Runtime/status mirrors', start)
    return s[:start]+ '    /* V10.59: no writable legacy EEV alias over diagnostic 881..884. */\n'+s[end:]

def polling(s):
    s=replace(s, 'static uint8_t PSC316PollRound[PSC316_HMI_UNIT_NUM] = {0,0,0,0};',
        'static uint8_t PSC316PollRound[PSC316_HMI_UNIT_NUM] = {0,0,0,0};\n'
        '/* One priority write per round; resume the interrupted poll afterwards. */\n'
        'static uint8_t PSC316PollResume[PSC316_HMI_UNIT_NUM] = {255,255,255,255};\n'
        'static uint8_t PSC316PollPreempted[PSC316_HMI_UNIT_NUM] = {0,0,0,0};')
    s=replace(s, '\t\t\t&& (SendParaAddr3[ModuleNum] != 8))',
        '\t\t\t&& (SendParaAddr3[ModuleNum] != 8)\n'
        '\t\t\t&& !PSC316PollPreempted[ModuleNum-1])')
    s=replace(s, '\t\t\t/* [V10.12] HMI write jumps the queue instead of waiting a full round. */',
        '\t\t\t/* V10.59: bound preemption so repeated writes cannot starve faults. */\n'
        '\t\t\tPSC316PollResume[ModuleNum-1] = (uint8_t)SendParaAddr3[ModuleNum];\n'
        '\t\t\tPSC316PollPreempted[ModuleNum-1] = 1;')
    s=replace(s, '\t\t\tSendParaAddr3[ModuleNum]=0;\n\t\t\tPSC316PollRound[ModuleNum-1] = (PSC316PollRound[ModuleNum-1] + 1) & 3;',
        '\t\t\tif(PSC316PollResume[ModuleNum-1] != 255)\n'
        '\t\t\t{\n'
        '\t\t\t\tSendParaAddr3[ModuleNum] = PSC316PollResume[ModuleNum-1];\n'
        '\t\t\t\tPSC316PollResume[ModuleNum-1] = 255;\n'
        '\t\t\t}\n'
        '\t\t\telse\n'
        '\t\t\t{\n'
        '\t\t\t\tSendParaAddr3[ModuleNum]=0;\n'
        '\t\t\t\tPSC316PollRound[ModuleNum-1] = (PSC316PollRound[ModuleNum-1] + 1) & 3;\n'
        '\t\t\t\tPSC316PollPreempted[ModuleNum-1] = 0;\n'
        '\t\t\t}')
    line=next(x for x in s.splitlines() if 'SendParaAddr3[1]=0;SendParaAddr3[2]=0;' in x)
    s=replace(s,line,line+'\n\t\t\tfor(i=0;i<PSC316_HMI_UNIT_NUM;i++)\n'
        '\t\t\t{PSC316PollResume[i]=255;PSC316PollPreempted[i]=0;}')
    s=replace(s,'\t\t\tPSC316VersionRequestPending[i-1]=0;',
        '\t\t\tPSC316VersionRequestPending[i-1]=0;\n'
        '\t\t\tPSC316PollResume[i-1]=255;\n\t\t\tPSC316PollPreempted[i-1]=0;')
    return s

def fans(s):
    s=replace(s, 'static unsigned int OutdoorTypeIILowRecoverCount=0;',
        'static unsigned int OutdoorTypeIILowRecoverCount=0; /* max of independent holds */\n'
        'static unsigned int OutdoorTypeIILowRecoverEnvCount=0;\n'
        'static unsigned int OutdoorTypeIILowRecoverCondCount=0;')
    s=replace(s,'\tOutdoorTypeIILowRecoverCount = 0;',
        '\tOutdoorTypeIILowRecoverCount = 0;\n\tOutdoorTypeIILowRecoverEnvCount = 0;\n\tOutdoorTypeIILowRecoverCondCount = 0;')
    s=replace(s, '\tif((EnviTempAI0Disp > 100) || (CondTempMax > 420))\n\t{\n\t\tif(OutdoorTypeIILowRecoverCount < 30) OutdoorTypeIILowRecoverCount += uc1s;\n\t\tif(OutdoorTypeIILowRecoverCount >= 30) OutdoorTypeIILowFanOff = 0;\n\t}\n\telse OutdoorTypeIILowRecoverCount = 0;',
        '\t/* V12.41: each recovery condition must hold continuously for 30 s. */\n'
        '\tif(EnviTempAI0Disp > 100)\n\t{\n'
        '\t\tif(OutdoorTypeIILowRecoverEnvCount < 30) OutdoorTypeIILowRecoverEnvCount += uc1s;\n\t}\n'
        '\telse OutdoorTypeIILowRecoverEnvCount = 0;\n'
        '\tif(CondTempMax > 420)\n\t{\n'
        '\t\tif(OutdoorTypeIILowRecoverCondCount < 30) OutdoorTypeIILowRecoverCondCount += uc1s;\n\t}\n'
        '\telse OutdoorTypeIILowRecoverCondCount = 0;\n'
        '\tOutdoorTypeIILowRecoverCount = (OutdoorTypeIILowRecoverEnvCount > OutdoorTypeIILowRecoverCondCount)\n'
        '\t\t? OutdoorTypeIILowRecoverEnvCount : OutdoorTypeIILowRecoverCondCount;\n'
        '\tif(OutdoorTypeIILowRecoverCount >= 30) OutdoorTypeIILowFanOff = 0;')
    s=replace(s, '\tif((OutdoorFanTypeSet == 1)||(OutdoorFanTypeSet == 3)||(OutdoorFanTypeSet == 4))\n\t{\n\t\tif(OutdoorHeatTwoFan) OutdoorFanSelectTwoSequential(&Fan1On,&Fan2On);\n\t\telse OutdoorFanSelectOneByRuntime(&Fan1On,&Fan2On);\n\t}',
        '\tif(OutdoorFanTypeSet == 3)\n\t{\n'
        '\t\t/* V12.41: select targets only; TypeIIFanApply owns the single action gate. */\n'
        '\t\tif(OutdoorHeatTwoFan) {Fan1On=1;Fan2On=1;}\n'
        '\t\telse if(CurrentFan1 == CurrentFan2)\n\t\t{\n'
        '\t\t\tFan1On = (OutdoorFanTotalRun[0] <= OutdoorFanTotalRun[1]) ? 1 : 0;\n'
        '\t\t\tFan2On = Fan1On ? 0 : 1;\n\t\t}\n'
        '\t\telse {Fan1On=CurrentFan1;Fan2On=CurrentFan2;}\n\t}\n'
        '\telse if((OutdoorFanTypeSet == 1)||(OutdoorFanTypeSet == 4))\n\t{\n'
        '\t\tif(OutdoorHeatTwoFan) OutdoorFanSelectTwoSequential(&Fan1On,&Fan2On);\n'
        '\t\telse OutdoorFanSelectOneByRuntime(&Fan1On,&Fan2On);\n\t}')
    s,n = re.subn(r'OutdoorFan(Run|Stop)Seconds\[([01])\] (>=|<) FanMin(?:Run|Stop)TimeSet',
        lambda m: ('!' if m[3]=='<' else '')+f'OutdoorFan{m[1]}Ok({m[2]})',s)
    assert n == 10,n
    return s

edit('PSC330RK-V10-内机/User/UserSrc/DispAction.c',display)
edit('PSC330RK-V10-内机/User/modbus/modbus.c',modbus)
edit('PSC330RK-V10-内机/User/UserSrc/modulecontrol.c',polling)
edit('PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c',fans)
edit('PSC330RK-V10-内机/User/UserHead/User.h',lambda s: replace(replace(s,
    '#define PSC330_VERSION_MINOR        58','#define PSC330_VERSION_MINOR        59'),
    '#define PSC330_VERSION_DAY          10','#define PSC330_VERSION_DAY          11'))
edit('PSC316RK-V12-外机/WELLTHINKER/User/User.h',lambda s: replace(replace(s,
    '#define PSC316_VERSION_MINOR 40','#define PSC316_VERSION_MINOR 41'),
    '#define PSC316_VERSION_DAY 10','#define PSC316_VERSION_DAY 11'))
after={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in before}
(OUT/'source_after.json').write_text(json.dumps(after,indent=2)+'\n','utf8')
print('Changed sources:',*[p for p in before if before[p]!=after[p]],sep='\n')
