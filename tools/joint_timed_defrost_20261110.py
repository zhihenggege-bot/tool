"""True 20-minute timed-defrost preconditions, raw NTC inputs, no timer forcing."""
from joint_priority_20261110 import *
import multiprocessing as mp
import struct,math,queue

def worker(board,sy,values,stop,out):
    ss=None
    try:
        ss=ConnectHelper.session_with_chosen_probe(blocking=False,unique_id=board[1],target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        assert ss,'Outdoor input probe unavailable';ss.open();t=ss.target;p=sy['Parameter'][0]
        table=struct.unpack('<201f',bytes(t.read_memory_block8(sy['NTCtable'][0],804)))
        out.put(('ready',dict(table=list(table),environment_calibration=signed16(t.read16(p+493*2)))));began=time.monotonic();previous=began;gap=0;nextdiag=0
        while not stop.is_set():
            assert time.monotonic()-began<1500,'fixture maximum duration'
            with values.get_lock():active={i:v for i,v in enumerate(values[:]) if v>=0}
            for ch,v in active.items():
                t.write16(sy['ADbuffer'][0]+2*ch,v)
                t.write_memory_block8(sy['NTC_Val_Filter'][0]+40*ch,list(struct.pack('<20H',*([v]*20))))
                t.write16(sy['NTC_AD'][0]+2*ch,v)
            t.flush();nt=time.monotonic();gap=max(gap,nt-previous);previous=nt
            if nt>=nextdiag:
                row=dict(at=now(),t=nt,max_transfer_gap_s=gap,params={str(a):t.read16(p+2*a) for a in (1,165,166,167,168,169,171,182,183,185,612,617,1400,1403,1406,1409,1420,1421,1422,1425,1426,1501)},output=list(t.read_memory_block8(sy['output'][0],8)))
                for k in ('TimedEnvLowCount','NormalEnvLowCount','TimerDefrostMode','DefGapCount','CompRunTime','PSC316DefrostState','PSC316DefrostStateTime','SensorStatus','AmbientLockout','LowRecoverCount','HighRecoverCount','PreviousWorkMode','PreviousOutdoorUnitType'):
                    if k in sy:
                        addr,n=sy[k];raw=bytes(t.read_memory_block8(addr,n))
                        row[k]=list(raw) if k in ('PSC316DefrostState','SensorStatus','AmbientLockout','PreviousWorkMode','PreviousOutdoorUnitType') else list(struct.unpack('<'+'I'*(n//4),raw))
                out.put(('diagnostic',row));nextdiag=nt+1;gap=0
            stop.wait(.002)
        out.put(('stopped',dict(at=now(),elapsed_s=time.monotonic()-began)))
    except BaseException:out.put(('error',traceback.format_exc()))
    finally:
        if ss:ss.close()

def run():
    b=TodayBench('O-DEFROST-015_timed15_env12')
    e=dict(started=now(),status='running',ids=['O-DEFROST-015'],scope='20-minute actual gap/5-minute actual run; raw NTC0 and NTC5 input simulation, no final fault/timer/output writes',diagnostics=[],snapshots=[])
    b.log['priority_case']=e;b.save();proc=None;stop=None;out=None
    try:
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,365:1,372:350,10:500,12:500,1389:150,1390:20,1392:5})
        b.temperature(0,220);b.reset_faults()
        sy=b.outsy;b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue()
        proc=ctx.Process(target=worker,args=(BOARDS[0],sy,values,stop,out),daemon=True);proc.start()
        kind,ready=out.get(timeout=30);assert kind=='ready',(kind,ready)
        table=ready['table'];e['environment_calibration']=ready['environment_calibration']
        def rawtemp(temp10):
            i=math.floor(temp10/10)+50;f=temp10/10-(i-50);r=table[i]+f*(table[i+1]-table[i]);return round((2.048*r/(5.1+r))/.0000625)
        def inputs(temp10,fault=True):
            with values.get_lock():values[0]=rawtemp(temp10-ready['environment_calibration']);values[5]=0 if fault else -1
            e.setdefault('input_events',[]).append(dict(at=now(),environment_temp10=temp10,raw_ntc0=values[0],raw_ntc5=values[5]));b.save()
        inputs(120,False);b.start();began=time.monotonic();lastprint=began;lastsave=began;lastsnapshot=began;qualified=None;cooler=None;fault_injected=False
        while True:
            assert time.monotonic()-began<1470,'timed defrost observation timeout'
            try:kind,row=out.get(timeout=3)
            except queue.Empty:
                assert proc.is_alive(),'input worker ended';continue
            if kind=='error':raise RuntimeError(row)
            if kind!='diagnostic':continue
            e['diagnostics'].append(row);p=row['params']
            if not fault_injected:
                if row['output'][0] and row['output'][1] and p['617']==0:
                    e['healthy_heat_before_fault']=row;inputs(120,True);fault_injected=True
                else:assert time.monotonic()-began<200,('healthy heat precondition missing',row)
            if time.monotonic()-lastsnapshot>=10:
                e['snapshots'].append(b.snapshot('timed defrost preconditions and arbitration'));lastsnapshot=time.monotonic()
            if time.monotonic()-lastprint>=25:
                print('TIMED15',round(time.monotonic()-began,1),'env',signed16(p['1422']),'run',row['CompRunTime'][:2],'gap',row['DefGapCount'][:2],'timedlow',row['TimedEnvLowCount'],'mode',row['TimerDefrostMode'][:2],'phase',p['1420'],p['1421'],flush=True);lastprint=time.monotonic()
            if time.monotonic()-lastsave>=10:b.save();lastsave=time.monotonic()
            if qualified is None and signed16(p['1422'])==120 and p['617']==1 and p['612']==0 and row['output'][1] and row['CompRunTime'][1]>=300 and row['DefGapCount'][1]>=1200 and row['TimedEnvLowCount'][0]>=60:
                qualified=time.monotonic();e['qualified_at12']=row;e['before_threshold_observation_s']=20;b.save()
            if qualified is not None and cooler is None and time.monotonic()-qualified>=20:
                e['after_qualified_hold12']=row
                # Circuit 1 is deliberately unavailable (phase 6). Judge the
                # healthy circuit's request separately from that fault state.
                e['no_request_at12']=p['1421']==0 and p['1420'] in (0,6)
                inputs(90);cooler=time.monotonic();e['cooler_control_started']=now()
            if cooler is not None:
                if p['1420'] in (1,5,7,8) or p['1421'] in (1,5,7,8):
                    e['cooler_request']=row;e['status']='不符合：15℃设定下12℃满足全部前置仍无请求，降至9℃后发出化霜请求' if e.get('no_request_at12') else '见原始轨迹，12℃并非无请求';b.save();break
                assert time.monotonic()-cooler<80,('9C control no defrost request',row)
        print('TIMED CASE',e['status'],flush=True)
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc:
                stop.set();proc.join(10)
                assert not proc.is_alive(),'outdoor input worker did not stop'
                e['input_worker_exitcode']=proc.exitcode
            b.outss=ConnectHelper.session_with_chosen_probe(blocking=False,unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            assert b.outss,'outdoor restore probe unavailable';b.outss.open();b.ot=b.outss.target
            time.sleep(2);b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':run()
