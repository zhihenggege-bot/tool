"""Fault-phase display regression on the flashed bench, no control RAM writes."""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *

def main():
    b=HeatBench('special_display_v1055_valve_wait')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        for mode,cid in ((3,'T13-047'),(4,'T13-051'),(5,'T13-055')):
            runs=[];entry=dict(passed=False,mode=mode,runs=runs,scope='Valve-wait manual/phase/fire abort and display; physical inputs/other stages remain separate')
            b.log['cases'][cid]=entry;b.save()
            for kind,after in (('manual',0),('manual',1),('phase',1),('fire',1)):
                b.setup(mode)
                b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                          323:1,324:1,325:after,128:0,127:0,332:0,333:0,334:0,
                          245:1,247:0,125:0,126:0,248:0})
                b.reset_faults();b.start()
                before=b.wait('special valve wait established',lambda s:b.rd(885)[0]==1 and
                              not any(s['do'][i] for i in (3,8,10)),10)
                e=dict(kind=kind,after_policy=after,before=before,passed=False,samples=[]);runs.append(e);b.save()
                reg=155 if kind=='phase' else 156;began=time.monotonic()
                if kind=='manual':b.wr(398,0)
                else:
                    e['original_polarity']=b.rd(reg)[0];b.wr(reg,1-e['original_polarity'])
                stopped=b.wait('abort outputs and phase cleared',lambda s:s['state'][9]==0 and loads_off(s) and b.rd(885)[0]==0,12,allow_fault=kind!='manual')
                e.update(stopped=stopped,stop_observed_s=time.monotonic()-began,special_phase_after_stop=b.rd(885)[0])
                if kind!='manual':
                    assert b.rd(911 if kind=='phase' else 605)[0]==1
                    b.wr(reg,e['original_polarity']);time.sleep(.5)
                    assert b.rd(911 if kind=='phase' else 605)[0]==1
                    b.reset_faults()
                hold=time.monotonic()
                while time.monotonic()-hold<10:
                    s=b.snapshot('abort remains stopped');s['special_phase']=b.rd(885)[0];e['samples'].append(s)
                    assert s['state'][9]==0 and loads_off(s) and s['special_phase']==0 and not any(s['faults']),s
                    time.sleep(.25)
                e.update(passed=True,finished=now());b.save()
                print('DISPLAY ABORT PASS',mode,kind,'after',after,round(e['stop_observed_s'],3),flush=True)
            entry['passed']=True
            b.record_local(cid,True,f'V10.55：模式{mode}阀等待阶段手动停机（结束选择0/1）、相序和消防共4组，步骤0、负载软件输出及[885]均清零；排故复位后观察10秒无重启，显示保持0。修复回归，不代表其它阶段/端子/正式档验收。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('DISPLAY REGRESSION RESTORED',b.log.get('restored'),flush=True)

if __name__=='__main__':main()
