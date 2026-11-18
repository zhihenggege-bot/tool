"""Ventilation with individual indoor raw NTC faults on the current BENCH images."""
from joint_v1058_context_20261111 import *
from nonvent_ntc_input_boundaries_20261109 import RawNtcInput
from continuous_followups_v1055_20261109 import cold_config


def run():
    b=current_bench_class()('B07_vent_ntc'); fixture=None
    e=b.log['vent_ntc']=dict(cases=[],scope='Ventilation, indoor NTC0–7 raw ADC/filter open/short proxies and normal reset; not actual wiring faults')
    alarms=(618,604,600,599,612,613,614,615)
    try:
        assert b.rd(398)==b.rd(709)==[0] and not any(b.rd(2598,2))
        cold_config(b,2);b.config({330:2,328:30,132:30,135:30});b.start()
        fixture=RawNtcInput(b)

        def sample(ch,label):
            s=b.snapshot(label); s.update(at=now(),raw=b.rd(1374+ch)[0],alarm=b.rd(alarms[ch])[0]);return s

        def safe(s):
            return (s['state'][9]==2 and all(s['do'][i]==1 for i in (3,6,8)) and
                    not any(s['ao'][i] for i in (0,1,2,8,9)) and not any(x in (2,3,4) for pair in s['outdoor_status'] for x in pair))

        def until(ch,row,label,sec,pred):
            end=time.monotonic()+sec; samples=row.setdefault(label,[])
            while time.monotonic()<end:
                s=sample(ch,label);samples.append(s)
                if pred(s):return s
                if fixture.error:raise RuntimeError(fixture.error)
                time.sleep(.2)
            raise TimeoutError(label)

        for ch,alarm in enumerate(alarms):
            for bad,raw in enumerate((32767,0)):
                cid=f'T03-{49+6*ch+bad:03d}'
                row=dict(id=cid,ch=ch,raw=raw,alarm=alarm,started=now());e['cases'].append(row);b.save()
                try:
                    until(ch,row,'healthy',15,lambda s:safe(s) and s['alarm']==0 and 0<s['raw']<32767)
                    with fixture.lock:fixture.values[ch]=raw
                    s=until(ch,row,'assertion',20,lambda s:s['alarm']==1)
                    row['fans_during_fault']=safe(s)
                    end=time.monotonic()+4
                    while time.monotonic()<end:
                        s=sample(ch,'ventilation while raw fault held');row.setdefault('hold',[]).append(s)
                        row['fans_during_fault'] &= safe(s) and s['alarm']==1
                    row['status']='软件子范围通过' if row['fans_during_fault'] else '实测有待核对'
                except Exception as exc:row.update(status='实测有待核对',error=repr(exc))
                finally:
                    with fixture.lock:fixture.values.pop(ch,None)
                    try:
                        until(ch,row,'raw_recovered',15,lambda s:0<s['raw']<32767)
                        b.reset_faults()
                        until(ch,row,'recovered',15,lambda s:safe(s) and s['alarm']==0)
                        row['recovery_verified']=True
                    except Exception as exc:row.update(recovery_verified=False,recovery_error=repr(exc))
                    row['finished']=now();b.save();print('VENT NTC',cid,row['status'],row['recovery_verified'],flush=True)
                if not row['recovery_verified']:return
        e['status']='executed'
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if fixture is not None:fixture.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
