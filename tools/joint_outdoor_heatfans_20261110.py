"""Two fixed heating fans: real ambient hold and hysteresis, input-only worker."""
from joint_priority_20261110 import *
from joint_outdoor_ntc_protection_20261110 import worker
import multiprocessing as mp
import math,struct,queue


def run():
    b=TodayBench('O-HEATFAN-002_two_fixed_hysteresis');proc=None;stop=None;values=None
    e=dict(started=now(),id='O-HEATFAN-002',status='running',points=[],samples=[],scope='0/1 two-fixed heating fans; both compressors; NTC0 ADC/filter simulation, 7/12C boundaries and real30s hold. Rotation, single-compressor and other fan pairs separate')
    b.log['continuation_case']=e;b.save()
    def next_sample():
        while True:
            try:kind,s=out.get(timeout=3)
            except queue.Empty:assert proc.is_alive();continue
            if kind=='error':raise RuntimeError(s)
            if kind=='sample':e['samples'].append(s);return s
    try:
        b.setup(1);b.gateway(1830,0);b.gateway(1831,1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,365:1,372:350,10:500,12:500,1335:70,1336:50})
        b.temperature(0,220);b.reset_faults();b.start()
        b.wait('twofixed heat fans four actual heat',lambda s:all(v==3 for p in s['outdoor_status'] for v in p),180)
        table=struct.unpack('<201f',bytes(b.ot.read_memory_block8(b.outsy['NTCtable'][0],804)));cal=signed16(b.ot.read16(b.outsy['Parameter'][0]+493*2))
        e['destination_settings']={str(a):b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (165,166,174,175,179,180)}
        assert e['destination_settings']['174']==70 and e['destination_settings']['175']==50
        b.outss.close();b.outss=None;ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue();proc=ctx.Process(target=worker,args=(BOARDS[0],b.outsy,values,stop,out),daemon=True);proc.start();kind,_=out.get(timeout=30);assert kind=='ready'
        previous=None
        for temp,wanted in ((69,2),(70,2),(90,2),(120,2),(121,1),(100,1),(69,2)):
            value=temp-cal;i=math.floor(value/10)+50;f=value/10-(i-50);res=table[i]+f*(table[i+1]-table[i]);raw=round(2.048*res/(5.1+res)/.0000625)
            r=dict(temp10=temp,wanted_fans=wanted,raw_input=raw,samples=[]);e['points'].append(r);issued=time.monotonic()
            with values.get_lock():values[0]=raw
            r['requested_t']=issued;settled=None
            while True:
                s=next_sample()
                if s['t']<issued:continue
                r['samples'].append(s)
                assert not any(s['alarms']),s
                if signed16(s['params']['1422'])==temp:
                    if settled is None:settled=s['t'];r['first_exact_input_t']=settled
                    elapsed=s['t']-settled;fan_count=int(bool(s['output'][2]))+int(bool(s['output'][3]))
                    if previous is not None and wanted!=previous and elapsed<28.5:assert fan_count==previous,('changed before30s hold',r,s)
                    if elapsed>=33:
                        assert fan_count==wanted,('heating fan stage mismatch',temp,fan_count,wanted,s)
                        r.update(status='软件子范围通过',final=s,observed_exact_input_s=elapsed);break
                else:
                    assert settled is None,('exact simulated temperature not continuous',r,s)
                assert time.monotonic()-issued<45,('temperature hold timeout',r)
            previous=wanted;b.save();print('HEAT FAN',temp/10,'fans',wanted,'PASS',flush=True)
        e['status']='completed_boundaries_2compressor_subscope';b.save()
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc:
                with values.get_lock():values[0]=-1
                time.sleep(1);stop.set();proc.join(10);assert not proc.is_alive();e['worker_exitcode']=proc.exitcode
            b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            b.outss.open();b.ot=b.outss.target;time.sleep(2);b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
