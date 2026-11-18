"""Single writer, four authorized follow-ups; no main queue or soak restart."""
import joint_v1242_context_20261112 as ctx
from joint_v1242_context_20261112 import *
import argparse
import importlib
import shutil

import continuous_special_stages_v1055_20261109 as pause_module
pause_module.PAUSE=R/'.codex-tmp/four_followups_pause.request'

def audit(label='four_followups_audit',image=False):
    import bench_current_20261112 as common
    common.DAY=DAY;common.I=I;common.BOARDS=BOARDS
    return common.audit(label,image)

def deploy():
    assert DAY.is_dir()
    evidence=R/'测试证据/台架执行_20261112/independent_audit_104045.json'
    q=json.loads(evidence.read_text('utf8'));assert q['verified']
    c=runtime.client()
    try:
        assert c.read_holding_registers(1,2622,18)==[330,10,59,2026,11,11,316,12,41,2026,11,11,316,12,41,2026,11,11]
        s=runtime.snap(c);assert c.read_holding_registers(1,398,1)==[0] and s['state'][9]==0 and loads_off(s)
    finally:c.close()
    m=json.loads((I/'manifest.json').read_text('utf8'))
    assert all(runtime.sha(R/p)==h for p,h in m['source_inventory'].items())
    assert all(runtime.sha(I/p)==h for p,h in m['artifacts'].items())
    dump(DAY/'preflight.json',dict(at=now(),prior_restoration_audit=str(evidence.relative_to(R)),
        snapshot=s,scope='Only the two316 boards change;330 image remains byte-identical',source_inventory=m['source_inventory']))
    runtime.result=lambda case,status,actual,path,restored='',inputs='':print('DEPLOY RECORD',case,status,flush=True)
    allboards=list(runtime.BOARDS)
    try:
        runtime.BOARDS[:]=allboards[:2]
        runtime.flash()
    finally:runtime.BOARDS[:]=allboards
    audit('post_v1242_flash_audit',True)

def scaling():
    from bench_remaining_outdoor_20261111 import HEAT,Inputs
    b=current_bench_class()('fixed50Hz_span');inp=None
    e=b.log['scaling']=dict(cases=[],scope='Normal330 heating request; software frequency/DA/relay only; no terminal measurement')
    try:
        b.setup(1);b.config(HEAT);b.gateway(1830,2);b.gateway(1831,4)
        b.config({1335:70,1336:50,1337:10,1338:10,1341:5})
        b.temperature(0,220);b.reset_faults()
        for maximum in (30,40,50):
            b.stop();b.config({1340:maximum,127:1})
            inp=Inputs(b,e);issued=inp.temperatures({0:69});b.wr(398,1)
            row=dict(maximum_hz=maximum,expected_speed10=maximum*10,expected_DA=maximum*20,samples=[])
            e['cases'].append(row);end=time.monotonic()+260;stable=None
            while time.monotonic()<end:
                s=inp.sample(issued);row['samples'].append(s)
                assert not any(s['alarms']),('scaling healthy precondition',s)
                matched=s['output'][:2]==[1,1] and s['OutdoorVfdSpeed']==maximum*10 and s['params']['1468']==maximum*20
                if matched:
                    if stable is None:stable=s['t']
                    if s['t']-stable>=6:
                        row.update(passed=True,final=s,finished=now());b.save();print('SCALING BOARD',maximum,'Hz',maximum*20,'DA PASS',flush=True);break
                else:stable=None
            else:raise TimeoutError(('scaling output',maximum))
            b.wr(398,0)
            while True:
                s=inp.sample()
                if not any(s['output'][i] for i in (0,1,2,3,7)):break
                assert time.monotonic()<end+220,'scaling normal fan rundown'
            inp.close();inp=None;b.stop()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:b.finish()

def contacts():
    import bench_contacts_recheck_20261112 as test
    test.run(recheck=True,channels=(4,5,7,1,6))

def timing(value):
    import bench_restart_diagnostics_20261112 as test
    test.run(value,pairs=((2,4),),initial_hold_seconds=0,require_both=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--value',type=int,default=60);a=p.parse_args()
    if a.action=='deploy':deploy();return
    if a.action=='audit':audit();return
    pause_module.paused()
    if a.action=='scaling':scaling()
    elif a.action=='typeII':
        import bench_typeII_regression_20261112 as test
        test.run()
    elif a.action=='contacts':contacts()
    elif a.action=='minrun':timing(a.value)
    else:raise ValueError(a.action)
    audit('after_'+a.action+'_audit')

if __name__=='__main__':main()
