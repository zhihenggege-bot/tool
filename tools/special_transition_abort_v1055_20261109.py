"""Real auto disinfect-to-exhaust transition, then fire input simulation."""
from v1055_bench_context_20261109 import *
from remaining_pid_live_20261106 import *

def main():
    b=HeatBench('special_transition_abort_v1055')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    cid='T13-058'
    try:
        b.setup(5)
        b.config({329:2,330:0,331:1,335:1,336:1,337:1,338:1,
                  323:1,324:1,325:1,128:0,127:0,332:0,333:0,334:0,
                  245:1,247:0,125:0,126:0,248:0})
        b.reset_faults();b.start()
        entry=dict(passed=False,mode=5,kind='fire',scope='Actual auto disinfect-to-exhaust phase5 fire abort; manual transition abort remains untested',edges=[])
        b.log['cases'][cid]=entry;b.save()
        began=time.monotonic();last=None;last_report=began
        while True:
            s=b.snapshot('wait real auto interphase');diag=b.rd(885,3)
            s['special_diag']=diag
            if diag[0]!=last or time.monotonic()-last_report>=30:
                entry['edges'].append(s);b.save();last=diag[0];last_report=time.monotonic()
                print('AUTO TRANSITION WAIT',round(time.monotonic()-began,1),diag,flush=True)
            assert not any(s['faults']) and all(s['ao'][i]==0 for i in (0,1,2,8,9)),s
            if diag[0]==5:
                # Do not combine a pre-transition DO sample with a later phase
                # read. The phase5 wait lasts30s; confirm it on a fresh scan.
                s=b.snapshot('confirm real interphase outputs');diag=b.rd(885,3);s['special_diag']=diag
                if diag[0]!=5 or any(s['do'][i] for i in (3,8,10)):
                    time.sleep(.1);continue
                assert diag[1]>=60 and s['do'][10]==0 and s['do'][3]==0 and s['do'][8]==0,(diag,s)
                entry['before']=s;break
            assert time.monotonic()-began<260,('transition not reached',diag,s)
            time.sleep(.25)
        original=b.rd(156)[0];entry['original_polarity']=original;b.wr(156,1-original)
        entry['stopped']=b.wait('auto transition fire clears phase/output',lambda s:s['state'][9]==0 and loads_off(s) and b.rd(885)[0]==0,10,True)
        assert b.rd(605)[0]==1
        b.wr(156,original);time.sleep(.5);assert b.rd(605)[0]==1;b.reset_faults()
        hold=time.monotonic();entry['hold_samples']=[]
        while time.monotonic()-hold<10:
            s=b.snapshot('auto transition remains stopped');s['special_phase']=b.rd(885)[0];entry['hold_samples'].append(s)
            assert s['state'][9]==0 and loads_off(s) and s['special_phase']==0 and not any(s['faults']),s
            time.sleep(.3)
        b.start();entry['restart_diag']=b.rd(885,3);assert entry['restart_diag']==[1,0,0]
        entry.update(passed=True,finished=now())
        b.record_local(cid,True,'V10.55自动消排毒真实完成150秒阀等待、20秒风机等待及1分钟消毒，进入阶段5的30秒过渡等待后注入消防DI极性故障；负载软件输出、主步骤和[885]归零，排故复位后10秒无重启；新开机[885..887]=[1,0,0]。仅过渡阶段消防中止；手动中止、后续排毒阶段、物理接点/端子与正式档另验。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('AUTO TRANSITION RESTORED',b.log.get('restored'),flush=True)

if __name__=='__main__':main()
