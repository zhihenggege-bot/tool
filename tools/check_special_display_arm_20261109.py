"""Linked ARM regression: fault abort while waiting or running, both profiles."""
import argparse,json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware
R=Path(__file__).resolve().parents[1]

def run(package,version,profile,mode,stage,fault):
    f=Firmware(str(package/profile/f'PSC330_V{version}_{profile}.axf'))
    f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    for a,v in {1:mode,236:mode,214:3,709:0,700:0,163:0,164:0,166:0,
        323:5,324:5,325:0,329:2,330:0,331:1,328:0,132:0,135:0,
        335:0,336:0,337:0,338:0,381:0,386:0}.items():f.p(a,v)
    for a in range(250,258):f.p(a,1)
    f.var('X_02',1);f.var('Systick_1ms',30000);f.call('SwitchStatusProcess')
    f.p(398,1);f.call('SwitchStatusProcess');f.call('IndoorDisinfectExhaustAction')
    if stage=='running':
        for ms in (180000,200000):f.var('Systick_1ms',ms);f.call('IndoorDisinfectExhaustAction')
    before=f.p(885);assert before==(1 if stage=='valve_wait' else 4 if mode==4 else 3)
    if fault=='system':f.p(710,1)
    else:f.p(1406,1) # ModUrgencyStop = Parameter[PLCctrlPara(1400)+6]
    f.call('IndoorDisinfectExhaustAction')
    after=f.p(885);step=f.p(709)
    return dict(profile=profile,mode=mode,stage=stage,fault=fault,before=before,after=after,main_step=step,
                passed=after==0 and step==0)

def main():
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('version');p.add_argument('--expect-defect',action='store_true');args=p.parse_args()
    rows=[run(R/args.package,args.version,profile,mode,stage,fault)
        for profile in ('PRODUCTION','BENCH_ONLY_3S') for mode in (3,4,5)
        for stage in ('valve_wait','running') for fault in ('system','urgency')]
    out=R/args.package/'special_display_ARM_20261109.json'
    out.write_text(json.dumps(dict(hardware_access=False,time_simulated=True,checks=rows),indent=2),'utf8')
    assert all(r['passed']==(not args.expect_defect) for r in rows),rows
    print('ARM display checks',len(rows),'expected defect',args.expect_defect)

if __name__=='__main__':main()
