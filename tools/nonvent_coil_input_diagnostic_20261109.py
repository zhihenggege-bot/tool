"""Read-only protection counters while simulating one raw NTC input.

Diagnostic only: this cannot pass the missing 300/120-second cases.
"""
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
import subprocess,sys


class DiagnosticInput(RawNtcInput):
    def __init__(self,b):
        self.io=threading.Lock();super().__init__(b)
    def loop(self):
        try:
            while not self.stop_event.is_set():
                with self.lock:values=dict(self.values)
                with self.io:
                    for ch,v in values.items():
                        self.t.write16(self.sy['ADbuffer'][0]+ch*2,v)
                        self.t.write_memory_block8(self.sy['NTC_Val_Filter'][0]+ch*self.stride,list(struct.pack('<20H',*([v]*20))))
                        self.t.write16(self.sy['NTC_AD'][0]+ch*2,v)
                    self.t.flush()
                self.stop_event.wait(.012)
        except BaseException:self.error=traceback.format_exc()
    def read(self):
        with self.io:
            def words(k,n):return list(struct.unpack('<'+'I'*n,bytes(self.t.read_memory_block8(self.sy[k][0],4*n))))
            return dict(at=now(),t=time.monotonic(),low=words('evapLowCount',8),release=words('evapReleaseCount',8),
                sensors=list(self.t.read_memory_block8(self.sy['SensorStatus'][0],18)),
                raw_buffer=self.t.read16(self.sy['ADbuffer'][0]+8),raw_ntc=self.t.read16(self.sy['NTC_AD'][0]+8),
                converted=signed16(self.t.read16(self.sy['Parameter'][0]+515*2)))


def run():
    b=CheckedBench('coil_adc_continuity_diagnostic');fixture=None
    e=dict(completed=False,passed=False,samples=[],scope='Input fixture continuity diagnostic only; no 300/120s acceptance result')
    b.log['diagnostic']=e;b.save()
    try:
        b.setup(0);b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,315:0,320:0,346:0,245:1,247:0,
            329:2,330:0,331:0,110:5,111:-20,112:50,114:2,491:0})
        b.temperature(0,250);b.reset_faults();b.start()
        fixture=DiagnosticInput(b);fixture.set(4,-21)
        began=time.monotonic();heartbeat=began
        while time.monotonic()-began<25:
            paused();s=fixture.read();e['samples'].append(s)
            if time.monotonic()-heartbeat>=5:
                z=b.snapshot('coil continuity diagnostic status');e.setdefault('status_samples',[]).append(z)
                assert z['state'][9]==2 and not any(z['faults']),z
                print('COIL INPUT DIAGNOSTIC',round(time.monotonic()-began,1),s['low'],s['converted'],s['sensors'][9],flush=True)
                b.save();heartbeat=time.monotonic()
            time.sleep(.04)
        rows=e['samples'];e.update(completed=True,
            count_decreases=[dict(before=a,after=z) for a,z in zip(rows,rows[1:]) if z['low'][0]<a['low'][0]],
            converted_excursions=[s for s in rows if s['converted']!=-21],
            invalid_sensor_samples=[s for s in rows if s['sensors'][9]!=0],
            max_low_seconds=max(s['low'][0] for s in rows))
        b.save()
        print('COIL INPUT CONTINUITY RESULT',json.dumps({k:len(e[k]) for k in ('count_decreases','converted_excursions','invalid_sensor_samples')},ensure_ascii=False),'max low',e['max_low_seconds'],flush=True)
    except BaseException:b.log['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if fixture:fixture.close();time.sleep(2)
            b.stop()
        finally:b.finish()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('coil_input_diagnostic_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after));dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q);run();restored_latest()
        proc=subprocess.run([sys.executable,'-u','tools/check_v1055_final_readback_20261109.py'],cwd=R,capture_output=True,text=True,encoding='utf8')
        q['check']=dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
