"""Restrict X02 to remote control; keep local HMI/timer and build offline only."""
import json
from pathlib import Path
import build_timing_profiles as b
from build_manual_gate_v1244_20261113 import sha

R = b.ROOT
OLD = R / '.codex-tmp/vfd_unload_min30_v1063_v1246_20261117'
OUT = R / '.codex-tmp/local_remote_v1064_20261117'


def replace(raw, old, new):
    old = old.replace('\n', '\r\n').encode('ascii')
    new = new.replace('\n', '\r\n').encode('ascii')
    assert raw.count(old) == 1, old[:120]
    return raw.replace(old, new)


def prepare():
    before = json.loads((OLD / 'PRODUCTION/manifest.json').read_text('utf8'))['source_inventory']
    assert all(sha(R / n) == digest for n, digest in before.items())
    OUT.mkdir(exist_ok=False)
    files = ('User/UserHead/User.h', 'User/UserSrc/Switch.c',
             'User/UserSrc/ErrorCheck.c', 'User/UserSrc/UserAction.c')
    for rel in files:
        p = R / 'PSC330RK-V10-内机' / rel
        raw = p.read_bytes()
        backup = OUT / 'source_backup' / p.relative_to(R)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(raw)
        if rel.endswith('User.h'):
            raw = replace(raw, 'PSC330_VERSION_MINOR        63', 'PSC330_VERSION_MINOR        64')
            raw = replace(raw, 'PSC330_VERSION_DAY          13', 'PSC330_VERSION_DAY          17')
        elif rel.endswith('Switch.c'):
            raw = replace(raw, '    static unsigned char lastRemote=0, lastPLC=0, timerArmed=0;',
                '    static unsigned char lastRemote=0, lastPLC=0, timerArmed=0;\n'
                '    static unsigned char lastControlSource=0;')
            raw = replace(raw, '\tFarSwitch = FarSwitchX02;', '''\tFarSwitch = FarSwitchX02;
    /* V10.64: X02 has no interlock or resume effect outside remote control. */
    if(UserSwitchSet!=1)
    {
        RemoteInterlockStopFlag=0;
        RemoteInterlockResumeFlag=0;
    }''')
            raw = replace(raw, '        lastRemote=FarSwitch; lastPLC=TMOnOffFlag; timerArmed=(TimeStatus==0);',
                '        lastRemote=FarSwitch; lastPLC=TMOnOffFlag; timerArmed=(TimeStatus==0);\n'
                '        lastControlSource=UserSwitchSet;')
            raw = replace(raw, '\t\tif((UserAutoModeSet==1)&&(SysStatusLoader))',
                '\t\tif((UserSwitchSet!=1)&&(UserAutoModeSet==1)&&(SysStatusLoader))')
            raw = replace(raw, '\t\treturn;\t\n\t}\n\n\tSysTryAction();', '''        /* Remote boot follows the maintained, filtered X02 contact. */
        if(UserSwitchSet==1)
        {
            SysStatusLoader=0;
            RemoteInterlockResumeFlag=FarSwitch ? 1 : 0;
        }
\t\treturn;\t
\t}

    if(lastControlSource!=UserSwitchSet)
    {
        /* Retire the old source through the existing normal-stop sequence.
           A closed remote contact waits for that sequence to finish. */
        lastControlSource=UserSwitchSet;
        Old_SysStatus=0;
        HMIOnOffCommandSet=0;
        OldHMIOnOff=0;
        TouchScreenONOFF=0;
        SysStatusLoader=0;
        RemoteInterlockStopFlag=0;
        RemoteInterlockResumeFlag=(UserSwitchSet==1 && FarSwitch) ? 1 : 0;
        timerArmed=(TimeStatus==0);
        lastRemote=FarSwitch;
        lastPLC=TMOnOffFlag;
    }

\tSysTryAction();''')
            raw = replace(raw, '\tif(UserWidsModeSet==0)',
                '\tif((UserWidsModeSet==0)||(UserSwitchSet==1))')
            raw = replace(raw,
                '\t\t\tif((FarSwitch ==1)&&(lastRemote==0)&&(SysStep==0)&&(Old_SysStatus==0))Old_SysStatus=1;',
                '''            if((FarSwitch==1)&&(lastRemote==0)&&(Old_SysStatus==0))
            {
                if(SysStep==0)Old_SysStatus=1;
                else RemoteInterlockResumeFlag=1;
            }''')
            raw = replace(raw,
                '\tif(RemoteInterlockResumeFlag && !RemoteInterlockStopFlag &&\n\t   (SysStep==0) && (SysErrStatus==0))',
                '\tif((UserSwitchSet==1) && RemoteInterlockResumeFlag && !RemoteInterlockStopFlag &&\n'
                '\t   (SysStep==0) && (SysErrStatus==0) && (TryUseOver==0))')
        elif rel.endswith('ErrorCheck.c'):
            raw = replace(raw, '\tif(X_02 == 0)', '\tif((UserSwitchSet==1) && (X_02==0))')
            raw = replace(raw,
                '\t\tremoteInterlockOpenCount=0;\n\t\tRemoteInterlockStopFlag=0;',
                '\t\tremoteInterlockOpenCount=0;\n\t\tRemoteInterlockStopFlag=0;\n'
                '        if(UserSwitchSet!=1)RemoteInterlockResumeFlag=0;')
            raw = replace(raw,
                '/* External interlock: open for 3 s requests normal shutdown and auto-recovers. */',
                '/* V10.64: remote X02 only; local manual/timer ignore this input. */')
        else:
            raw = replace(raw, '\tif(UserWidsModeSet==0)\n\t{\n\t\tCtrlDisp=UserSwitchSet;',
                '\tif((UserWidsModeSet==0)||(UserSwitchSet==1))\n\t{\n\t\tCtrlDisp=UserSwitchSet;')
        p.write_bytes(raw)
    after = {n: sha(R / n) for n in before}
    changed = [n for n in before if before[n] != after[n]]
    assert len(changed) == 4, changed
    for name, data in (('source_before.json', before), ('source_after.json', after)):
        (OUT / name).write_text(json.dumps(data, indent=2), 'utf8')
    return after, changed


def main():
    if OUT.exists():
        after = json.loads((OUT / 'source_after.json').read_text('utf8'))
        before = json.loads((OUT / 'source_before.json').read_text('utf8'))
        assert all(sha(R / n) == digest for n, digest in after.items())
        changed = [n for n in before if before[n] != after[n]]
    else:
        after, changed = prepare()
    b.OUT = OUT
    for bench in (False, True):
        profile = 'BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts = b.build(*b.PROJECTS[0][:-1], '10.64', bench, incremental=True)
        assert all(sha(R / n) == digest for n, digest in after.items())
        manifest = json.loads((OLD / profile / 'manifest.json').read_text('utf8'))
        manifest.update(artifacts=artifacts, source_inventory=after,
            indoor_version='10.64', outdoor_version='12.46',
            indoor_unchanged=False, outdoor_unchanged=True,
            new_changed_sources=changed,
            change='X02 remote only; local manual/timer retained; source transition retires stale requests',
            flashed=False, hardware_tested=False)
        (OUT / profile / 'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf8')
        print('BUILD VERIFIED', profile, flush=True)


if __name__ == '__main__':
    main()
