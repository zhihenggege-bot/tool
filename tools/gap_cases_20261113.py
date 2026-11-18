"""Targeted cases using normal protocol and continuous consumed-input evidence."""
from gap_capture_20261113 import *
from bench_remaining_outdoor_20261111 import HEAT
from remaining529_manual_defrost_input_20261105 import manual_defrost
from continuous_special_stages_v1055_20261109 import paused
import multiprocessing as mp
import queue
import threading
import math


def wait(b,row,label,reader,predicate,seconds,hold=0):
    end=time.monotonic()+seconds;first=None;heartbeat=0
    while time.monotonic()<end:
        paused();s=reader();row.setdefault('samples',[]).append(s)
        event('case_sample',label=label,sample=s)
        if predicate(s):
            if first is None:first=s['t']
            if s['t']-first>=hold:
                row[label]=s;b.save();return s
        else:first=None
        if time.monotonic()-heartbeat>25:
            heartbeat=time.monotonic();b.save();print('CAPTURE',label,flush=True)
        time.sleep(.12)
    raise TimeoutError(label)


def manual(include_second_fan=False,require_indoor_alarm=False):
    b=Bench('manual_protection_stopped_configuration')
    e=b.log['targeted_rerun']=dict(kind='manual_protection',cases=[],
        scope='Manual commands configured with330 SysStep0 and1300 enabled first; global polarity inputs affect both boards; actual consumed DI, protection, mirrors and recovery')
    b.attach_extra()
    targets=[(b.ot,b.outsy),(b.extra[0][1].target,b.extra[0][2])]
    originals={ch:b.rd(ch+2)[0] for ch in (0,1,6,4,5)}
    def read(ch,alarm):
        s=dict(at=now(),t=time.monotonic(),manual=b.rd(1300,18),step=b.rd(709)[0],
               reset_window330=b.rd(1402)[0],boards=[])
        it=b.extra[1][1].target;isy=b.extra[1][2]
        s['indoor_alarm']=dict(flag=b.rd(861)[0],total=b.rd(703)[0],
                              Y05=it.read8(isy['output'][0]+5),Y05_mirror=b.rd(819)[0],
                              manual_alarm_test=b.rd(1318)[0])
        for key in ('PSC316ResetGeneration','PSC316ResetAck','PSC316BusResetGeneration'):
            if key in isy:
                a,n=isy[key];s[key]=list(struct.unpack('<'+'H'*(n//2),bytes(it.read_memory_block8(a,n))))
        for index,(t,sy) in enumerate(targets):
            p=sy['Parameter'][0]
            q=dict(raw=t.read8(sy[f'X_{ch:02d}'][0]),qualified=t.read8(sy[f'X{ch:02d}_En'][0]),
                   polarity=t.read16(p+2*(ch+2)),alarm=t.read16(p+2*alarm),
                   layer=t.read16(p+3002),output=list(t.read_memory_block8(*sy['output'])),
                   manual=list(struct.unpack('<10H',bytes(t.read_memory_block8(p+2600,20)))),
                   mirror=b.rd(2022+index*128+alarm-600)[0],
                   reset_input=t.read16(p+2*1402),
                   high_pressure=[t.read16(p+2*a) for a in (1443,1445)],
                   sensor_status=list(t.read_memory_block8(*sy['SensorStatus'])))
            for name in ('CompRunTime','EnableCheckLow'):
                a,n=sy[name];q[name]=list(struct.unpack('<'+'I'*(n//4),bytes(t.read_memory_block8(a,n))))
            s['boards'].append(q)
        return s
    def enable():
        assert b.rd(709)==[0]
        b.config({1300:1})
        b.config({1318:0})
        b.config({1301:1,**{a:1 for a in range(1302,1308)},**{a:1 for a in range(1310,1316)}})
    try:
        b.setup(1);b.config({**HEAT,27:1});b.temperature(0,220);b.reset_faults()
        cases=((0,606,True),(1,600,False),(6,626,True),(4,621,True))
        if include_second_fan:cases+=((5,622,True),)
        for ch,alarm,latched in cases:
            row=dict(channel=ch,alarm=alarm,started=now());e['cases'].append(row)
            changed=False;reader=lambda:read(ch,alarm)
            try:
                enable()
                wait(b,row,'both_boards_manual_healthy',reader,
                     lambda s:all(q['output'][:2]==[1,1] and q['manual'][0]==1 and not q['raw'] and not q['alarm'] for q in s['boards']),85,2)
                if ch==1:
                    wait(b,row,'low_pressure_detection_enabled',reader,
                         lambda s:all(q['CompRunTime'][0]>1 and q['EnableCheckLow'][0] for q in s['boards']),45)
                b.config({ch+2:1-originals[ch]});changed=True
                # Both installed axial-fan fault inputs stop the whole outdoor
                # unit (spec 4.6.6); X05 must use the same verdict as X04.
                expected=[0,0] if ch in (4,5) else [0,1]
                wait(b,row,'protected_and_mirrored',reader,
                     lambda s:all(q['raw']==q['qualified']==q['alarm']==q['mirror']==1 and q['output'][:2]==expected for q in s['boards']) and
                     (not require_indoor_alarm or s['indoor_alarm']['flag']==s['indoor_alarm']['Y05']==1),70,6)
                if latched:
                    b.reset_faults()
                    wait(b,row,'reset_with_source_active_still_protected',reader,
                         lambda s:all(q['raw']==q['alarm']==1 and q['output'][:2]==expected for q in s['boards']),20,4)
                b.config({ch+2:originals[ch]});changed=False
                if latched:
                    released=wait(b,row,'source_released_before_reset',reader,lambda s:all(q['raw']==q['qualified']==0 for q in s['boards']),40,2)
                    row['latch_retained']=all(q['alarm']==1 for q in released['boards'])
                    b.reset_faults()
                wait(b,row,'source_alarm_mirror_clear',reader,
                     lambda s:all(not q['raw'] and not q['alarm'] and not q['layer'] and not q['mirror'] for q in s['boards']) and
                     (not require_indoor_alarm or s['indoor_alarm']['flag']==s['indoor_alarm']['Y05']==0),70,2)
                wait(b,row,'healthy_manual_outputs_recovered',reader,
                     lambda s:all(q['output'][:2]==[1,1] and not q['alarm'] and not q['layer'] for q in s['boards']),30,2)
                row['passed']=not latched or row['latch_retained']
            except Exception:
                row.update(passed=False,error=traceback.format_exc());event('case_exception',case='manual',channel=ch,error=row['error'])
            finally:
                if changed:b.config({ch+2:originals[ch]})
                b.reset_faults()
                wait(b,row,'recovery_input_fault_verified',reader,
                     lambda s:all(not q['raw'] and not q['alarm'] and not q['layer'] and not q['mirror'] for q in s['boards']),55,2)
                b.config({**{a:0 for a in range(1302,1318)},1301:0,1300:0})
                wait(b,row,'manual_outputs_off',reader,lambda s:all(not any(q['output'][:2]) for q in s['boards']),25,1)
                row['finished']=now();b.save();print('MANUAL RERUN',ch,row.get('passed'),flush=True)
    finally:
        try:
            b.config({ch+2:v for ch,v in originals.items()})
            b.reset_faults();b.config({**{a:0 for a in range(1302,1318)},1301:0,1300:0})
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save()


def analog(channel):
    from bench_remaining_adc_20261111 import ADCInputs
    from app import Psc330MonitorApp
    b=Bench('defrost_analog_pressure_'+str(channel));inp=None
    e=b.log['targeted_rerun']=dict(kind='defrost_analog_pressure',channel=channel,samples=[],
        scope='Normal330 AI engineering spans; ADC acquisition read-only; actual defrost and alarm masking. Physical pressure calibration and unspecified analog exit threshold separate')
    base=2680+12*channel;old={a:b.rd(a)[0] for a in (base+4,base+5)}
    e['ai_original']=old
    m=object.__new__(Psc330MonitorApp);m.values={};m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)
    def write(a,v):
        if signed16(b.rd(a)[0])!=v:m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
    def scale(low,high):
        event('pressure_span_issue',channel=channel,low=low,high=high)
        if low>=signed16(b.rd(base+5)[0]):write(base+5,high)
        write(base+4,low);write(base+5,high)
    def read():
        s=inp.sample();s.update(mirror_phase=b.rd(1550,2),mirror_alarm=b.rd(2028+channel)[0],
                               peer=b.rd(1625,2),owner=b.extra[1][1].target.read8(b.extra[1][2]['PSC316DefrostOwner'][0]))
        return s
    try:
        b.setup(1);b.config({**HEAT,56:3800});b.temperature(0,220)
        scale(3600,3601);b.gateway(1856,2);b.gateway(1857,2)
        b.attach_extra();inp=ADCInputs(b)
        wait(b,e,'stable_healthy_pressure',read,lambda s:s['pressures'][channel]==3600,20,3)
        b.reset_faults()
        wait(b,e,'healthy_before_start',read,lambda s:not any(s['alarms']) and not any(s['sensor_status'][:4]),20,2)
        b.start();b.wait('analog rerun four heat',lambda s:all(v==3 for q in s['outdoor_status'] for v in q),240)
        b.wr(540,1);manual_defrost(b,True,session=b.extra[1][1])
        wait(b,e,'actual_defrost_qualified',read,lambda s:s['phase']==s['mirror_phase']==[8,8] and s['defrost_state']==[1] and s['output'][:2]==[1,1],65,2)
        scale(3801,3802)
        high=wait(b,e,'high_pressure_in_actual_defrost',read,
                  lambda s:s['pressures'][channel]==3801 and s['defrost_state']==[1] and s['phase']==[8,8],20,4)
        exact=[s for s in e['samples'] if s['pressures'][channel]==3801 and s['defrost_state']==[1]]
        e['continuous_high_defrost_s']=exact[-1]['t']-exact[0]['t']
        e['alarm_masked']=all(not s['alarms'][6+channel] and not s['mirror_alarm'] for s in exact)
        e['compressor_observations']=[s['output'][:2] for s in exact]
        e['passed']=e['alarm_masked'] and e['continuous_high_defrost_s']>=3
        scale(3600,3601)
        wait(b,e,'high_source_removed',read,lambda s:s['pressures'][channel]==3600,20,2)
        b.save();print('ANALOG RERUN',channel,e.get('passed'),flush=True)
    except BaseException:
        e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            scale(signed16(old[base+4]),signed16(old[base+5]))
            e['ai_restored']=all(b.rd(a)[0]==v==b.ot.read16(b.outsy['Parameter'][0]+2*(302+a-2680)) for a,v in old.items())
            assert e['ai_restored'];b.reset_faults()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save()


def partner():
    b=Bench('defrost_partner_30s_legal_environment')
    e=b.log['targeted_rerun']=dict(kind='defrost_partner_30s',samples=[])
    fixture=None
    def read():
        with fixture.lock:
            s=sample(b,'defrost_partner_30s')
        s['target']=b.rd(881)[0];s['fresh_temperature10']=signed16(b.rd(512)[0])
        s['fixture_error']=fixture.error
        assert not fixture.error,fixture.error
        return s
    try:
        b.setup(1)
        e.update(fresh_air_temperature10=140,full_load_endpoint10=0,zero_load_endpoint10=150,
                 scope='Raw330 NTC2 acquisition/filter input at14C; legal environment endpoints0/15C yield one demand. No converted-temperature/demand/timer/output writes; actual state counter and software edges')
        b.config({**HEAT,127:0,315:1,327:1,38:0,318:0,319:150})
        b.gateway(1856,2);b.gateway(1857,2);b.reset_faults();b.attach_extra()
        fixture=IndoorNtcFixture(b,2,140)
        end=time.monotonic()+15
        while abs(signed16(b.rd(512)[0])-140)>1:
            assert time.monotonic()<end,'FreshNTC2 input did not establish14C';time.sleep(.1)
        b.start()
        before=wait(b,e,'one_actual_compressor',read,
                    lambda s:s['target']==1 and sum(sum(q['output'][:2]) for q in s['boards'])==1,240,3)
        unit=next(i for i,q in enumerate(before['boards']) if any(q['output'][:2]));running=before['boards'][unit]['output'][:2].index(1);other=1-running
        e.update(unit=unit+1,running_compressor=running+1,partner=other+1)
        b.wr(540,unit+1)
        with fixture.lock:manual_defrost(b,True,session=b.extra[1][1])
        active=wait(b,e,'actual_defrost_started',read,lambda s:s['boards'][unit]['PSC316DefrostState']==[1],60)
        started=wait(b,e,'partner_started',read,lambda s:s['boards'][unit]['output'][other]==1,50)
        rows=[s for s in e['samples'] if s['boards'][unit]['PSC316DefrostState']==[1]]
        counter=started['boards'][unit]['PSC316DefrostStateTime'][0]
        e.update(partner_start_counter_s=counter,observed_from_first_active_s=started['t']-active['t'],
                 passed=active['boards'][unit]['output'][other]==0 and 30<=counter<=34 and
                 all(s['boards'][unit]['output'][running]==1 for s in rows) and
                 not any(s['boards'][unit]['output'][other] and s['boards'][unit]['PSC316DefrostStateTime'][0]<30 for s in rows))
        b.save();print('PARTNER RERUN',e['passed'],counter,flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if fixture:fixture.close()
            b.finish()
        finally:e['finished']=now();b.save()


class IndoorNtcFixture:
    def __init__(self,b,ch,temp10):
        self.b=b;self.ch=ch;self.t=b.extra[1][1].target;self.sy=b.extra[1][2]
        self.lock=threading.RLock();self.stop=threading.Event();self.error=None
        table=struct.unpack('<201f',bytes(self.t.read_memory_block8(self.sy['NTCtable'][0],804)))
        cal=signed16(b.rd(495-ch)[0]);value=temp10-cal;i=math.floor(value/10)+50;fraction=value/10-(i-50)
        resistance=table[i]+fraction*(table[i+1]-table[i])
        self.raw=round(2.048*resistance/(5.1+resistance)/.0000625)
        self.trace=DAY/('partner_NTC2_input_'+time.strftime('%H%M%S')+'.jsonl')
        b.log['NTC_fixture']=dict(channel=ch,requested_temperature10=temp10,calibration10=cal,raw=self.raw,trace=str(self.trace.relative_to(R)))
        self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
    def worker(self):
        try:
            previous=time.monotonic();last=0;gap=0
            with self.trace.open('a',encoding='utf8',buffering=1) as f:
                while not self.stop.is_set():
                    with self.lock:
                        t=self.t;sy=self.sy;ch=self.ch;v=self.raw
                        t.write16(sy['ADbuffer'][0]+2*ch,v)
                        t.write_memory_block8(sy['NTC_Val_Filter'][0]+40*ch,list(struct.pack('<20H',*([v]*20))))
                        t.write16(sy['NTC_AD'][0]+2*ch,v);t.flush()
                        nt=time.monotonic();gap=max(gap,nt-previous);previous=nt
                        if nt-last>=.2:
                            row=dict(at=now(),t=nt,max_input_write_gap_s=gap,requested_raw=v,
                                acquired_raw=t.read16(sy['ADbuffer'][0]+2*ch),consumed_raw=t.read16(sy['NTC_AD'][0]+2*ch),
                                fresh_temperature10=signed16(t.read16(sy['Parameter'][0]+2*512)),
                                sensor_status=list(t.read_memory_block8(*sy['SensorStatus'])))
                            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();gap=0;last=nt
                    self.stop.wait(.003)
        except BaseException:self.error=traceback.format_exc()
    def close(self):
        self.stop.set();self.thread.join(10)
        assert not self.thread.is_alive(),'NTC input worker failed to close'
        assert not self.error,self.error


def run(action):
    if action=='manual':manual()
    elif action.startswith('analog'):analog(int(action[-1]))
    elif action=='partner':partner()
    elif action=='ai':ai_diagnostics()
    elif action=='recover-manual':recover_manual()
    else:raise ValueError(action)


def recover_manual():
    source=max(DAY.glob('rerun_manual_protection_stopped_configuration_*.json'),key=lambda p:p.stat().st_mtime)
    prior=json.loads(source.read_text('utf8'))
    b=Bench('manual_ordered_restore_recheck')
    b.original.update(prior['original']);b.touched.update(map(int,prior['original']))
    b.gateway_original.update({int(a):v for a,v in prior.get('gateway_original',{}).items()})
    b.log['recovery_source']=str(source.relative_to(R));b.save();b.finish()


def ai_worker(board,sy,values,stop,out,trace):
    """Only ADC acquisition/filter inputs are written; AD_Val/AI read-only."""
    out.cancel_join_thread();ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;p=sy['Parameter'][0];out.put(('ready',True));last=0
        with Path(trace).open('a',encoding='utf8',buffering=1) as f:
            while not stop.is_set():
                with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
                for ch,v in active.items():
                    t.write16(sy['ADC_Val'][0]+2*ch,v)
                    t.write_memory_block8(sy['ADC_Val_Filter'][0]+20*ch,list(struct.pack('<10H',*([v]*10))))
                t.flush();nt=time.monotonic()
                if nt-last>=.15:
                    s=dict(at=now(),t=nt,requested_raw=active)
                    for name,width in (('ADC_Val',2),('AD_Val',2),('AI',2),('SensorStatus',1),('SensorErrCount',4),('output',1),('DA',2)):
                        a,n=sy[name];raw=bytes(t.read_memory_block8(a,n))
                        s[name]=list(raw) if width==1 else list(struct.unpack('<'+('H' if width==2 else 'I')*(n//width),raw))
                    s['alarm_words_594_627']=list(struct.unpack('<34H',bytes(t.read_memory_block8(p+2*594,68))))
                    f.write(json.dumps(s,ensure_ascii=False)+'\n');f.flush();out.put(('sample',s));last=nt
                stop.wait(.001)
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


class DetailedAI:
    def __init__(self,b):
        self.b=b;ctxmp=mp.get_context('spawn');self.values=ctxmp.Array('i',[-1]*8)
        self.stop=ctxmp.Event();self.out=ctxmp.Queue()
        self.trace=DAY/('AI_consumed_inputs_'+time.strftime('%H%M%S')+'.jsonl')
        self.proc=ctxmp.Process(target=ai_worker,args=(BOARDS[2],b.sy,self.values,self.stop,self.out,str(self.trace)),daemon=True)
        self.proc.start();kind,value=self.out.get(timeout=25);assert kind=='ready',(kind,value)
    def apply(self,ch=None,raw=None):
        with self.values.get_lock():
            self.values[:]=[-1]*8
            if ch is not None:self.values[ch+3]=raw
        return time.monotonic()
    def sample(self,after=0):
        end=time.monotonic()+8
        while time.monotonic()<end:
            try:kind,s=self.out.get(timeout=1)
            except queue.Empty:
                assert self.proc.is_alive(),'AI acquisition exited';continue
            if kind=='error':raise RuntimeError(s)
            if s['t']>=after and time.monotonic()-s['t']<1:return s
        raise TimeoutError('Fresh detailed AI capture')
    def close(self):
        self.apply();self.stop.set();self.proc.join(10)
        if self.proc.is_alive():self.proc.terminate();self.proc.join(3)
        self.out.close();assert self.proc.exitcode==0,'AI worker forced exit'


def ai_diagnostics():
    from continuous_followups_v1055_20261109 import cold_config
    b=Bench('AI_consumed_input_diagnostics');inp=None
    e=b.log['targeted_rerun']=dict(kind='AI_diagnostics',cases=[],
        scope='ADC acquisition/filter simulation; AD_Val consumed by firmware, AI, SensorStatus and fault counts captured. Physical open/short and terminal acceptance separate')
    try:
        cold_config(b,2);b.config({330:2,328:30,132:30,135:30});b.start();inp=DetailedAI(b)
        e['continuous_trace']=str(inp.trace.relative_to(R))
        for ch,alarm,flow in ((0,627,False),(1,619,False),(2,616,False),(3,617,False),(3,617,True),(4,620,False)):
            b.config({335:2,377:1 if ch in (1,2,4) else 0,1229+12*ch:1})
            if ch==3:b.config({329:3,133:0 if flow else 1,339:60,340:60,341:30,342:90,343:720,344:100,345:100})
            for raw in (4095,0):
                row=dict(channel=ch,raw=raw,alarm_address=alarm,flow_basis=flow,samples=[],started=now());e['cases'].append(row)
                try:
                    b.reset_faults();issued=inp.apply(ch,raw);end=time.monotonic()+22
                    continuous=None;fault_first=None
                    while time.monotonic()<end:
                        s=inp.sample(issued);s['alarm']=b.rd(alarm)[0];row['samples'].append(s)
                        consumed=s['AD_Val'][ch+3]
                        threshold=500 if b.rd(1230+12*ch)==[1] else 100
                        invalid=consumed<=threshold or consumed>=3800
                        if invalid:
                            if continuous is None:continuous=s['t']
                        else:continuous=None
                        if continuous is not None and s['SensorStatus'][ch] and s['alarm']:
                            if fault_first is None:fault_first=s['t']
                            if s['t']-fault_first>=4 and s['t']-continuous>=5:
                                row.update(diagnostic_seen=True,continuous_invalid_s=s['t']-continuous);break
                        else:fault_first=None
                    row['diagnostic_seen']=row.get('diagnostic_seen',False)
                    row['consumed_range']=[min(s['AD_Val'][ch+3] for s in row['samples']),max(s['AD_Val'][ch+3] for s in row['samples'])]
                    snap=b.snapshot('AI diagnostic final');row['software_snapshot']=snap
                    row['ventilation_outputs_safe']=(snap['state'][9]==2 and not any(snap['ao'][i] for i in (0,1,2,8,9)) and all(v not in (2,3,4) for q in snap['outdoor_status'] for v in q)
                        and all(not any(s['DA'][i] for i in (0,1,2,8,9)) for s in row['samples']))
                    row['passed']=row['diagnostic_seen'] and row['ventilation_outputs_safe']
                    if not row['diagnostic_seen']:row['limitation']='No continuous consumed invalid input and diagnostic established; not a firmware pass/fail verdict'
                except Exception:row.update(passed=False,error=traceback.format_exc())
                finally:
                    issued=inp.apply();end=time.monotonic()+25
                    while time.monotonic()<end:
                        s=inp.sample(issued);event('AI_recovery_sample',sample=s)
                        if not s['SensorStatus'][ch]:break
                    else:raise RuntimeError('AI raw source recovery not verified')
                    b.reset_faults();end=time.monotonic()+25
                    while time.monotonic()<end:
                        s=inp.sample()
                        if b.rd(alarm)==[0]:row['recovery_verified']=True;break
                    else:raise RuntimeError('AI alarm recovery not verified')
                    row['finished']=now();b.save();print('AI RERUN',ch,raw,row.get('passed'),row.get('consumed_range'),flush=True)
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save()
