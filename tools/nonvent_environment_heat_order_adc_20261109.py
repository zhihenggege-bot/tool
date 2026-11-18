"""Three heat full-load sequences with an explicit NTC2 ADC input fixture."""
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
import continuous_env_full_order_v1055_20261109 as matrix
import subprocess,sys


class InputBench(CheckedBench):
    def __init__(self,name):
        super().__init__(name+'_adc_input');self.fixture=None
        self.config({315:1,327:1,493:0})
        self.fixture=RawNtcInput(self);self.fixture.set(2,0)
        self.wait('raw environmental heat full-load input0C',lambda s:signed16(self.rd(512)[0])==0,10)
    def record_local(self,cid,passed,actual,entry):
        actual=actual.replace('合法校准，无需求/输出/计时RAM写入','NTC2原始ADC/滤波INPUT模拟0℃，其余正常配置；无需求/输出/计时RAM写入')
        super().record_local(cid,passed,actual,entry)
        data=json.loads(RESULTS.read_text('utf8'));data[cid]['inputs']='NTC2 raw ADC/filter INPUT simulation at0C; no demands/commands/output/timer forcing';dump(RESULTS,data)
    def finish(self):
        try:
            self.stop()
            if self.fixture:self.fixture.close();self.fixture=None;time.sleep(2)
        finally:super().finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('environment_heat_order_adc_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after),ventilation='Deferred by user');dump(path,q)
    try:
        while True:
            paused();d=json.loads(a.after.read_text('utf8'))
            if d.get('finished'):break
            time.sleep(3)
        assert d.get('status')=='completed',d;restored_latest();q['status']='running';dump(path,q)
        # Retest DA8 only under its actual fixed0 selector, preserving its first
        # rejected selector write and nonzero trace as historical evidence.
        from nonvent_da8_isolation_live_20261109 import main as da8
        da8();restored_latest();matrix.CheckedBench=InputBench;matrix.run(False);restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8');q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
