"""High-RH switch veto while manual humidifier output remains enabled.

Manual 168/169 are normal HMI controls, not an injected demand or output.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
from nonvent_supplement_v1055_20261109 import restored_latest
from remaining_pid_live_20261106 import ai_exact
import subprocess,sys,struct


def run():
    b=CheckedBench('auto_high_humidity_manual_humidifier_veto');ss=None;cid='T11-100'
    e=dict(passed=False,phases=[],stimulus='AI1 engineering mapping and normal manual humidifier controls168/169',
        scope='Heat mode high-humidity branch; genuine QHS60. Manual humidifier input is software simulation; no electrical/terminal qualification')
    b.log['cases'][cid]=e;b.save()
    try:
        b.setup(1);b.config({128:0,127:0,332:0,333:0,334:1,125:1,126:1,248:1,
            160:250,161:250,162:500,120:20,361:200,412:1,168:1,169:1,
            320:0,321:50,322:60,315:0,346:0,245:1,247:0,
            329:2,330:0,331:0,386:0})
        b.temperature(0,250);ai_exact(b,601);b.reset_faults();b.start()
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target
        def sample(label):
            s=b.snapshot(label);d=b.rd(872,22)
            s.update(mode=b.rd(236)[0],humidity=b.rd(501)[0],room=signed16(b.rd(511)[0]),
                switch_count=d[12],heat_demand=d[18],humidity_demand=d[20],
                active=t.read8(b.sy['IndoorActiveWorkMode'][0]),
                pending=struct.unpack('<i',struct.pack('<I',t.read32(b.sy['IndoorPendingWorkMode'][0])))[0])
            return s
        b.wait('manual humidifier genuine normal output established',lambda s:s['ao'][2]==1000,15)
        b.config({320:1});p=dict(label='high RH601 manual humidifier ON veto65s',samples=[]);e['phases'].append(p)
        began=time.monotonic();heartbeat=began
        while time.monotonic()-began<65:
            paused();s=sample(p['label']);p['samples'].append(s)
            assert s['mode']==s['active']==1 and s['pending']==-1 and s['switch_count']==0,s
            assert s['room']==250 and s['humidity']==601 and s['humidity_demand']==s['ao'][2]==1000 and not any(s['faults']),s
            if time.monotonic()-heartbeat>=20:
                print('HUMIDIFIER SWITCH VETO',round(time.monotonic()-began,1),flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.12)
        p['observed_s']=time.monotonic()-began;b.save();b.config({169:0})
        p=dict(label='manual humidifier OFF qualifies fresh QHS60',samples=[],marks={});e['phases'].append(p)
        began=time.monotonic();heartbeat=began
        while True:
            paused();s=sample(p['label']);p['samples'].append(s)
            assert s['humidity']==601 and s['room']==250 and not any(s['faults']),s
            if s['pending']==0 or s['mode']==0:break
            assert s['mode']==s['active']==1 and s['pending']==-1,s
            if s['humidity_demand']==s['ao'][2]==0:p['marks'].setdefault(s['switch_count'],s['monotonic'])
            assert time.monotonic()-began<65,('QHS60 not triggered',s)
            if time.monotonic()-heartbeat>=20:
                print('HUMIDIFIER OFF QUALIFY',s['switch_count'],flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.08)
        assert all(i in p['marks'] for i in range(2,60)),p['marks']
        p['trigger']=s;p['count2_to_trigger_s']=s['monotonic']-p['marks'][2]
        assert 57.5<=p['count2_to_trigger_s']<=58.5,p['count2_to_trigger_s']
        p['transition']=[];began=time.monotonic()
        while True:
            s=sample('normal heat to cool after humidifier off');p['transition'].append(s)
            assert not any(s['faults']),s
            if s['mode']==s['active']==0 and s['pending']==-1 and s['state'][9]==2:break
            assert time.monotonic()-began<160,s
            time.sleep(.2)
        e['passed']=True;b.record_local(cid,True,
            f'V10.55控湿制热，WD25/室温25℃，SD50/SDF20且AI1精确60.1%RH；正常手动加湿168/169保持AO和需求1000真实65s，自动转冷计时始终0。关闭手动加湿后实际输出与需求清0，重新连续QHS60后转冷，计数2至触发{p["count2_to_trigger_s"]:.3f}s，并完成旧模式退出至制冷步骤2。AI1工程映射与正常手动输入，非真实湿度/端子测量。',e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']=e['stimulus'];dump(RESULTS,records)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        if ss:ss.close()
        b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_auto_humidifier_gate_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],ventilation='Deferred by user');dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    assert previous.get('status')=='completed',previous
    restored_latest();q['status']='running';dump(journal,q)
    try:
        run()
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT AUTO HUMIDIFIER GATE FINISHED',journal,flush=True)


if __name__=='__main__':main()
