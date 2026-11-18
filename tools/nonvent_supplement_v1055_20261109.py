"""Live non-ventilation follow-ups, with explicit simulated-input boundaries.

One serial writer, normal parameter changes; the optional-sensor check writes
only one SensorErr input byte located in the selected AXF. No output, demand,
history, target-count, runtime-counter or protection-timer writes.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench, paused
import subprocess, sys


def restored_latest():
    p=max(D.glob('remaining571_heat_dynamic_*.json'),key=lambda x:x.stat().st_mtime)
    d=json.loads(p.read_text('utf8'))
    assert d.get('restored') is True and not d.get('cleanup_error') and not d.get('restore_mismatches'),p
    return p


def unused_sensors(mode):
    b=CheckedBench('unused_sensor_inputs_mode_'+str(mode));ss=None
    cid='T03-117' if mode==0 else 'T03-118'
    e=dict(passed=False,runs=[],mode=mode,
        stimulus='Single SensorErr input latch; genuine raw sensor kept healthy',
        scope='Unused AI0/AI1/AI2/AI3/AI4/NTC2/NTC3 only; not electrical faults or unused compressor-coil probes')
    b.log['cases'][cid]=e;b.log['sensor_stimulus']=e['stimulus'];b.save()
    try:
        b.setup(mode)
        b.config({128:2 if mode==1 else 0,127:1,129:1,332:1,
            333:0,334:0,125:0,126:0,248:0,315:0,327:1,
            160:250,161:250,120:20,412:1,347:100,348:1,349:0,
            329:2,330:2,331:1,335:0,336:1,337:1,338:1,
            381:0,382:0,386:0,346:0,320:0,245:1,247:0,
            136:0,137:0,138:0,139:0})
        b.temperature(0,220);b.reset_faults();b.start()
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target

        def sample(label,index):
            s=b.snapshot(label)
            s.update(sensor_index=index,raw_status=t.read8(b.sy['SensorStatus'][0]+index),
                latch=t.read8(b.sy['SensorErr'][0]+index),
                partial_stop=t.read8(b.sy['IndoorSensorPartialStopFlag'][0]),
                actual_running=b.rd(119)[0])
            return s

        def healthy_load(s):
            expected_running=1 if mode==0 else 0
            feedback=sum(v in (2,3,4) for pair in s['outdoor_status'] for v in pair)
            return s['state'][9]==2 and all(s['do'][i] for i in (3,6,8)) and s['ao'][0]==1000 and s['partial_stop']==0 and s['actual_running']==feedback==expected_running

        for index in (0,1,2,3,4,7,8):
            paused();b.reset_faults();began=time.monotonic();rows=[]
            while True:
                s=sample('unused probe before',index);rows.append(s)
                if healthy_load(s) and s['raw_status']==s['latch']==0:break
                assert time.monotonic()-began<70,('optional probe healthy precondition unavailable',s)
                time.sleep(.15)
            # Reheat-enabled cooling intentionally retains at least one
            # compressor. Establish its genuine feedback; do not suppress or
            # write its target merely to satisfy a zero-compressor fixture.
            if mode==0 and index==0:
                runtime_case=dict(passed=False,scope='One actual compressor feedback; software cumulative runtime only',samples=[])
                b.log['cases']['T10-021']=runtime_case
                # Let the separate outdoor runtime poll blocks converge before
                # taking the baseline. Never assign runtime counter values.
                began=time.monotonic()
                while time.monotonic()-began<6:
                    z=sample('single compressor runtime poll settle',index);assert healthy_load(z),z
                    time.sleep(.2)
                def timed():
                    return dict(at=now(),t=time.monotonic(),state=sample('single compressor runtime',index),
                        comp=b.rd(2602,8),unit=b.rd(2670,4))
                before=timed();began=time.monotonic()
                while time.monotonic()-began<20:
                    paused();z=sample('single compressor twenty real seconds',index)
                    runtime_case['samples'].append(z);assert healthy_load(z),z;time.sleep(.2)
                after=timed()
                def totals(words):return [(words[i]<<16)|words[i+1] for i in range(0,len(words),2)]
                cd=[v-u for u,v in zip(totals(before['comp']),totals(after['comp']))]
                ud=[v-u for u,v in zip(totals(before['unit']),totals(after['unit']))]
                active=[i for i,v in enumerate(x for pair in after['state']['outdoor_status'] for x in pair) if v in (2,3,4)]
                assert len(active)==1
                k=active[0];elapsed=after['t']-before['t']
                runtime_case.update(before=before,after=after,actual_compressor_index=k,elapsed_s=elapsed,comp_delta=cd,unit_delta=ud)
                runtime_case['passed']=all(abs(v-(elapsed if i==k else 0))<3 for i,v in enumerate(cd)) and all(abs(v-(elapsed if i==k//2 else 0))<3 for i,v in enumerate(ud))
                b.record_local('T10-021',runtime_case['passed'],
                    f'V10.55制冷再热保留1台实际运行反馈，连续观察{elapsed:.2f}s；4压机累计增量{cd}、两外机累计增量{ud}，运行索引{k}。只核对软件累计秒数及停止设备不增长；未写计数，累计持久化、真实动力/断电与正式档另验。',runtime_case)
            r=dict(index=index,before=s,before_samples=rows,hold=[])
            e['runs'].append(r);b.save()
            r['write']=dict(address=b.sy['SensorErr'][0]+index,width=1,value=1,at=now())
            t.write8(r['write']['address'],1);t.flush();began=time.monotonic()
            while time.monotonic()-began<4:
                paused();s=sample('unused probe must not stop established heat',index);r['hold'].append(s)
                assert healthy_load(s) and s['raw_status']==0 and s['latch']==1,s
                time.sleep(.15)
            b.reset_faults();s=sample('unused probe normal reset',index)
            assert healthy_load(s) and s['latch']==0,s
            r.update(passed=True,recovered=s);b.save()
            print('UNUSED PROBE',mode,index,'PASS',flush=True)
        e['passed']=len(e['runs'])==7 and all(r['passed'] for r in e['runs'])
        b.record_local(cid,e['passed'],
            f'V10.55模式{mode}正常热输出先达到1000，'+('制冷启用再热先建立1台压机真实运行反馈；' if mode==0 else '非热泵制热压机保持停止；')+
            '7个未使用探头AI0/AI1/AI2/AI3/AI4/NTC2/NTC3逐一模拟SensorErr锁存，各保持4s，热量、送/回/排风及既有压机反馈保持，部分停机标志为0，524复位清除。仅未使用输入的下游资格门禁，未覆盖电气诊断、未用盘管、压机动力及端子。',e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']=e['stimulus'];dump(RESULTS,records)
    except BaseException:
        e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:b.reset_faults()
        finally:
            if ss:ss.close()
            b.finish()


def reconfigure_fans():
    b=CheckedBench('fan_runtime_reconfiguration');cid='T07-085'
    e=dict(passed=False,runs=[],mode=0,stimulus='Normal Modbus live configuration; AI3 engineering-map input',
        scope='Cold mode, no thermal demand; software enables and retired AO clearing; no terminal/PRODUCTION acceptance')
    b.log['cases'][cid]=e;b.save()
    try:
        b.setup(0);b.config({128:0,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:320,161:150,315:0,320:0,346:0,245:1,247:0,
            329:2,330:2,331:1,134:37,131:43,336:0,337:0,382:0,
            133:1,339:60,340:60,341:30,342:90,345:100})
        b.temperature(0,250);b.ai(3,100,20);b.reset_faults();b.start()
        for supply,returning,exhaust in ((1,1,1),(2,2,1),(3,2,1),(3,0,0),(2,2,1),(1,0,0)):
            b.config({329:supply,330:returning,331:exhaust})
            r=dict(config=[supply,returning,exhaust],settling=[],hold=[],passed=False)
            e['runs'].append(r);b.save();began=time.monotonic()
            def matches(s):
                return s['state'][9]==2 and s['do'][3]==1 and s['do'][6]==int(returning!=0) and s['do'][8]==exhaust and \
                    s['ao'][4]==(430 if returning==2 else 0) and \
                    (s['ao'][7]==0 if supply==1 else s['ao'][7]==370 if supply==2 else 300<=s['ao'][7]<=900)
            while True:
                paused();s=b.snapshot('fan live reconfiguration settle');r['settling'].append(s)
                if matches(s):break
                assert time.monotonic()-began<25,('fan live configuration did not settle',r['config'],s)
                time.sleep(.15)
            began=time.monotonic()
            while time.monotonic()-began<4:
                paused();s=b.snapshot('fan live reconfiguration hold');r['hold'].append(s)
                assert matches(s) and not any(s['faults']),s
                assert all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
                assert all(v==0 for pair in s['outdoor_status'] for v in pair),s
                time.sleep(.2)
            r['passed']=True;b.save();print('FAN RECONFIG',r['config'],'PASS',flush=True)
        e['stopped']=b.stop();assert loads_off(e['stopped'])
        e['passed']=all(r['passed'] for r in e['runs'])
        b.record_local(cid,e['passed'],
            'V10.55制冷无热湿需求，持续运行中切换送风开关/手动AO/自动AO，回风开关/手动AO/禁用，排风开关/禁用共6组；各组稳定4s核对DO许可及AO清理，自动档只核对合法范围；最后正常停机清零。AI3工程映射输入，非真实闭环扰动、物理端子或正式秒数。',e)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:b.finish()


def reconfigure_heat():
    b=CheckedBench('main_heat_runtime_reconfiguration');cid='T07-086'
    e=dict(passed=False,runs=[],mode=1,stimulus='Normal Modbus heat selection and legal room calibration',
        scope='Main heat AO/1:2/1:2:4/SCR/none route replacement at real PID full demand; preheat and independent reheat not in this sub-scope')
    b.log['cases'][cid]=e;b.save()
    try:
        b.setup(1);b.config({128:2,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,347:100,348:1,349:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0})
        b.temperature(0,220);b.reset_faults();b.start()
        wants={2:([0,0,0],1000),3:([1,1,0],0),4:([1,1,1],0),5:([1,1,0],1000),0:([0,0,0],0)}
        for kind in (2,3,4,5,0,5,2,0):
            b.config({128:kind});r=dict(kind=kind,settling=[],hold=[],passed=False)
            e['runs'].append(r);b.save();began=time.monotonic()
            def matches(s):
                return s['state'][9]==2 and s['do'][3]==1 and s['do'][:3]==wants[kind][0] and s['ao'][0]==wants[kind][1] and all(s['ao'][i]==0 for i in (1,2,8,9))
            while True:
                paused();s=b.snapshot('main heat live reconfiguration settle');r['settling'].append(s)
                if matches(s):break
                assert time.monotonic()-began<30,('main heat live configuration did not settle',kind,s)
                time.sleep(.15)
            began=time.monotonic()
            while time.monotonic()-began<4:
                paused();s=b.snapshot('main heat live reconfiguration hold');r['hold'].append(s)
                assert matches(s) and not any(s['faults']),s
                assert all(v==0 for pair in s['outdoor_status'] for v in pair),s
                time.sleep(.2)
            r['passed']=True;b.save();print('HEAT RECONFIG',kind,'PASS',flush=True)
        e['passed']=all(r['passed'] for r in e['runs'])
        b.record_local(cid,e['passed'],
            'V10.55非热泵制热，合法室温22℃由真实PID建立满需求；运行中主热依次AO→1:2→1:2:4→SCR→无→SCR→AO→无，共8次，每组稳定4s核对DA0/Y00/Y01/Y02与退役输出清理，其它热AO保持0、外机未运行。未写需求/PID/输出；本子范围不替代预热、独立再热重配置及端子验收。',e)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_supplement_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],
        ventilation='Deferred by user; no ventilation case in this batch')
    dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    assert previous.get('status')=='completed',previous
    restored_latest();q['status']='running';dump(journal,q)
    from remaining_eev_live_20261106 import main as eev
    actions=[('EEV-startup-correct-parameter-map',lambda:eev(startups=True)),
        ('unused-sensors-cooling',lambda:unused_sensors(0)),
        ('unused-sensors-heating',lambda:unused_sensors(1)),
        ('fans-live-reconfiguration',reconfigure_fans),('main-heat-live-reconfiguration',reconfigure_heat)]
    try:
        for name,fn in actions:
            paused();restored_latest();row=dict(name=name,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:fn();row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT SUPPLEMENT FINISHED',journal,flush=True)


if __name__=='__main__':main()
