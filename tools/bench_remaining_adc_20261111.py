"""ADC acquisition buffers only; diagnose through the running firmware."""
from joint_v1058_context_20261111 import *
from continuous_followups_v1055_20261109 import cold_config
import multiprocessing as mp
import queue
import struct
from continuous_special_stages_v1055_20261109 import paused


def raw_worker(board,sy,values,stop,out):
    out.cancel_join_thread();ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;p=sy['Parameter'][0];out.put(('ready',True));began=time.monotonic();next_read=0
        while not stop.is_set():
            assert time.monotonic()-began<3500,'ADC fixture duration limit'
            with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
            for ch,value in active.items():
                assert 0<=ch<sy['ADC_Val'][1]//2
                t.write16(sy['ADC_Val'][0]+2*ch,value)
                t.write_memory_block8(sy['ADC_Val_Filter'][0]+20*ch,list(struct.pack('<10H',*([value]*10))))
            t.flush();nt=time.monotonic()
            if nt>=next_read:
                out.put(('sample',dict(at=now(),t=nt,sensor_status=list(t.read_memory_block8(*sy['SensorStatus'])),
                    adc=list(struct.unpack('<'+'H'*(sy['ADC_Val'][1]//2),bytes(t.read_memory_block8(*sy['ADC_Val'])))),
                    alarms=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+1200,56)))),
                    output=list(t.read_memory_block8(*sy['output'])),
                    pressures=[t.read16(p+2*a) for a in (1443,1445)] if board[0]!='330' else None,
                    high_press_counts=list(struct.unpack('<2I',bytes(t.read_memory_block8(sy['HighPressCount'][0],8)))) if board[0]!='330' and 'HighPressCount' in sy else None,
                    phase=[t.read16(p+2*a) for a in (1420,1421)] if board[0]!='330' else None,
                    defrost_state=list(t.read_memory_block8(*sy['PSC316DefrostState'])) if board[0]!='330' else None,
                    layer=t.read16(p+3002) if board[0]!='330' else None)))
                next_read=nt+.3
            stop.wait(.002)
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


class ADCInputs:
    def __init__(self,b,indoor=False):
        self.b=b;self.indoor=indoor
        board=BOARDS[2] if indoor else BOARDS[0];sy=b.sy if indoor else b.outsy
        assert sy['ADC_Val_Filter'][1]==sy['ADC_Val'][1]*10
        # ADProcess in the selected AXF reads indoor AI0..4 from ADC3..7;
        # outdoor AI0..3 read ADC0..3. No converted AI/status writes.
        if not indoor:b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');self.values=ctx.Array('i',[-1]*8);self.stop=ctx.Event();self.out=ctx.Queue()
        self.proc=ctx.Process(target=raw_worker,args=(board,sy,self.values,self.stop,self.out),daemon=True)
        self.proc.start();kind,data=self.out.get(timeout=25);assert kind=='ready',(kind,data)
    def apply(self,ch=None,raw=None):
        with self.values.get_lock():
            self.values[:]=[-1]*8
            if ch is not None:self.values[ch+(3 if self.indoor else 0)]=raw
        return time.monotonic()
    def sample(self,after=0):
        if not getattr(self.b,'_cleaning_up',False):paused()
        until=time.monotonic()+8
        while time.monotonic()<until:
            try:kind,data=self.out.get(timeout=1)
            except queue.Empty:
                assert self.proc.is_alive(),'ADC fixture exited';continue
            if kind=='error':raise RuntimeError(data)
            if kind=='sample' and data['t']>=after and time.monotonic()-data['t']<2:return data
        raise TimeoutError('fresh ADC sample')
    def close(self):
        self.apply();self.stop.set();self.proc.join(10)
        if self.proc.is_alive():self.proc.terminate();self.proc.join(3)
        self.out.close()
        if not self.indoor:
            b=self.b;b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            b.outss.open();b.ot=b.outss.target
        assert self.proc.exitcode==0,'ADC fixture forced exit'


