"""Build isolated start-watchdog and typeII fan-recovery corrections; no flash.

Run only after the current live batches have restored and their audit passed.
"""
import hashlib
import json
import shutil
import build_timing_profiles as b

R=b.ROOT
OLD=R/'.codex-tmp/vfd_scale_v1242_20261112'
OUT=R/'.codex-tmp/restart_guard_v1060_v1243_20261112'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    prior=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'))
    before=prior['source_inventory']
    assert all(sha(R/p)==h for p,h in before.items()),'Current source/image binding changed'
    assert not OUT.exists(),'Never overwrite prior build evidence'
    OUT.mkdir()
    rel='PSC330RK-V10-内机/User/UserSrc/CompAction.c'
    head='PSC330RK-V10-内机/User/UserHead/User.h'
    outdoor='PSC316RK-V12-外机/WELLTHINKER/User/UserAction.c'
    outdoor_head='PSC316RK-V12-外机/WELLTHINKER/User/User.h'
    for name in (rel,head,outdoor,outdoor_head):
        p=R/name;raw=p.read_bytes();backup=OUT/'source_backup'/name
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(raw)
        s=raw.decode('latin1').replace('\r\n','\n')
        if name==rel:
            old='''static void CompStartStateUpdate(void)
{
    unsigned int m,c,timeout;
    timeout=(unsigned int)FanONLaySet+60U;
    if(timeout<60U)timeout=60U;
    if(timeout>300U)timeout=300U;
'''
            new='''/* Outdoor fan minimum-stop is a legitimate startup WAIT, not a failed
   compressor. Preserve the original confirmation allowance after that wait.
   Read each unit's actual316[180] mirror, including independent settings. */
static unsigned int CompStartTimeoutSeconds(unsigned int module)
{
    unsigned int timeout;
    signed int fanMinStop;
    timeout=(unsigned int)FanONLaySet+60U;
    if(timeout<60U)timeout=60U;
    if(timeout>300U)timeout=300U;
    if(PSC316UnitSettingsReady(module))
    {
        fanMinStop=Parameter[PSC316SettingMirrorAddress(module,15U)];
        if((fanMinStop>=10) && (fanMinStop<=300))
            timeout+=(unsigned int)fanMinStop;
    }
    return timeout;
}
static void CompStartStateUpdate(void)
{
    unsigned int m,c;
'''
            assert s.count(old)==1;s=s.replace(old,new)
            old='Systick_1ms-CompStartTick[m][c]>=(unsigned long long)timeout*1000U'
            new='Systick_1ms-CompStartTick[m][c]>=(unsigned long long)CompStartTimeoutSeconds(m)*1000U'
            assert s.count(old)==1;s=s.replace(old,new)
        elif name==head:
            for old,new in (('PSC330_VERSION_MINOR        59','PSC330_VERSION_MINOR        60'),
                            ('PSC330_VERSION_DAY          11','PSC330_VERSION_DAY          12')):
                assert s.count(old)==1;s=s.replace(old,new)
        elif name==outdoor:
            old='OutdoorFanTypeSet == 3 && OutdoorTypeIILowFanOff && OutdoorFanStage == 0'
            new='OutdoorFanTypeSet == 3 && (OutdoorTypeIILowFanOff || OutdoorTypeIIStage == 0) && OutdoorFanStage == 0'
            assert s.count(old)==1;s=s.replace(old,new)
            old='    if(UserWorkModeSet == 0 && !OutdoorPrestartOwnsFans && (Comp1Y05 || Comp2Y06) &&'
            new='''    /* Low-temperature fan-off recovery still has the stage0->1 delay.
       Keep its regulated no-fan permission until stage0 has completed; clearing
       the temperature latch alone must not cut the running compressors. */
'''+old
            assert s.count(old)==1;s=s.replace(old,new)
        else:
            old='PSC316_VERSION_MINOR 42';new='PSC316_VERSION_MINOR 43'
            assert s.count(old)==1;s=s.replace(old,new)
        p.write_bytes(s.replace('\n','\r\n').encode('latin1'))
    after={p:sha(R/p) for p in before}
    changed=[p for p in before if before[p]!=after[p]]
    assert set(changed)=={rel,head,outdoor,outdoor_head}
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    b.OUT=OUT
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts=b.build(*b.PROJECTS[0][:-1],'10.60',bench)
        artifacts.update(b.build(*b.PROJECTS[1][:-1],'12.43',bench))
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        assert all(sha(R/p)==h for p,h in after.items())
        m.update(artifacts=artifacts,source_inventory=after,
            changed_sources=sorted(set(m['changed_sources']+changed)),
            new_changed_sources=changed,
            change='330 confirmation includes outdoor minimum-stop;316 preserves regulated stop through typeII stage0 recovery;fixed50Hz AO retained',
            indoor_version='10.60',outdoor_version='12.43',indoor_unchanged=False,
            outdoor_unchanged_since_v1242=False,flashed=False,hardware_tested=False)
        (OUT/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        print('BUILD VERIFIED',profile,flush=True)


if __name__=='__main__':main()
