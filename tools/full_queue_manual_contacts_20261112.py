"""Manual protection with stable normal330 polarity inputs, read-only probes.

The broadcast setting affects both units. Check each healthy partner compressor,
not an allegedly untouched peer unit. Never race the broadcast with SWD writes.
"""
from full_queue_context_20261112 import *
from bench_remaining_outdoor_20261111 import HEAT
import struct

def run():
    b = current_bench_class()('manual_contacts_stable_global_inputs')
    e = b.log['manual_contact_protection'] = dict(cases=[], scope=
        'Normal330 manual commands and GLOBAL input-polarity settings; both outdoor units receive the input; each healthy compressor checked independently; software feedback, not physical switches')
    b.attach_extra()
    targets = [(b.ot, b.outsy), (b.extra[0][1].target, b.extra[0][2])]

    def sample(ch, alarm):
        rows = []
        for t, sy in targets:
            p = sy['Parameter'][0]
            rows.append(dict(raw=t.read8(sy[f'X_{ch:02d}'][0]),
                polarity=t.read16(p+2*(ch+2)), alarm=t.read16(p+2*alarm),
                layer=t.read16(p+3002), output=list(t.read_memory_block8(*sy['output'])),
                run_seconds=list(struct.unpack('<5I', bytes(t.read_memory_block8(*sy['CompRunTime'])))),
                low_enabled=list(struct.unpack('<5I', bytes(t.read_memory_block8(*sy['EnableCheckLow']))))))
        return dict(at=now(), t=time.monotonic(), boards=rows,
            mirrors=[b.rd(2022+128*u+alarm-600)[0] for u in range(2)])

    def observe(row, label, ch, alarm, predicate, seconds):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            s=sample(ch, alarm);row.setdefault(label, []).append(s)
            if predicate(s):b.save();return s
            time.sleep(.2)
        b.save();raise TimeoutError(label)

    try:
        b.setup(1);b.config(HEAT);b.temperature(0,220);b.reset_faults();b.start()
        b.wait('manual protection all four healthy', lambda s:all(v==3 for q in s['outdoor_status'] for v in q),360)
        b.config({1301:1, **{a:1 for a in range(1302,1308)},
            **{a:1 for a in range(1310,1316)},1300:1})
        for ch,alarm,comp,latched in ((0,606,0,True),(1,600,0,False),(6,626,0,True),(4,621,None,True)):
            row=dict(id='O-PROTECT-018',ch=ch,alarm=alarm,started=now())
            e['cases'].append(row);old=b.rd(ch+2)[0];assert old in (0,1)
            changed=False
            expected=[0,0] if comp is None else [0,1]
            try:
                observe(row,'before',ch,alarm,lambda s:all(x['output'][:2]==[1,1] and not x['raw'] and not x['alarm'] for x in s['boards']),360)
                if ch==1:
                    delay=b.rd(27)[0]
                    observe(row,'lp_eligible',ch,alarm,lambda s:all(x['run_seconds'][0]>delay and x['low_enabled'][0] for x in s['boards']),max(360,delay+180))
                b.config({ch+2:1-old});changed=True
                observe(row,'assertion',ch,alarm,lambda s:all(x['raw']==x['alarm']==1 and x['output'][:2]==expected for x in s['boards']),90)
                if latched:b.reset_faults()
                end=time.monotonic()+20
                while time.monotonic()<end:
                    row.setdefault('hold',[]).append(sample(ch,alarm));time.sleep(.2)
                row['protected_continuously']=all(x['raw']==x['alarm']==1 and x['output'][:2]==expected for s in row['hold'] for x in s['boards'])
                row['both_mirrors_seen']=all(any(s['mirrors'][u]==1 for s in row['hold']) for u in range(2))
                b.config({ch+2:old});changed=False
                if latched:
                    released=observe(row,'released_before_reset',ch,alarm,lambda s:all(not x['raw'] for x in s['boards']),12)
                    row['latched_until_reset']=all(x['alarm']==1 for x in released['boards'])
                    b.reset_faults()
                else:row['automatic_clear_required']=True
                observe(row,'cleared',ch,alarm,lambda s:all(not x['raw'] and not x['alarm'] and not x['layer'] for x in s['boards']) and not any(s['mirrors']),90)
                row['passed']=row['protected_continuously'] and row['both_mirrors_seen'] and (not latched or row['latched_until_reset'])
            except Exception as exc:
                row.update(passed=False,error=repr(exc))
            finally:
                if changed:b.config({ch+2:old})
                b.reset_faults()
                observe(row,'recovery_verified',ch,alarm,lambda s:all(not x['raw'] and not x['alarm'] and not x['layer'] for x in s['boards']),90)
                row['finished']=now();b.save()
                print('MANUAL GLOBAL INPUT',ch,row.get('passed'),flush=True)
    finally:
        try:b.config({1300:0,**{a:0 for a in range(1302,1318)}});b.wr(398,0)
        finally:
            b.finish();e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':run()
