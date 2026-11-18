"""Retry the real 300/120s test with batched raw-input transfers.

The first four-channel fixture wrote each channel separately and may not have
established continuous low temperature for the protection task. This reduces
transfer gaps, records read-only counters, and preserves the original failure.
No firmware, calculated temperature, protection counter, flag, or output writes.
"""
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
import nonvent_coil_real_time_20261109 as matrix
import subprocess,sys


class GroupedNtcInput(RawNtcInput):
    def __init__(self,b):
        self.continuity=[];self.next_diagnostic=0
        b.log['grouped_raw_input_fixture']=dict(
            transfer='Adjacent ADC/filter INPUT channels packed into three transfers, interval1ms',
            writes='ADbuffer,NTC_Val_Filter,NTC_AD only',
            read_only_counters=self.continuity)
        super().__init__(b)
    def loop(self):
        try:
            while not self.stop_event.is_set():
                with self.lock:values=dict(self.values)
                groups=[]
                for ch in sorted(values):
                    if not groups or ch!=groups[-1][-1]+1:groups.append([ch])
                    else:groups[-1].append(ch)
                for group in groups:
                    raw=[values[c] for c in group];first=group[0]
                    payload=struct.pack('<'+'H'*len(raw),*raw)
                    self.t.write_memory_block8(self.sy['ADbuffer'][0]+first*2,list(payload))
                    filtered=[v for v in raw for _ in range(20)]
                    self.t.write_memory_block8(self.sy['NTC_Val_Filter'][0]+first*self.stride,
                        list(struct.pack('<'+'H'*len(filtered),*filtered)))
                    self.t.write_memory_block8(self.sy['NTC_AD'][0]+first*2,list(payload))
                self.t.flush()
                if values and time.monotonic()>=self.next_diagnostic:
                    self.continuity.append(dict(at=now(),t=time.monotonic(),
                        low=list(struct.unpack('<8I',bytes(self.t.read_memory_block8(self.sy['evapLowCount'][0],32)))),
                        release=list(struct.unpack('<8I',bytes(self.t.read_memory_block8(self.sy['evapReleaseCount'][0],32)))),
                        sensor_status=list(self.t.read_memory_block8(self.sy['SensorStatus'][0]+9,4))))
                    self.next_diagnostic=time.monotonic()+1
                self.stop_event.wait(.001)
        except BaseException:self.error=traceback.format_exc()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('coil_grouped_retry_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after));dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q)
        matrix.RawNtcInput=GroupedNtcInput;matrix.run();restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8')
            q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
