"""Current-board NTC protection and automatic alarm recovery; input-only worker."""
from joint_priority_20261110 import *
import multiprocessing as mp
import struct,queue


def worker(board,sy,values,stop,out):
    ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open();t=ss.target;p=sy['Parameter'][0];out.put(('ready',True));began=time.monotonic();previous=began;longest=0;next_sample=0
        while not stop.is_set():
            assert time.monotonic()-began<2400,'input fixture duration bound'
            with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
            for ch,v in active.items():
                t.write16(sy['ADbuffer'][0]+2*ch,v)
                t.write_memory_block8(sy['NTC_Val_Filter'][0]+40*ch,list(struct.pack('<20H',*([v]*20))))
                t.write16(sy['NTC_AD'][0]+2*ch,v)
            t.flush();nt=time.monotonic();longest=max(longest,nt-previous);previous=nt
            if nt>=next_sample:
                indexes=(1,30,107,1420,1421,1422,1425,1426,1501,1400,1403,1406)
                r=dict(at=now(),t=nt,max_input_gap_s=longest,params={str(a):t.read16(p+2*a) for a in indexes},
                    alarms=[t.read16(p+2*a) for a in range(600,628)],output=list(t.read_memory_block8(sy['output'][0],8)),
                    sensor_status=list(t.read_memory_block8(sy['SensorStatus'][0],sy['SensorStatus'][1])))
                for k in ('PSC316DefrostState','UnitLevelFault','SysLevelFault','CompLevelFault','OutdoorHeatTwoFan','OutdoorFanStage','OutdoorHeatFanHighCount','OutdoorHeatFanLowCount'):
                    if k in sy:
                        addr,n=sy[k];raw=bytes(t.read_memory_block8(addr,n));r[k]=list(struct.unpack('<I',raw)) if n==4 and k.endswith('Count') else list(raw)
                out.put(('sample',r));next_sample=nt+.2;longest=0
            stop.wait(.002)
        out.put(('stopped',dict(at=now(),duration_s=time.monotonic()-began)))
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()


def run():
    b=TodayBench('outdoor_NTC_protection_recovery');proc=None;stop=None;values=None
    e=dict(started=now(),status='running',cases=[],input_events=[],samples=[],scope='Raw NTC ADC/filter input simulation; normal 330 demand, real316 diagnostic/output and330 mirrors; no fault/timer/output forcing, no physical terminals')
    b.log['continuation_case']=e;b.save()
    def set_inputs(channels):
        with values.get_lock():
            for i in range(8):values[i]=0 if i in channels else -1
        e['input_events'].append(dict(at=now(),t=time.monotonic(),fault_adc_zero_channels=channels));b.save()
    def until(label,pred,timeout,row):
        began=time.monotonic();last_save=began
        while True:
            try:kind,s=out.get(timeout=3)
            except queue.Empty:assert proc.is_alive(),'input worker exited';continue
            if kind=='error':raise RuntimeError(s)
            if kind!='sample':continue
            e['samples'].append(s)
            # Only fresh samples can satisfy a condition after a stimulus.
            if s['t']<began:continue
            if pred(s):row[label]=s;b.save();print('OUTDOOR NTC',row['id'],label,'alarm',s['alarms'][12:19],'comp',s['output'][:2],flush=True);return s
            assert time.monotonic()-began<timeout,(label,s)
            if time.monotonic()-last_save>15:print('NTC WAIT',label,round(time.monotonic()-began,1),flush=True);last_save=time.monotonic();b.save()
    try:
        b.setup(1);b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        b.temperature(0,220);b.reset_faults();b.start()
        b.wait('NTC protection precondition four actual heating',lambda s:all(v==3 for p in s['outdoor_status'] for v in p),180)
        e['configuration']={str(a):b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (30,107,165,166,167,168,169)}
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue();proc=ctx.Process(target=worker,args=(BOARDS[0],b.outsy,values,stop,out),daemon=True);proc.start()
        kind,s=out.get(timeout=30);assert kind=='ready',(kind,s)
        cases=[('O-PROTECT-003',3,615,0),('O-PROTECT-004',5,617,0),('O-PROTECT-005',1,613,0),('O-PROTECT-008',4,616,1),('O-PROTECT-009',6,618,1),('O-PROTECT-010',2,614,1),('O-PROTECT-016',0,612,None)]
        for cid,ch,alarm,system in cases:
            r=dict(id=cid,channel=ch,alarm_parameter=alarm,system=system,status='running');e['cases'].append(r)
            until('healthy_both_running',lambda s:s['output'][:2]==[1,1] and not any(s['alarms']),200,r)
            set_inputs([ch]);index=alarm-600
            until('fault_and_protection',lambda s:s['alarms'][index]==1 and (s['output'][:2]==[0,0] if system is None else s['output'][system]==0 and s['output'][1-system]==1),35,r)
            mirror=b.rd(2022+index)[0];r['330_fault_mirror']=mirror;r['330_layer']=b.rd(2598)[0];r['other_outdoor_status']=b.rd(1625,2)
            # Keep the source present long enough to distinguish a transient.
            edge=r['fault_and_protection']['t']
            until('fault_hold',lambda s:s['t']>=edge+2 and s['alarms'][index]==1,6,r)
            began=time.monotonic();r['mirror_assert_samples']=[]
            while True:
                v=b.rd(2022+index)[0];r['mirror_assert_samples'].append(dict(at=now(),value=v))
                if v==1 or time.monotonic()-began>=45:break
                time.sleep(.4)
            r['330_fault_mirror']=v
            set_inputs([])
            until('alarm_auto_cleared_without_reset',lambda s:s['alarms'][index]==0 and s['params']['1501']&31==0,25,r)
            began=time.monotonic();r['mirror_clear_samples']=[]
            while True:
                v=b.rd(2022+index)[0];r['mirror_clear_samples'].append(dict(at=now(),value=v))
                if v==0 or time.monotonic()-began>=45:break
                time.sleep(.4)
            r['recovered_330_mirror']=v
            r['status']='软件子范围通过' if r['330_fault_mirror']==1 and v==0 else '保护动作已见；330镜像待核'
            b.save()
        e['status']='completed_see_per_case_scope';b.save()
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc:
                if values is not None:
                    with values.get_lock():
                        for i in range(8):values[i]=-1
                time.sleep(1);stop.set();proc.join(10);assert not proc.is_alive();e['worker_exitcode']=proc.exitcode
            b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            b.outss.open();b.ot=b.outss.target;time.sleep(2);b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