def ventilation():
    b=current_bench_class()('remaining_vent_AI');inp=None
    e=b.log['remaining_functional']=dict(kind='indoor_ADC_ventilation',cases=[],
        scope='Raw DMA/filter ADC upper/lower invalid proxies; physical open/short circuits and terminal voltages untested')
    scenarios=((0,'T03-013','T03-014'),(1,'T03-019','T03-020'),(2,'T03-025','T03-026'),
               (3,None,'T03-032'),(3,None,'T03-038'),(4,'T03-043','T03-044'))
    alarms={0:627,1:619,2:616,3:617,4:620}
    try:
        cold_config(b,2);b.config({330:2,328:30,132:30,135:30});b.start();inp=ADCInputs(b,True)
        def sample(after=0):
            s=inp.sample(after);s.update(snapshot=b.snapshot('ventilation ADC input'),alarm=None)
            return s
        def safe(s):
            q=s['snapshot'];return q['state'][9]==2 and all(q['do'][i] for i in (3,6,8)) and not any(q['ao'][i] for i in (0,1,2,8,9)) and all(v not in (2,3,4) for pair in q['outdoor_status'] for v in pair)
        for index,(ch,highid,lowid) in enumerate(scenarios):
            b.config({335:2 if ch in (0,2,4) else 1,377:1 if ch in (2,4) else 0})
            if ch==3:b.config({329:3,133:0 if index==4 else 1,339:60,340:60,341:30,342:90,343:720,344:100,345:100})
            b.config({1229+12*ch:1});b.reset_faults()
            for cid,raw in ((highid,4095),(lowid,0)):
                if cid is None:continue
                row=dict(id=cid,label=f'AI{ch}_raw{raw}',channel=ch,raw=raw,samples=[]);e['cases'].append(row);b.save()
                try:
                    at=inp.apply(ch,raw);end=time.monotonic()+28;seen=False
                    while time.monotonic()<end:
                        s=sample(at);s['alarm']=b.rd(alarms[ch])[0];row['samples'].append(s)
                        if s['sensor_status'][ch] and s['alarm']:
                            seen=True
                            if not safe(s):row['unsafe_observed']=True
                            row.setdefault('first_fault_t',s['t'])
                            if s['t']-row['first_fault_t']>=5:break
                    row.update(passed=seen and not row.get('unsafe_observed'),final=s)
                    if not seen:row['error']='raw invalid input did not establish configured diagnostic'
                except Exception as exc:row.update(passed=False,error=repr(exc))
                finally:
                    at=inp.apply();end=time.monotonic()+25
                    while time.monotonic()<end:
                        s=sample(at)
                        if s['sensor_status'][ch]==0:break
                    else:raise RuntimeError('ADC acquisition did not recover')
                    b.reset_faults();end=time.monotonic()+25
                    while time.monotonic()<end:
                        s=sample(at)
                        if b.rd(alarms[ch])==[0] and safe(s):row['recovery_verified']=True;break
                    else:raise RuntimeError('ventilation diagnostic recovery not verified')
                    row['finished']=now();b.save();print('VENT AI',cid,row.get('passed'),flush=True)
        # Disable only installed AI channels, inject their acquisition inputs,
        # and check the controller does not turn an unused AI into a stop.
        row=dict(id='T03-119',label='disabled_AI0_input_invalid',samples=[]);e['cases'].append(row)
        b.config({335:1,1229:0});at=inp.apply(0,0);end=time.monotonic()+7
        while time.monotonic()<end:
            s=sample(at);row['samples'].append(s)
        row.update(final=s,passed=all(safe(q) for q in row['samples']),finished=now())
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def pressure_sensors():
    from bench_remaining_outdoor_20261111 import HEAT
    b=current_bench_class()('remaining_outdoor_pressure_sensors');inp=None
    e=b.log['remaining_functional']=dict(kind='outdoor_pressure_ADC',cases=[],
        scope='1# four raw ADC pressure channels; ordinary330 demand, actual316 faults/output plus330 mirrors; no physical disconnection')
    try:
        b.setup(1);b.config(HEAT);b.temperature(0,220);b.reset_faults();b.start()
        b.wait('pressure diagnostic four heat precondition',lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),180)
        inp=ADCInputs(b)
        for ch,cid in ((0,'O-PROTECT-001'),(2,'O-PROTECT-002'),(1,'O-PROTECT-006'),(3,'O-PROTECT-007')):
            row=dict(id=cid,label=f'pressure_AI{ch}_raw0',channel=ch,samples=[]);e['cases'].append(row)
            offset=8+ch;wanted=[0,1] if ch in (0,2) else [1,0]
            try:
                # Establish the healthy run again after the previous case.
                end=time.monotonic()+200
                while time.monotonic()<end:
                    s=inp.sample()
                    if s['output'][:2]==[1,1] and not any(s['alarms']):break
                else:raise TimeoutError('healthy pressure case precondition')
                at=inp.apply(ch,0);end=time.monotonic()+180
                while time.monotonic()<end:
                    s=inp.sample(at);s.update(mirror=b.rd(2022+offset)[0],mirror_layer=b.rd(2598)[0],other=b.rd(1625,2))
                    row['samples'].append(s)
                    if s['alarms'][offset] and s['output'][:2]==wanted:
                        row['protection_seen']=True
                        if s['mirror'] and s['mirror_layer']==s['layer'] and s['other']==[3,3]:row['passed']=True;break
                row.setdefault('passed',False);row['final']=s
            except Exception as exc:row.update(passed=False,error=repr(exc))
            finally:
                at=inp.apply();end=time.monotonic()+180
                while time.monotonic()<end:
                    s=inp.sample(at)
                    if not any(s['alarms']) and not s['layer'] and not b.rd(2022+offset)[0]:row['recovery_verified']=True;break
                else:raise RuntimeError('pressure source/mirror recovery not verified')
                row['finished']=now();b.save();print('PRESSURE ADC',cid,row['passed'],flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('ventilation','pressure'));a=p.parse_args()
    ventilation() if a.action=='ventilation' else pressure_sensors()
