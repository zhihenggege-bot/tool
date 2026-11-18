"""Keep per-unit reset generations pending until their command frame is ACKed."""
import json
import shutil
import build_timing_profiles as b
from build_manual_gate_v1244_20261113 import sha

R=b.ROOT;OLD=R/'.codex-tmp/manual_gate_v1062_v1244_20261113';OUT=R/'.codex-tmp/manual_gate_v1063_v1244_20261113'

def change(raw,old,new):
    old=old.replace('\n','\r\n').encode('ascii');new=new.replace('\n','\r\n').encode('ascii')
    assert raw.count(old)==1,old[:100]
    return raw.replace(old,new)

def main():
    m=json.loads((OLD/'BENCH_ONLY_3S/manifest.json').read_text('utf8'));before=m['source_inventory']
    assert all(sha(R/n)==v for n,v in before.items())
    OUT.mkdir(exist_ok=False)
    for rel in ('PSC330RK-V10-内机/User/UserHead/User.h','PSC330RK-V10-内机/User/UserSrc/modulecontrol.c',
                'PSC330RK-V10-内机/User/UserSrc/UserAction.c'):
        p=R/rel;raw=p.read_bytes();backup=OUT/'source_backup'/rel
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(raw)
        if rel.endswith('User.h'):
            raw=change(raw,'PSC330_VERSION_MINOR        62','PSC330_VERSION_MINOR        63')
        elif rel.endswith('UserAction.c'):
            raw=change(raw,'\t\tErrorOutY00 = HandDebugAlarmMan ? 1 : 0;',
'''        /* V10.63: manual alarm test may assert Y05, never suppress a fault. */
		ErrorOutY00 = (ErrorOutFlag || HandDebugAlarmMan) ? 1 : 0;''')
        else:
            raw=change(raw,'static uint8_t PSC316CtrlShadowValid[PSC316_HMI_UNIT_NUM] = {0,0,0,0};',
'''static uint8_t PSC316CtrlShadowValid[PSC316_HMI_UNIT_NUM] = {0,0,0,0};
/* V10.63: the HMI reset pulse may expire before a unit's next control poll.
   Each request is retained until its own control-write ACK, including retries. */
static uint16_t PSC316ResetGeneration=0;
static uint16_t PSC316ResetAck[PSC316_HMI_UNIT_NUM]={0,0,0,0};
static uint16_t PSC316BusResetGeneration=0;
static uint8_t PSC316ResetPending(uint8_t unit)
{
    return (unit>=1 && unit<=PSC316_HMI_UNIT_NUM &&
            PSC316ResetAck[unit-1]!=PSC316ResetGeneration) ? 1:0;
}''')
            raw=change(raw,'    PSC316BusTick=Systick_1ms;',
'''    PSC316BusResetGeneration=0;
    if(fn==16 && PSC316BusAddress==PLCctrlPara && PSC316BusCount>=3 &&
       (ucUart5Buff[11] || ucUart5Buff[12]) && PSC316ResetPending(unit))
        PSC316BusResetGeneration=PSC316ResetGeneration;
    PSC316BusTick=Systick_1ms;''')
            raw=change(raw,'            PSC316CtrlShadowValid[PSC316BusUnit-1]=1;',
'''            PSC316CtrlShadowValid[PSC316BusUnit-1]=1;
            if(PSC316BusResetGeneration)
                PSC316ResetAck[PSC316BusUnit-1]=PSC316BusResetGeneration;''')
            raw=change(raw,'\tfor(u=0; u<PSC316_HMI_UNIT_NUM; u++)PSC316FaultLatch[u]=0;',
'''    PSC316ResetGeneration++;
    if(!PSC316ResetGeneration)
    {
        PSC316ResetGeneration=1;
        for(u=0;u<PSC316_HMI_UNIT_NUM;u++)PSC316ResetAck[u]=0;
    }
    for(u=0;u<PSC316_HMI_UNIT_NUM;u++)
    {
        PSC316FaultLatch[u]=0;
        if((u+2)>ModuleNumSet)PSC316ResetAck[u]=PSC316ResetGeneration;
    }''')
            raw=change(raw,'\t\tif((ModuleNum>=1)&&(ModuleNum<=PSC316_HMI_UNIT_NUM)\n\t\t\t&&PSC316VersionRequestPending[ModuleNum-1])',
'''        if(PSC316ResetPending(ModuleNum))
        {
            SendParaAddr3[ModuleNum]=0;
            PSC316PollResume[ModuleNum-1]=255;
            PSC316PollPreempted[ModuleNum-1]=0;
        }
		if((ModuleNum>=1)&&(ModuleNum<=PSC316_HMI_UNIT_NUM)
            &&!PSC316ResetPending(ModuleNum)
			&&PSC316VersionRequestPending[ModuleNum-1])''')
            raw=change(raw,'\t\telse if(PSC316WriteJob.active\n\t\t\t&& (PSC316WriteJob.unit == ModuleNum)',
'''\t\telse if(PSC316WriteJob.active
            && !PSC316ResetPending(ModuleNum)
			&& (PSC316WriteJob.unit == ModuleNum)''')
            raw=change(raw,'\t\t\tchanged = 0;','\t\t\tchanged = PSC316ResetPending(ModuleNum);')
            raw=change(raw,'\t\t\t\tucUart5Buff[j*2+7]   = Parameter[Addr+j]>>8;',
'''                BroadcastValue=((j==2) && PSC316ResetPending(ModuleNum)) ? 1 : (uint16_t)Parameter[Addr+j];
				ucUart5Buff[j*2+7]   = BroadcastValue>>8;''')
            raw=change(raw,'\t\t\t\tucUart5Buff[j*2+8]   = Parameter[Addr+j];','\t\t\t\tucUart5Buff[j*2+8]   = BroadcastValue;')
            raw=change(raw,'\t\t\t\tfor(j=0;j<Num;j++)PSC316CtrlShadow[ModuleNum-1][j] = Parameter[Addr+j];',
'''\t\t\t\tfor(j=0;j<Num;j++)PSC316CtrlShadow[ModuleNum-1][j] = Parameter[Addr+j];
                if(PSC316ResetPending(ModuleNum))PSC316CtrlShadow[ModuleNum-1][2]=1;''')
        p.write_bytes(raw)
    after={n:sha(R/n) for n in before};changed=[n for n in before if before[n]!=after[n]];assert len(changed)==3
    for name,data in (('source_before.json',before),('source_after.json',after)):
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')
    b.OUT=OUT
    for bench in (False,True):
        profile='BENCH_ONLY_3S' if bench else 'PRODUCTION'
        artifacts=b.build(*b.PROJECTS[0][:-1],'10.63',bench)
        m=json.loads((OLD/profile/'manifest.json').read_text('utf8'))
        for n,v in m['artifacts'].items():
            if n.startswith('PSC316_'):
                assert sha(OLD/profile/n)==v
                shutil.copy2(OLD/profile/n,OUT/profile/n);artifacts[n]=v
        assert all(sha(R/n)==v for n,v in after.items())
        m.update(artifacts=artifacts,source_inventory=after,indoor_version='10.63',outdoor_version='12.44',
                 indoor_unchanged=False,outdoor_unchanged=True,new_changed_sources=changed,
                 change='Retain per-unit reset until matching ACK; prioritize reset control writes; manual alarm cannot suppress real Y05 alarm',
                 flashed=False,hardware_tested=False)
        (OUT/profile/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        print('BUILD VERIFIED',profile,flush=True)

if __name__=='__main__':main()
