"""User-authorized sensor fault-input simulation on the live BENCH scheduler.

Write only one SensorErr byte at a time, located from the exact current AXF.
Open/short case pairs share this downstream evidence; electrical cause and ADC
diagnostic delay are explicitly untested. No control/output/timer RAM writes.
"""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import CheckedBench,paused

ALARM={0:627,1:619,2:616,3:617,4:620,5:618,6:604,7:600,8:599,
       9:612,10:613,11:614,12:615,13:623,14:624,15:625,16:626}
NAMES=['AI0房压','AI1回风湿度','AI2 CO2','AI3风压','AI3风速','AI4新风湿度']+[f'NTC{i}' for i in range(12)]


def thermal_off(s):
    return all(s['ao'][i]==0 for i in (0,1,2,8,9)) and all(s['do'][i]==0 for i in (0,1,2,11,13,14,15))


def run(mode):
    b=CheckedBench('sensor_latch_matrix_mode_'+str(mode));ss=None
    b.log.update(sensor_stimulus='Single SensorErr input byte via exact-image SWD symbol; raw sensor remains healthy',
        output_or_pid_ram_writes=False,physical_terminal_measurement=False,
        bypassed='ADC electrical detection, open/short distinction, diagnostic delay and reset with electrically active fault')
    try:
        inventory=json.loads((D/'pending_evidence_inventory_20261109.json').read_text('utf8'))
        missing={r['id'] for r in inventory['rows'] if not r['evidence']['board']}
        ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target
        b.log['ram_write_allowlist']={f'SensorErr[{i}]':b.sy['SensorErr'][0]+i for i in range(17)};b.save()
        b.setup(mode)
        b.temperature(0,220)
        b.ai(1,300);b.ai(0,5);b.ai(2,600);b.ai(3,100,20);b.ai(4,500)

        def config(sensor):
            values={128:2 if mode==1 else 0,127:1,129:1,332:1,333:1,
                125:1,126:1,248:1,334:1,160:250,161:250,162:500,168:0,
                347:10,348:1,349:0,350:10,351:1,352:0,353:10,354:1,355:0,
                412:1,120:20,361:200,315:0,327:1,374:1,375:100,376:40,
                329:2,330:2,331:1,328:0,132:0,135:0,
                335:0,336:1,337:1,338:1,377:0,381:0,382:0,
                386:0,346:0,320:0,136:0,137:0,138:0,139:0}
            if sensor==0:values.update({335:2,377:0})
            if sensor in (2,4):values.update({335:2,377:1})
            if sensor==3:values.update({329:3,133:1,339:60,340:60,341:30,342:90,345:100})
            if sensor==7:values.update({374:0,356:100,357:0})
            b.config(values)

        def sample(label,index):
            s=b.snapshot(label)
            s.update(t=time.monotonic(),sensor_index=index,
                raw_status=t.read8(b.sy['SensorStatus'][0]+index),
                sensor_latch=t.read8(b.sy['SensorErr'][0]+index),
                alarm=b.rd(ALARM[index])[0],partial_stop=t.read8(b.sy['IndoorSensorPartialStopFlag'][0]))
            return s

        def wait(label,index,predicate,seconds=40):
            began=time.monotonic();rows=[]
            while True:
                paused();s=sample(label,index);rows.append(s)
                if predicate(s):return s,rows
                assert time.monotonic()-began<seconds,(label,s)
                time.sleep(.15)

        def fans(s):return s['state'][9]==2 and all(s['do'][i] for i in (3,6,8))
        def established(s):return fans(s) and (thermal_off(s) if mode==2 else s['ao'][0]>0 and s['ao'][2]>0)

        for virtual,name in enumerate(NAMES):
            ids=[f'T03-{9+virtual*6+mode*2+bad:03d}' for bad in (0,1)]
            ids=[cid for cid in ids if cid in missing]
            if not ids:continue
            index=3 if virtual==4 else virtual-1 if virtual>4 else virtual
            if index>=13:
                b.log.setdefault('environment_skips',[]).append(dict(ids=ids,sensor=name,
                    reason='Only two outdoor units configured; required third/fourth unit not present. Do not pretend their cleared latch tests an enabled circuit.'))
                b.save();continue
            e=dict(passed=False,mode=mode,sensor=name,index=index,case_ids_sharing_downstream_scope=ids,
                stimulus='SensorErr latch input only; identical downstream fault for open/short labels',
                electrical_open_short_tested=False,diagnostic_delay_tested=False)
            b.log.setdefault('sensor_scenarios',[]).append(e);b.save()
            try:
                config(index)
                if virtual==4:b.config({133:0,343:720,344:100})
                b.reset_faults()
                if b.rd(709)[0]==0:b.start()
                before,rows=wait(name+' establish healthy loads',index,
                    lambda s:established(s) and s['raw_status']==0 and s['sensor_latch']==0 and s['alarm']==0)
                e.update(before=before,establish_samples=rows)
                assert b.rd(119)[0]==0,('This scope requires no compressors running; preserve before injecting',before)
                e['write']=dict(symbol=f'SensorErr[{index}]',address=b.sy['SensorErr'][0]+index,width=1,value=1,at=now())
                began=time.monotonic();t.write8(b.sy['SensorErr'][0]+index,1);t.flush()
                fault,rows=wait(name+' downstream fault stop',index,
                    lambda s:s['sensor_latch']==1 and s['alarm']==1 and s['partial_stop']==int(mode!=2) and fans(s) and thermal_off(s),12)
                e.update(fault=fault,fault_samples=rows,reaction_observed_s=time.monotonic()-began,hold=[])
                end=time.monotonic()+4
                while time.monotonic()<end:
                    paused();s=sample(name+' latch without reset',index);e['hold'].append(s)
                    assert s['raw_status']==0 and s['sensor_latch']==s['alarm']==1 and fans(s) and thermal_off(s),s
                    time.sleep(.2)
                if mode==2:
                    e['vent_stopped']=b.stop();b.wr(398,1)
                    e['vent_restart'],e['vent_restart_samples']=wait(name+' ventilation restart with fault',index,
                        lambda s:fans(s) and s['sensor_latch']==1 and thermal_off(s),30)
                b.reset_faults()
                e['recovered'],e['recovery_samples']=wait(name+' reset recovery',index,
                    lambda s:s['sensor_latch']==s['alarm']==s['partial_stop']==0 and established(s),40)
                e.update(passed=True,finished=now());b.save()
                actual=(f'【故障锁存输入模拟】V10.55模式{mode}/{name}，正常输出先建立后仅注入SensorErr[{index}]=1；'+(
                    '主热/再热及加湿软件输出关闭，风机风阀链保留；' if mode!=2 else '通风风机保留，带故障可正常停机再启动；')+
                    '健康原始输入下锁存保持4秒，524复位后恢复。开路/短路编号共用同一条下游模拟证据，未验证电气原因、ADC诊断延时或故障仍在时复位；本例未建立压机运行。')
                for cid in ids:
                    b.record_local(cid,True,actual,e)
                    records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']=b.log['sensor_stimulus'];dump(RESULTS,records)
                print('SENSOR SCENARIO PASS',mode,name,ids,flush=True)
            except Exception:
                e.update(error=traceback.format_exc(),finished=now());b.save()
                print('SENSOR SCENARIO UNFINISHED',mode,name,e['error'].splitlines()[-1],flush=True)
                for cid in ids:
                    b.record_local(cid,False,'故障输入模拟未完成；见原始前置/采样/恢复异常，未自动判固件缺陷。'+e['error'].splitlines()[-1],e)
            finally:
                # Raw inputs were never changed. Normal reset clears injected
                # latch; never write zero into the fault/output state to clean up.
                b.reset_faults();time.sleep(.4)
                assert t.read8(b.sy['SensorErr'][0]+index)==0,('reset failed to clear simulated latch',index)
        b.log['all_planned_sensor_scenarios_finished']=True
    except BaseException:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if ss:ss.close()
        b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',type=int,choices=(0,1,2),required=True);run(p.parse_args().mode)
