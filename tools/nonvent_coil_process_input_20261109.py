"""Independent raw-input writer avoids parent JSON/GIL pauses; no firmware edits.

Only ADC/filter acquisition inputs are simulated. All protection counters,
computed temperatures, flags, demands, feedback and outputs remain read-only.
"""
from nonvent_ntc_input_boundaries_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
import nonvent_coil_real_time_20261109 as matrix
import multiprocessing as mp
import queue, subprocess, sys


def input_worker(board,sy,values,stop,out):
    ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target
        table=list(struct.unpack('<201f',bytes(t.read_memory_block8(sy['NTCtable'][0],804))))
        out.put(('ready',table));next_diag=0;began=time.monotonic();longest_gap=0;previous=began
        while not stop.is_set():
            assert time.monotonic()-began<1500,'Input-only worker maximum duration reached'
            with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
            groups=[]
            for ch in sorted(active):
                if not groups or ch!=groups[-1][-1]+1:groups.append([ch])
                else:groups[-1].append(ch)
            for group in groups:
                raw=[active[c] for c in group];first=group[0]
                payload=struct.pack('<'+'H'*len(raw),*raw)
                t.write_memory_block8(sy['ADbuffer'][0]+first*2,list(payload))
                filtered=[v for v in raw for _ in range(20)]
                t.write_memory_block8(sy['NTC_Val_Filter'][0]+first*40,list(struct.pack('<'+'H'*len(filtered),*filtered)))
                t.write_memory_block8(sy['NTC_AD'][0]+first*2,list(payload))
            t.flush();now_t=time.monotonic();longest_gap=max(longest_gap,now_t-previous);previous=now_t
            if active and now_t>=next_diag:
                row=dict(at=now(),t=now_t,low=list(struct.unpack('<8I',bytes(t.read_memory_block8(sy['evapLowCount'][0],32)))),
                    release=list(struct.unpack('<8I',bytes(t.read_memory_block8(sy['evapReleaseCount'][0],32)))),
                    flags=[t.read16(sy['Parameter'][0]+2*a) for a in range(640,648)],
                    converted_temp10=[signed16(t.read16(sy['Parameter'][0]+2*a)) for a in (515,516,514,517)],
                    sensor_status=list(t.read_memory_block8(sy['SensorStatus'][0]+9,4)),max_transfer_gap_s=longest_gap)
                out.put(('diagnostic',row));longest_gap=0;next_diag=now_t+1
            stop.wait(.001)
        out.put(('stopped',dict(at=now(),duration_s=time.monotonic()-began)))
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


class ProcessNtcInput:
    def __init__(self,b):
        self.b=b;self.sy=b.sy;self.error=None;self.lock=threading.Lock()
        ctx=mp.get_context('spawn');self.values=ctx.Array('i',[-1]*12);self.stop_event=ctx.Event();self.out=ctx.Queue()
        self.log=dict(scope='Independent process writes only raw ADC/filter input values; counters/status are read-only',events=[],read_only_counters=[])
        b.log['raw_ntc_input_fixture']=self.log
        self.worker=ctx.Process(target=input_worker,args=(BOARDS[2],self.sy,self.values,self.stop_event,self.out),daemon=True)
        self.worker.start();kind,value=self.out.get(timeout=30)
        assert kind=='ready',(kind,value)
        self.table=value;self.collect_stop=threading.Event();self.collector=threading.Thread(target=self.collect,daemon=True);self.collector.start();b.save()
    def collect(self):
        while not self.collect_stop.is_set():
            try:kind,value=self.out.get(timeout=.2)
            except queue.Empty:continue
            if kind=='diagnostic':self.log['read_only_counters'].append(value)
            elif kind=='error':self.error=value;self.log['error']=value
            elif kind=='stopped':self.log['worker_stopped']=value
    def set(self,ch,temp10):
        assert 0<=ch<12 and -400<=temp10<=1000
        i=int(math.floor(temp10/10))+50;f=temp10/10-(i-50)
        resistance=self.table[i]+f*(self.table[i+1]-self.table[i])
        raw=round((2.048*resistance/(5.1+resistance))/.0000625);assert 5<raw<32760
        applied_before=time.monotonic()
        with self.values.get_lock():self.values[ch]=raw
        self.log['events'].append(dict(at=now(),t=applied_before,channel=ch,requested_temp10=temp10,adc=raw));self.b.save();return raw
    def close(self):
        self.stop_event.set();self.worker.join(10)
        assert not self.worker.is_alive(),'Raw input worker did not stop'
        time.sleep(.3);self.collect_stop.set();self.collector.join(2);self.out.close()
        self.log.update(stopped=now(),exitcode=self.worker.exitcode,error=self.error);self.b.save()
        assert self.worker.exitcode==0 and not self.error,(self.worker.exitcode,self.error)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    path=D/('coil_process_controller_'+time.strftime('%H%M%S')+'.json');q=dict(started=now(),status='waiting_without_hardware',dependency=str(a.after));dump(path,q)
    try:
        while True:
            paused();prior=json.loads(a.after.read_text('utf8'))
            if prior.get('finished'):break
            time.sleep(3)
        assert prior.get('status')=='completed',prior
        restored_latest();q['status']='running';dump(path,q)
        matrix.RawNtcInput=ProcessNtcInput;matrix.run();restored_latest();q['checks']=[]
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8');q['checks'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(path,q);assert proc.returncode==0
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:q['finished']=now();dump(path,q)
