"""Retry only after all existing non-ventilation controllers release COM6."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused
from nonvent_supplement_v1055_20261109 import restored_latest,unused_sensors
import subprocess,sys


def pressure_sensor_pair():
    b=CheckedBench('pressure_plus_AI3_latch');ss=None;cid='T05-042'
    e=dict(passed=False,phases=[],stimulus='Normal X15 polarity plus one SensorErr[3] input latch',
        scope='AI3 partial stop, then pressure whole stop, input release/latch retention and normal reset; active electrical AI3 reset/requalification not tested')
    b.log['cases'][cid]=e;b.save()
    try:
        b.setup(1);b.config({128:2,127:0,332:0,333:0,334:1,125:1,126:1,248:1,
            160:250,161:250,162:500,120:20,361:200,412:1,
            347:100,348:1,349:0,353:100,354:1,355:0,
            329:3,330:2,331:1,133:1,339:60,340:60,341:30,342:90,345:100,
            335:0,336:1,337:1,338:1,381:0,382:0,386:2,
            315:0,320:0,346:0,245:1,247:0})
        b.temperature(0,220);b.ai(1,300);b.ai(3,100,20)
        def contact(closed):
            if b.rd(1363)[0]!=closed:b.config({397:1-b.rd(397)[0]})
            began=time.monotonic()
            while b.rd(1363)[0]!=closed:
                assert time.monotonic()-began<6,('X15 polarity did not produce desired input',closed)
                time.sleep(.1)
        contact(1);b.reset_faults();b.start()
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target
        def sample(label):
            s=b.snapshot(label);s.update(pressure_input=b.rd(1363)[0],pressure_fault=b.rd(912)[0],
                ai3_fault=b.rd(617)[0],sensor_latch=t.read8(b.sy['SensorErr'][0]+3),
                raw_status=t.read8(b.sy['SensorStatus'][0]+3),
                partial_stop=t.read8(b.sy['IndoorSensorPartialStopFlag'][0]))
            return s
        def wait(label,predicate,seconds):
            p=dict(label=label,samples=[]);e['phases'].append(p);began=time.monotonic();heartbeat=began
            while True:
                paused();s=sample(label);p['samples'].append(s)
                if predicate(s):p['elapsed_s']=time.monotonic()-began;b.save();return s
                assert time.monotonic()-began<seconds,(label,s)
                if time.monotonic()-heartbeat>=20:
                    print('PRESSURE+AI3',label,round(time.monotonic()-began,1),s['state'][9],s['pressure_fault'],s['ai3_fault'],flush=True);heartbeat=time.monotonic();b.save()
                time.sleep(.12)
        def established(s):return s['state'][9]==2 and all(s['do'][i] for i in (3,6,8)) and s['ao'][0]>0 and s['ao'][2]>0
        e['before']=wait('main heat/humidity and fans established',lambda s:established(s) and s['raw_status']==s['sensor_latch']==s['pressure_fault']==0,35)
        p=dict(label='pressure closed during real arming60s',samples=[]);e['phases'].append(p);began=time.monotonic();heartbeat=began
        while time.monotonic()-began<65:
            paused();s=sample(p['label']);p['samples'].append(s)
            assert established(s) and s['pressure_input']==1 and s['pressure_fault']==0 and s['sensor_latch']==0,s
            if time.monotonic()-heartbeat>=25:
                print('PRESSURE ARM',round(time.monotonic()-began,1),flush=True);heartbeat=time.monotonic();b.save()
            time.sleep(.2)
        e['sensor_write']=dict(symbol='SensorErr[3]',address=b.sy['SensorErr'][0]+3,width=1,value=1,at=now())
        t.write8(e['sensor_write']['address'],1);t.flush()
        e['sensor_only']=wait('AI3 alone cuts loads, retains fans',lambda s:s['partial_stop']==1 and s['ai3_fault']==1 and s['pressure_fault']==0 and s['state'][9]==2 and all(s['do'][i] for i in (3,6,8)) and all(s['ao'][i]==0 for i in (0,1,2,8,9)),10)
        contact(0);e['both']=wait('armed pressure open adds whole-unit stop',lambda s:s['pressure_fault']==1 and s['ai3_fault']==1 and s['state'][9]==0 and loads_off(s),15)
        contact(1);p=dict(label='pressure input released, both latches stay without reset',samples=[]);e['phases'].append(p);began=time.monotonic()
        while time.monotonic()-began<4:
            s=sample(p['label']);p['samples'].append(s)
            assert s['pressure_input']==1 and s['pressure_fault']==s['sensor_latch']==s['ai3_fault']==1 and s['state'][9]==0 and loads_off(s),s
            time.sleep(.15)
        b.reset_faults();b.wr(398,0);b.start()
        e['recovered']=wait('healthy inputs plus normal reset recover loads',lambda s:established(s) and s['pressure_fault']==s['sensor_latch']==s['ai3_fault']==s['partial_stop']==0,40)
        e['passed']=True;b.record_local(cid,True,
            'V10.55制热主热/加湿及风机先建立；X15闭合真实等待65s后，仅模拟SensorErr[3]，冷热湿负载关闭而风机保留；再以DI极性令X15断开，持续故障触发送风压差锁存并停整机。X15恢复但未复位时两故障锁存仍在且不恢复；健康原始AI3及X15下524复位、正常开机恢复。未测AI3电气故障仍在时单独复位/重新诊断的反向路径，不把本子范围当完整多故障验收。',e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']=e['stimulus'];dump(RESULTS,records)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:
            b.config({397:b.polarities[397]});b.reset_faults()
        finally:
            if ss:ss.close()
            b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True)
    p.add_argument('--actions',nargs='+',choices=('unused','pressure'),default=('unused','pressure'))
    a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_unused_retry_controller_'+time.strftime('%H%M%S')+'.json')
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
        actions={'unused':('unused-cooling-retry-plus-single-runtime',lambda:unused_sensors(0)),
                 'pressure':('pressure-plus-AI3',pressure_sensor_pair)}
        for name,fn in (actions[key] for key in a.actions):
            paused();restored_latest();row=dict(name=name,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:fn();row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT UNUSED RETRY FINISHED',journal,flush=True)


if __name__=='__main__':main()
