"""Additional ordinary-demand/ADC-input scopes; firmware and state are read-only."""
from joint_v1058_context_20261111 import *
import multiprocessing as mp
import struct
import math
import queue
from continuous_special_stages_v1055_20261109 import paused

PAIRS=((0,0),(0,1),(1,2),(1,3),(2,2),(2,4))
HEAT={128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
      315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,
      347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,
      365:1,372:350,10:500,12:500}


def acquisition(board,sy,values,stop,stream,adc_values=None):
    stream.cancel_join_thread()
    ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;p=sy['Parameter'][0]
        stream.put(('ready',True));began=time.monotonic();next_read=0;previous=began;gap=0
        while not stop.is_set():
            assert time.monotonic()-began<7100,'fixture duration limit'
            with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
            for ch,v in active.items():
                t.write16(sy['ADbuffer'][0]+2*ch,v)
                t.write_memory_block8(sy['NTC_Val_Filter'][0]+40*ch,list(struct.pack('<20H',*([v]*20))))
                t.write16(sy['NTC_AD'][0]+2*ch,v)
            if adc_values is not None:
                with adc_values.get_lock():adc={i:v for i,v in enumerate(adc_values[:]) if v>=0}
                for ch,v in adc.items():
                    assert 0<=ch<4 and 0<=v<=4095
                    t.write16(sy['ADC_Val'][0]+2*ch,v)
                    t.write_memory_block8(sy['ADC_Val_Filter'][0]+20*ch,list(struct.pack('<10H',*([v]*10))))
            t.flush();nt=time.monotonic();gap=max(gap,nt-previous);previous=nt
            if nt>=next_read:
                words=list(struct.unpack('<103H',bytes(t.read_memory_block8(p+2800,206))))
                faults=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+1200,56))))
                s=dict(at=now(),t=nt,input_gap_s=gap,params={str(1400+i):v for i,v in enumerate(words)},
                    alarms=faults,output=list(t.read_memory_block8(*sy['output'])))
                for name in ('CompRunTime','DefGapCount','PSC316DefrostState','PSC316DefrostRunTime',
                             'OutdoorFanTotalRun','OutdoorVfdSpeed','OutdoorFanStage','OutdoorHeatTwoFan',
                             'OutdoorFanRunSeconds','OutdoorFanStopSeconds','OutdoorFanChangeSeconds','OutdoorPrestartOwnsFans',
                             'OutdoorTypeIILowFanOff','OutdoorTypeIILowCount','OutdoorTypeIIRecoverCount',
                             'OutdoorTypeIILowOffCount','OutdoorTypeIILowRecoverCount',
                             'SensorStatus','EnableCheckLow','NormalEnvLowCount','TimedEnvLowCount',
                             'TimerDefrostMode','FinLowCount'):
                    if name in sy:
                        address,n=sy[name];raw=bytes(t.read_memory_block8(address,n))
                        if name=='OutdoorVfdSpeed':
                            assert n==4,('current AXF signed int width',name,n)
                            value=struct.unpack('<i',raw)[0]
                        elif n%4==0 and name!='SensorStatus':value=list(struct.unpack('<'+'I'*(n//4),raw))
                        else:value=list(raw)
                        s[name]=value
                stream.put(('sample',s));next_read=nt+.3;gap=0
            stop.wait(.003)
    except BaseException:stream.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


class Inputs:
    def __init__(self,b,e,board=None):
        self.b=b;self.e=e;self.board=board or BOARDS[0]
        self.table=struct.unpack('<201f',bytes(b.ot.read_memory_block8(b.outsy['NTCtable'][0],804)))
        self.cal=[signed16(b.ot.read16(b.outsy['Parameter'][0]+2*(493-i))) for i in range(8)]
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');self.values=ctx.Array('i',[-1]*8);self.adc_values=ctx.Array('i',[-1]*4)
        self.stop=ctx.Event();self.out=ctx.Queue()
        self.proc=ctx.Process(target=acquisition,args=(self.board,b.outsy,self.values,self.stop,self.out,self.adc_values),daemon=True)
        self.proc.start();kind,data=self.out.get(timeout=25);assert kind=='ready',(kind,data)
    def temperatures(self,changes):
        raw={}
        for ch,temp in changes.items():
            val=temp-self.cal[ch];i=math.floor(val/10)+50;f=val/10-(i-50)
            resistance=self.table[i]+f*(self.table[i+1]-self.table[i])
            raw[ch]=round(2.048*resistance/(5.1+resistance)/.0000625)
        at=time.monotonic()
        with self.values.get_lock():
            for ch,v in raw.items():self.values[ch]=v
        self.e.setdefault('input_events',[]).append(dict(at=now(),t=at,temperatures10=changes,raw=raw));self.b.save()
        return at
    def sample(self,after=0):
        if not getattr(self.b,'_cleaning_up',False):getattr(self.b,'input_pause_check',paused)()
        end=time.monotonic()+8
        while time.monotonic()<end:
            try:kind,data=self.out.get(timeout=1)
            except queue.Empty:
                assert self.proc.is_alive(),'input worker stopped';continue
            if kind=='error':raise RuntimeError(data)
            if kind=='sample' and data['t']>=after and time.monotonic()-data['t']<2:return data
        raise TimeoutError('fresh input sample')
    def adc(self,changes):
        with self.adc_values.get_lock():
            for ch,v in changes.items():
                assert 0<=ch<4 and -1<=v<=4095;self.adc_values[ch]=v
        self.e.setdefault('adc_input_events',[]).append(dict(at=now(),t=time.monotonic(),raw=changes));self.b.save()
        return time.monotonic()
    def point(self,cid,label,temp,seconds,expected_count=None,expect_lock=None,allow_fault=False):
        issued=self.temperatures({0:temp});row=dict(id=cid,label=label,temp10=temp,seconds=seconds,samples=[])
        self.e.setdefault('cases',[]).append(row);exact=None;end=time.monotonic()+seconds+35
        while time.monotonic()<end:
            s=self.sample(issued);row['samples'].append(s)
            if not allow_fault:assert not any(s['alarms']),('unexpected fault during healthy-temperature test',s)
            if signed16(s['params']['1422'])==temp:
                if exact is None:exact=s['t']
                if s['t']-exact>=seconds:
                    row.update(final=s,observed_s=s['t']-exact)
                    if expected_count is not None:
                        typ=self.e['pair'][1];o=s['output']
                        count=int(bool(o[2] or (o[7] if typ==0 else 0)))+int(bool(o[3] or (o[7] if typ==3 else 0)))
                        row.update(expected_count=expected_count,actual_count=count,passed=count==expected_count)
                        if typ in (2,4):row['vfd_speed10']=s['OutdoorVfdSpeed']
                        if typ==0:row['passed'] &= bool(o[7])
                    elif expect_lock is not None:
                        row.update(expected_lock=expect_lock,passed=bool(s['params']['1501']&32)==expect_lock)
                    break
            else:exact=None
        else:raise TimeoutError(label)
        row['finished']=now();self.b.save();print('OUTDOOR POINT',cid,label,row.get('passed'),flush=True);return row
    def close(self):
        with self.values.get_lock():self.values[:]=[-1]*8
        with self.adc_values.get_lock():self.adc_values[:]=[-1]*4
        self.stop.set();self.proc.join(10)
        if self.proc.is_alive():self.proc.terminate();self.proc.join(3)
        self.e['worker_exitcode']=self.proc.exitcode;self.out.close()
        b=self.b
        b.outss=ConnectHelper.session_with_chosen_probe(unique_id=self.board[1],target_override=self.board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        b.outss.open();b.ot=b.outss.target
        assert self.proc.exitcode==0,'input fixture required forced termination'


def heat_and_dispatch(index):
    pair=PAIRS[index];b=current_bench_class()(f'remaining_heat_dispatch_{index}');inp=None
    e=b.log['remaining_functional']=dict(kind='heat_dispatch',pair=pair,cases=[],events=[],
        scope='Ordinary330 heating and room-temperature demand changes; raw316 NTC0 input; BENCH software outputs, terminals/production timing separate')
    cid=f'O-HEATFAN-{index+1:03d}';dispatch=f'O-DISPATCH-{3*index+3:03d}'
    try:
        b.setup(1);b.gateway(1830,pair[0]);b.gateway(1831,pair[1]);b.config(HEAT)
        b.config({1335:70,1336:50});b.temperature(0,220);b.reset_faults();b.start()
        b.wait('ordinary heat all four before remaining fan tests',lambda s:all(v==3 for q in s['outdoor_status'] for v in q),180)
        inp=Inputs(b,e)
        if pair[1] in (0,2):points=((69,1),(121,1))
        else:points=((69,2),(121,1),(100,1),(69,2))
        for temp,count in points:inp.point(cid,f'heat_{temp}',temp,36,count)
        if pair[1] in (2,4):
            for row in e['cases']:
                if row['actual_count'] and row['final']['output'][2]:row['passed'] &= row['vfd_speed10']==500
        b.config({127:0});b.temperature(0,280)
        event=dict(id=dispatch,label='ordinary_total_demand_unload',samples=[]);e['events'].append(event)
        end=time.monotonic()+190
        while time.monotonic()<end:
            s=inp.sample();s.update(target=b.rd(881)[0],other=b.rd(1625,2));event['samples'].append(s)
            if s['target']==0 and s['output'][:2]==[0,0] and s['other']==[0,0]:event['passed']=True;break
            time.sleep(.2)
        else:event.update(passed=False,error='ordinary unload precondition/feedback timeout')
        # Preserve the actual fan trailing-stop and restart edges in the same
        # ordinary-demand cycle. BENCH evidence does not close PRODUCTION timing.
        trailing=dict(id=f'O-FANTIME-{4*index+4:03d}',label='fan_trailing_stop_after_normal_unload',samples=[])
        e['events'].append(trailing);end=time.monotonic()+95
        while time.monotonic()<end:
            s=inp.sample();trailing['samples'].append(s)
            if not any(s['output'][i] for i in (0,1,2,3,7)):
                trailing.update(final=s,passed=True);break
        else:trailing.update(passed=False,error='normal unloaded fan stop did not finish')
        b.temperature(0,220);b.config({127:1})
        event=dict(id=dispatch,label='ordinary_total_demand_reload',samples=[]);e['events'].append(event)
        end=time.monotonic()+190
        while time.monotonic()<end:
            s=inp.sample();s.update(target=b.rd(881)[0],other=b.rd(1625,2));event['samples'].append(s)
            if s['target']==4 and s['output'][:2]==[1,1] and s['other']==[3,3]:event['passed']=True;break
            time.sleep(.2)
        else:event.update(passed=False,error='ordinary reload precondition/feedback timeout')
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def ambient(case):
    b=current_bench_class()(f'remaining_ambient_{case}');inp=None
    e=b.log['remaining_functional']=dict(kind='ambient',pair=[0,1],cases=[],scope='Raw ambient input, ordinary demand and real elapsed time; BENCH only')
    try:
        mode=0 if case in ('lws22','lws25','type2high') else 1
        b.setup(mode)
        if case=='type2high':b.gateway(1830,2);b.gateway(1831,4);e['pair']=[2,4]
        b.config(HEAT if mode==1 else {**HEAT,127:0,416:100,417:1,418:0,411:200})
        if case.startswith('lws'):b.gateway(1835,int(case[3:])*10)
        elif case in ('rws10','rws18'):b.gateway(1836,int(case[3:])*10)
        b.temperature(0,220 if mode else 290);b.reset_faults()
        inp=Inputs(b,e)
        start=150 if case.startswith('lws') else 200 if case=='type2high' else 80
        inp.temperatures({0:start});b.start()
        if case.startswith('lws'):
            base=int(case[3:])*10;cid='O-AMBIENT-002' if base==220 else 'O-AMBIENT-003'
            for label,temp,sec,lock in [('below_LWS',base-1,10,True),('equal_LWS',base,10,True),('above_LWS',base+1,12,False)]:
                inp.point(cid,label,temp,sec,expect_lock=lock)
            b.wait('LWS actual running precondition',lambda s:s['outdoor_status'][0]==[2,2],180)
            for label,temp,sec,lock in [('running_13_equal',130,12,False),('running_below13',129,306,True)]:
                inp.point(cid,label,temp,sec,expect_lock=lock)
        elif case=='type2high':
            cid='O-AMBIENT-012'
            inp.point(cid,'establish_positive_ambient',200,15,expect_lock=False)
            b.wait('type2 positive ambient cooling available',lambda s:s['outdoor_status'][0]==[2,2],180)
            for label,temp,sec,lock in [('43_short',430,25,False),('42_9_break',429,4,False),('43_full',430,66,True),('42_9_recover',429,12,False)]:
                inp.point(cid,label,temp,sec,expect_lock=lock)
        elif case in ('rws10','rws18'):
            base=int(case[3:])*10;cid='O-AMBIENT-007' if base==100 else 'O-AMBIENT-006'
            inp.point(cid,'below_RWS',base-1,12,expect_lock=False)
            b.wait('RWS actual running precondition',lambda s:s['outdoor_status'][0]==[3,3],180)
            for label,temp,sec,lock in [('equal_RWS_plus2',base+20,12,False),('above_RWS_plus2',base+21,306,True),('equal_RWS_recovery',base,12,True),('below_RWS_recovery',base-1,12,False)]:
                inp.point(cid,label,temp,sec,expect_lock=lock)
        else:
            # Heating has -10/-12 boundaries; -15/-14 belongs to cooling.
            inp.point('O-AMBIENT-008','above_minus10_start',-99,12,expect_lock=False)
            b.wait('lower heating actual running precondition',lambda s:s['outdoor_status'][0]==[3,3],180)
            for cid,label,temp,sec,lock in [('O-AMBIENT-008','minus12_running_equal',-120,12,False),('O-AMBIENT-008','below_minus12_running',-121,306,True),('O-AMBIENT-008','minus10_stopped_equal',-100,12,True),('O-AMBIENT-008','above_minus10_recover',-99,12,False),('O-AMBIENT-009','3_equal',30,12,None),('O-AMBIENT-009','above3',31,12,None),('O-AMBIENT-009','below3',29,12,None)]:
                inp.point(cid,label,temp,sec,expect_lock=lock)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def defrost_interrupt(kind):
    b=current_bench_class()(f'remaining_defrost_{kind}')
    cid={'disable':'O-DEFROST-018','fault':'O-DEFROST-019','mode':'O-DEFROST-022'}[kind]
    e=b.log['remaining_functional']=dict(kind='defrost_interrupt',cases=[],scope='Manual request establishes actual defrost8; ordinary disable/mode or contact-polarity input; BENCH software lifecycle')
    original=None
    try:
        e['before']=b.prepare()
        row=dict(id=cid,label=('single_overload_healthy_comp_continues' if kind=='fault' else kind),samples=[]);e['cases'].append(row)
        if kind=='disable':b.gateway(1832,1)
        elif kind=='mode':b.config({236:2})
        else:
            address=b.outsy['Parameter'][0]+16
            original=b.ot.read16(address);b.ot.write16(address,1-original);b.ot.flush()
        end=time.monotonic()+65
        while time.monotonic()<end:
            s=b.sample('defrost interruption '+kind);row['samples'].append(s)
            outputs=list(b.ot.read_memory_block8(*b.outsy['output']));s['direct_output']=outputs
            if kind=='fault':
                alarm=b.ot.read16(b.outsy['Parameter'][0]+2*626)
                s['overload_alarm626']=alarm
                match=outputs[:2]==[0,1] and s['phase']==[8,8] and alarm==1
            else:
                match=outputs[:2]==[0,0] and s['phase']==[0,0]
            if match:
                row.update(final=s,passed=True);break
            time.sleep(.2)
        else:row.update(passed=False,error=('single fault did not isolate one system while healthy system continued' if kind=='fault' else 'outputs or defrost lifecycle did not clear within observation'))
        row['finished']=now()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if original is not None:b.ot.write16(b.outsy['Parameter'][0]+16,original);b.ot.flush()
            b.reset_faults();b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('heat','ambient','defrost'));p.add_argument('case');a=p.parse_args()
    if a.action=='heat':heat_and_dispatch(int(a.case))
    elif a.action=='ambient':ambient(a.case)
    else:defrost_interrupt(a.case)
