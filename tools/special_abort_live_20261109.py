"""V10.54 regression: manual/fault abort during genuine special valve wait."""
from remaining_pid_live_20261106 import *


def main():
    b=HeatBench('special_valve_wait_abort_20261109')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        for mode,cid in ((3,'T13-047'),(4,'T13-051'),(5,'T13-055')):
            runs=[]
            entry=dict(passed=False,runs=runs,scope='Valve-wait stage only; running/transition aborts remain separate')
            b.log['cases'][cid]=entry;b.save()
            for kind,after in (('manual',0),('manual',1),('phase',1),('fire',1)):
                b.setup(mode)
                b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                          323:1,324:1,325:after,128:0,127:0,332:0,333:0,334:0,
                          245:1,247:0,125:0,126:0,248:0})
                b.reset_faults();b.start()
                before=b.wait('actual special valve wait',lambda s:
                              b.rd(885)[0]==1 and not any(s['do'][i] for i in (3,8,10)),10)
                e=dict(kind=kind,after_policy=after,before=before,passed=False,samples=[])
                runs.append(e);b.save()
                reg=155 if kind=='phase' else 156
                began=time.monotonic()
                if kind=='manual':
                    b.wr(398,0)
                else:
                    e['original_polarity']=b.rd(reg)[0]
                    b.wr(reg,1-e['original_polarity'])
                stopped=b.wait('special abort loads cleared',lambda s:
                    s['state'][9]==0 and loads_off(s),
                    12,allow_fault=kind!='manual')
                e.update(stopped=stopped,stop_observed_s=time.monotonic()-began,
                         special_phase_after_stop=b.rd(885)[0])
                e['phase_display_cleared']=e['special_phase_after_stop']==0
                if kind=='manual':assert e['phase_display_cleared'],e
                elif not e['phase_display_cleared']:
                    b.log.setdefault('diagnostic_defects',[]).append(dict(mode=mode,kind=kind,
                        register=885,actual=e['special_phase_after_stop'],expected=0,
                        scope='Stale display after actual emergency stop; actuator stop is checked separately'))
                if kind!='manual':
                    assert any(stopped['faults']) or (kind=='phase' and b.rd(911)[0]==1),stopped
                    b.wr(reg,e['original_polarity']);time.sleep(.5)
                    e['healthy_without_reset']=b.snapshot('contact returned latch retained')
                    assert b.rd(911 if kind=='phase' else 605)[0]==1
                    b.reset_faults()
                hold=time.monotonic()
                while time.monotonic()-hold<10:
                    s=b.snapshot('abort must stay stopped');e['samples'].append(s)
                    s['special_phase']=b.rd(885)[0]
                    assert s['state'][9]==0 and loads_off(s),s
                    if kind=='manual':assert s['special_phase']==0,s
                    assert not any(s['faults']),s
                    time.sleep(.25)
                e.update(passed=True,finished=now());b.save()
                print('SPECIAL ABORT PASS',mode,kind,'after',after,round(e['stop_observed_s'],3),flush=True)
            entry['passed']=True
            entry['phase_display_defects']=[dict(kind=e['kind'],actual=e['special_phase_after_stop']) for e in runs if not e['phase_display_cleared']]
            b.record_local(cid,True,f'模式{mode}实际进入150秒开阀等待阶段后，手动停机（结束选择0/1各一例）、相序故障、消防故障共4组均停止到步骤0且负载软件输出清零；接点排故/复位后及手动停止后各观察10秒不自行重启。注意阶段显示[885]未清零问题={entry["phase_display_defects"]}，未修固件，不判整项验收通过。故障为正常DI极性模拟；仅阀等待阶段，其它阶段、物理接点、正式档待验。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SPECIAL ABORT RESTORED',b.log.get('restored'),flush=True)


if __name__=='__main__':main()
