"""Fixed plus two-speed low-ambient stop and independent restart conditions."""
from bench_remaining_outdoor_20261111 import *
from app import Psc330MonitorApp


def run():
    b=current_bench_class()('remaining_typeII_lowfan');inp=None
    e=b.log['remaining_functional']=dict(kind='typeII_low_ambient_fan',pair=[1,3],cases=[],
        scope='Raw ambient and normal330 pressure-AI scaling inputs; real30s conditions and software fan outputs; no physical pressure or terminals')
    original={a:b.rd(a)[0] for a in (2684,2685,2696,2697)};e['ai_original']=original
    table=struct.unpack('<'+'h'*(b.outsy['R410ATemp'][1]//2),bytes(b.ot.read_memory_block8(*b.outsy['R410ATemp'])))
    m=object.__new__(Psc330MonitorApp);m.values={}
    m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)

    def write(a,v):
        m.write_outdoor_gateway_register(1830,a,302+a-2680,v)

    def span(ch,low,high):
        base=2680+12*ch
        if low>=signed16(b.rd(base+5)[0]):write(base+5,max(low+1,high))
        write(base+4,low);write(base+5,high)

    def pt(pressure):
        j=min(870,(pressure+100)//5)
        return table[j]+(pressure%5)*(table[j+1]-table[j])//5

    def pressure(temp):
        values=[p for p in range(100,3400) if pt(p)==pt(p+1)==temp]
        assert values,('exact PT input span unavailable',temp)
        return values[len(values)//2]

    def set_condensing(temps):
        for ch,temp in enumerate(temps):
            value=pressure(temp);span(ch,value,value+1)

    def point(cid,label,ambient,temps,seconds,expected_low):
        row=dict(id=cid,label=label,ambient10=ambient,condensing10=temps,samples=[])
        e['cases'].append(row);b.save()
        set_condensing(temps);issued=inp.temperatures({0:ambient});exact=None;end=time.monotonic()+seconds+40
        while time.monotonic()<end:
            s=inp.sample(issued);s['condensing10']=[pt(s['params'][str(a)]) for a in (1443,1445)]
            row['samples'].append(s)
            assert not any(s['alarms']),('unexpected alarm during lowfan test',s)
            if s['condensing10']==temps and signed16(s['params']['1422'])==ambient:
                if exact is None:exact=s['t']
                if s['t']-exact>=seconds:
                    row.update(final=s,observed_s=s['t']-exact,finished=now(),
                        passed=bool(s['output'][3])==expected_low and not s['output'][2] and not s['output'][7] and s['output'][:2]==[1,1])
                    b.save();print('TYPEII LOWFAN',label,row['passed'],s['output'],flush=True);return row
            else:exact=None
        raise TimeoutError(label)

    try:
        b.setup(0);b.gateway(1830,1);b.gateway(1831,3)
        b.config({**HEAT,127:0,416:100,417:1,418:0,411:200,
                  1333:300,1334:150,1337:10,1338:10,1339:0})
        b.temperature(0,290);set_condensing([290,290]);b.reset_faults()
        inp=Inputs(b,e);inp.temperatures({0:200});b.start()
        b.wait('typeII lowfan actual cooling',lambda s:s['outdoor_status'][0]==[2,2],210)
        point('O-FANCURVE-008','8C_equal_does_not_stop',80,[290,290],35,True)
        point('O-FANCURVE-008','7_9C_all_condensing29_stop',79,[290,290],35,False)
        point('O-FANCURVE-009','10C_equal_does_not_restart',100,[290,290],35,False)
        point('O-FANCURVE-009','10_1C_restart_after30',101,[290,290],35,True)
        point('O-FANCURVE-010','reestablish_lowfan_off',79,[290,290],35,False)
        point('O-FANCURVE-010','system1_above42_restarts_lowfan',79,[421,290],35,True)
        point('O-FANCURVE-010','both29_stop_again',79,[290,290],35,False)
        point('O-FANCURVE-010','system2_above42_restarts_lowfan',79,[290,421],35,True)
        # Use one fixed normal pressure span plus acquisition endpoints for a
        # rapid OR handover. The overlap keeps OR true while neither individual
        # clause lasts30s, unlike slow sequential gateway span edits.
        lo,hi=pressure(290),pressure(421)
        for ch in range(2):span(ch,lo,hi)
        inp.adc({0:400,1:400})
        row=dict(id='O-FANCURVE-011',label='environment_then_overlap_then_condensing_OR_continuity',samples=[],segments=[])
        e['cases'].append(row)

        def or_segment(label,ambient,raw0,seconds):
            inp.adc({0:raw0,1:400});issued=inp.temperatures({0:ambient})
            part=dict(label=label,seconds=seconds,samples=[]);row['segments'].append(part)
            exact=None;end=time.monotonic()+seconds+15
            expected=[421 if raw0==2000 else 290,290]
            while time.monotonic()<end:
                s=inp.sample(issued);s['condensing10']=[pt(s['params'][str(a)]) for a in (1443,1445)]
                s['OR']=signed16(s['params']['1422'])>100 or max(s['condensing10'])>420
                part['samples'].append(s);row['samples'].append(s)
                assert not any(s['alarms']),('OR test source diagnostic',s)
                if signed16(s['params']['1422'])==ambient and s['condensing10']==expected:
                    if exact is None:exact=s['t']
                    if s['t']-exact>=seconds:part.update(final=s,exact_start_t=exact);return s
                else:exact=None
            raise TimeoutError(('OR exact input',label))

        initial=or_segment('both_false_reestablish_off',79,400,35)
        assert not initial['output'][3] and initial['output'][:2]==[1,1],('OR test initial fan off missing',initial)
        or_segment('environment_only',101,400,18)
        or_segment('overlap_both_true',101,2000,3)
        final=or_segment('condensing_only',79,2000,16)
        active=[s for part in row['segments'][1:] for s in part['samples']]
        first=next(i for i,s in enumerate(active) if s['OR'])
        row.update(final=final,finished=now(),or_false_samples=sum(not s['OR'] for s in active[first:]),
            passed=bool(final['output'][3]) and final['output'][:2]==[1,1] and all(s['OR'] for s in active[first:]))
        b.save();print('TYPEII OR CONTINUITY',row['passed'],flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            for ch in range(2):span(ch,signed16(original[2684+ch*12]),signed16(original[2685+ch*12]))
            p=b.outsy['Parameter'][0]
            e['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(p+2*(302+a-2680)) for a,v in original.items())
            assert e['ai_restore_verified'],'typeII AI span restoration did not verify'
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
