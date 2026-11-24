"""Allow normal standby frost minimum on DA8; preserve existing safety inhibits."""
import difflib
import json
import build_timing_profiles as build
from build_normal_stop_v1070_20261119 import inventory
from deploy_production_v1064_v1246_20261118 import sha

R=build.ROOT
OLD=R/'.codex-tmp/da8_water_valve_v1074_20261124/PRODUCTION'
OUT=R/'.codex-tmp/da8_standby_v1075_20261124'
DAY=R/'测试证据/DA8停机防冻_V1075_20261124'


def prepare():
    assert inventory()==json.loads((OLD/'manifest.json').read_text('utf8'))['source_inventory']
    changes={
        'PSC330RK-V10-内机/User/UserSrc/UserAction.c':[(
            '    if((SysStep != 2) || SysErrStatus || IndoorSensorPartialStopFlag ||\n'
            '       ((UserWorkModeSetTEMP != MODE_COOL) && (UserWorkModeSetTEMP != MODE_HEAT)) ||\n'
            '       (minimum <= 0) || (FreshAirTempDisp >= 0) || TSysOutTempErr || shutdownFault)\n'
            '    {\n        return;\n    }\n'
            '    if(ColdWaterValveAO8Disp < minimum)ColdWaterValveAO8Disp = minimum;',
            '    /* Normal standby also protects the water coil. Safety inhibits\n'
            '       retain priority over both manual opening and frost minimum. */\n'
            '    if(SysErrStatus || IndoorSensorPartialStopFlag ||\n'
            '       ((minimum > 0) && TSysOutTempErr) || shutdownFault)\n'
            '    {\n'
            '        ColdWaterValveAO8Disp = 0;\n'
            '        IndoorSetAO(&ColdWaterValveAO8, 0);\n'
            '        return;\n    }\n'
            '    if((SysStep != 2) ||\n'
            '       ((UserWorkModeSetTEMP != MODE_COOL) && (UserWorkModeSetTEMP != MODE_HEAT)))\n'
            '    {\n'
            '        /* Only the frost minimum is active outside normal running.\n'
            '           Recompute from zero so warming or disabling releases it. */\n'
            '        ColdWaterValveAO8Disp = ((minimum > 0) && (FreshAirTempDisp < 0)) ? minimum : 0;\n'
            '        IndoorSetAO(&ColdWaterValveAO8, ColdWaterValveAO8Disp);\n'
            '        return;\n'
            '    }\n'
            '    if((minimum <= 0) || (FreshAirTempDisp >= 0))return;\n'
            '    if(ColdWaterValveAO8Disp < minimum)ColdWaterValveAO8Disp = minimum;')],
        'PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c':[
            ('return (climate && (CompControlModeSet==1 || MinValveOpenSet>0)) || enthalpy ||',
             'return (MinValveOpenSet>0) || (climate && CompControlModeSet==1) || enthalpy ||'),
            ('(((UserWorkModeSetTEMP == MODE_COOL) || (UserWorkModeSetTEMP == MODE_HEAT)) &&\n'
             '          (MinValveOpenSet > 0))', '(MinValveOpenSet > 0)')],
        'PSC330RK-V10-内机/User/UserHead/User.h':[
            ('#define PSC330_VERSION_MINOR        74','#define PSC330_VERSION_MINOR        75')]
    }
    staged={}
    for name,pairs in changes.items():
        before=(R/name).read_bytes();after=before
        nl='\r\n' if b'\r\n' in before else '\n'
        for old,new in pairs:
            old,new=(v.replace('\n',nl).encode('ascii') for v in (old,new))
            assert after.count(old)==1,(name,old)
            after=after.replace(old,new)
        staged[name]=(before,after)
    OUT.mkdir();DAY.mkdir(parents=True,exist_ok=True)
    (OUT/'source_before.json').write_text(json.dumps(inventory(),indent=2),'utf8')
    diff=[]
    for name,(before,after) in staged.items():
        backup=OUT/'source_backup'/name;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(before)
        (R/name).write_bytes(after)
        diff.extend(difflib.unified_diff(before.decode('gb18030',errors='replace').splitlines(True),
            after.decode('gb18030',errors='replace').splitlines(True),fromfile=name+' V10.74',tofile=name+' V10.75'))
    (DAY/'source_changes.diff').write_text(''.join(diff).replace('\r\n','\n'),'utf8')
    (OUT/'source_after.json').write_text(json.dumps(inventory(),indent=2),'utf8')


def main():
    if not OUT.exists():prepare()
    assert inventory()==json.loads((OUT/'source_after.json').read_text('utf8'))
    build.OUT=OUT
    artifacts=build.build(*build.PROJECTS[0][:-1],'10.75',False,incremental=True)
    manifest=dict(versions={'330':'10.75','316':'12.56'},profile='PRODUCTION',
        artifacts=artifacts,source_inventory=inventory(),flashed=False,hardware_tested=False,
        scope='DA8 frost minimum during normal standby; running manual and safety priorities preserved')
    (OUT/'PRODUCTION/manifest.json').write_text(json.dumps(manifest,indent=2),'utf8')
    print('BUILD PASS 330 V10.75; 0 errors, 0 warnings',flush=True)


if __name__=='__main__':main()
