"""Actual linked special-mode shutdown/remote-recovery, offline ARM only.

The board suite separately exercises real DI scanning and scheduling. This
focused regression isolates the special-mode completion writer and Switch.
"""
import argparse
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware

ROOT=Path(__file__).resolve().parents[1]


def fixture(package,version,profile,mode):
    f=Firmware(str(package/profile/f'PSC330_V{version}_{profile}.axf'))
    f.uc.mem_map(0x22000000,0x100000)
    f.call('ParameterInit')
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    for a,v in {1:mode,236:mode,214:3,709:0,700:0,163:0,164:0,166:0,
        323:5,324:5,325:0,329:2,330:0,331:1,328:0,132:0,135:0,
        335:0,336:0,337:0,338:0,381:0,386:0}.items():f.p(a,v)
    for a in range(250,258):f.p(a,1)
    f.var('X_02',1)
    f.var('Systick_1ms',30000)
    f.call('SwitchStatusProcess')
    f.p(398,1)
    f.call('SwitchStatusProcess')
    assert f.p(700)==4
    f.call('IndoorDisinfectExhaustAction')
    for ms in (180000,200000):
        f.var('Systick_1ms',ms)
        f.call('IndoorDisinfectExhaustAction')
    assert f.p(709)==2 and f.p(885)==(4 if mode==4 else 3)
    return f


def scenario(package,version,profile,mode,kind):
    f=fixture(package,version,profile,mode)
    entry=dict(profile=profile,mode=mode,kind=kind,steps=[])
    if kind=='remote':
        # Input-boundary flags only in the emulator; no hardware RAM writes.
        f.var('RemoteInterlockStopFlag',1)
        f.var('RemoteInterlockResumeFlag',1)
    elif kind=='manual':f.p(398,0)
    else:f.p(710,1)
    for ms in range(201000,291000,100):
        f.var('Systick_1ms',ms)
        f.call('SwitchStatusProcess')
        f.call('IndoorDisinfectExhaustAction')
        entry['steps'].append(dict(ms=ms,sys=f.p(700),step=f.p(709),hmi=f.p(398),saved=f.p(166),
            resume=f.var('RemoteInterlockResumeFlag',width=1),special=f.p(885)))
        if f.p(709)==0:
            # Include the next Switch scan, where a forced HMI falling edge
            # used to silently erase the pending remote restart.
            f.call('SwitchStatusProcess')
            break
    assert f.p(709)==0,(profile,mode,kind,entry['steps'][-1])
    entry['stopped_resume']=f.var('RemoteInterlockResumeFlag',width=1)
    entry['stopped_hmi']=f.p(398)
    f.var('RemoteInterlockStopFlag',0)
    f.call('SwitchStatusProcess')
    f.call('IndoorDisinfectExhaustAction')
    entry.update(final_sys=f.p(700),final_step=f.p(709),final_hmi=f.p(398),
        final_resume=f.var('RemoteInterlockResumeFlag',width=1))
    entry['passed']=(entry['stopped_resume']==1 and f.p(700)==4 and f.p(709)==2 and f.p(398)==1
                     if kind=='remote' else f.p(709)==0 and f.p(398)==0 and entry['final_resume']==0)
    return entry


def natural_completion(package,version,profile,mode,after):
    f=fixture(package,version,profile,mode)
    f.p(323,1);f.p(324,1);f.p(325,after);f.p(326,2)
    rows=[]
    for ms in range(201000,1000000,1000):
        f.var('Systick_1ms',ms)
        f.call('SwitchStatusProcess')
        f.call('IndoorDisinfectExhaustAction')
        rows.append(dict(ms=ms,sys=f.p(700),step=f.p(709),mode=f.p(236),
            hmi=f.p(398),special=f.p(885),resume=f.var('RemoteInterlockResumeFlag',width=1)))
        if after and f.p(236)==2 or not after and f.p(709)==0:break
    passed=(f.p(236)==2 and f.p(398)==1 and f.p(700)==4 if after else
            f.p(236)==mode and f.p(398)==0 and f.p(709)==0)
    passed&=f.var('RemoteInterlockResumeFlag',width=1)==0
    return dict(profile=profile,mode=mode,kind='natural_after_'+str(after),passed=bool(passed),steps=rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('package',type=Path)
    p.add_argument('version')
    p.add_argument('--expect-defect',action='store_true')
    args=p.parse_args()
    rows=[]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for mode in (3,4,5):
            for kind in ('remote','manual','fault'):
                row=scenario(ROOT/args.package,args.version,profile,mode,kind)
                rows.append(row)
                print(profile,mode,kind,'passed',row['passed'],'resume',row['stopped_resume'],flush=True)
            for after in (0,1):
                row=natural_completion(ROOT/args.package,args.version,profile,mode,after)
                rows.append(row)
                print(profile,mode,row['kind'],'passed',row['passed'],flush=True)
    remote=[r for r in rows if r['kind']=='remote']
    others=[r for r in rows if r['kind']!='remote']
    assert all(r['passed'] for r in others)
    assert all(r['passed'] is (not args.expect_defect) for r in remote)
    out=ROOT/args.package/'special_remote_ARM_20261106.json'
    out.write_text(json.dumps(dict(hardware_access=False,time_is_simulated=True,
        version=args.version,expected_known_defect=args.expect_defect,checks=rows),ensure_ascii=False,indent=2),'utf8')
    print('OFFLINE ARM RESULT',len(rows),out,flush=True)


if __name__=='__main__':main()
