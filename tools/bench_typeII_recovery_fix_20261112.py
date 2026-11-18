"""Live typeII recovery regression; normal gateway settings and raw acquisition.

Uses the actual ADProcess input scale (4-20mA raw745/3724 ->400/2000),
verified offline from the bound AXF. Never writes final AI/fault/output state.
"""
import joint_v1060_context_20261112 as ctx
from joint_v1060_context_20261112 import *
from bench_remaining_outdoor_20261111 import HEAT, Inputs
from app import Psc330MonitorApp
import struct
import continuous_special_stages_v1055_20261109 as pause_module
pause_module.PAUSE=R/'.codex-tmp/four_followups_pause.request'


def run():
    b=current_bench_class()('typeII_recovery_and_independent_OR');inp=None
    e=b.log['typeII_recovery']=dict(cases=[],scope='Raw NTC/ADC input simulation; normal330 AI settings; software outputs only, BENCH')
    addresses=[2680+12*ch+off for ch in range(2) for off in (1,4,5)]
    original={a:b.rd(a)[0] for a in addresses};e['original_ai']=original
    table=struct.unpack('<'+'h'*(b.outsy['R410ATemp'][1]//2),bytes(b.ot.read_memory_block8(*b.outsy['R410ATemp'])))
    m=object.__new__(Psc330MonitorApp);m.values={}
    m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)
    def write(a,v):m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
    def span(ch,low,high):
        base=2680+12*ch
        if low>=signed16(b.rd(base+5)[0]):write(base+5,max(low+1,high))
        write(base+4,low);write(base+5,high)
    def pt(p):
        j=min(870,(p+100)//5)
        return table[j]+(p%5)*(table[j+1]-table[j])//5
    def pressure(temp):
        values=[p for p in range(100,3400) if pt(p)==pt(p+1)==temp]
        assert values,('no exact input pressure',temp)
        return values[len(values)//2]
    def cond(temps):
        for ch,temp in enumerate(temps):
            p=pressure(temp);span(ch,p,p+1)
    def observe(row,label,ambient,temps,seconds,raw=None):
        if raw is None:cond(temps)
        else:inp.adc({0:raw,1:745})
        issued=inp.temperatures({0:ambient})
        part=dict(label=label,ambient10=ambient,condensing10=temps,samples=[])
        row.setdefault('segments',[]).append(part);exact=None;end=time.monotonic()+seconds+35
        while time.monotonic()<end:
            s=inp.sample(issued);s['condensing10']=[pt(s['params'][str(a)]) for a in (1443,1445)]
            part['samples'].append(s)
            assert not any(s['alarms']),('unexpected source alarm',label,s)
            assert s['output'][:2]==[1,1],('compressor continuity lost',label,s)
            if signed16(s['params']['1422'])==ambient and s['condensing10']==temps:
                if exact is None:exact=s['t']
                if s['t']-exact>=seconds:
                    part.update(final=s,exact_start_t=exact,observed_s=s['t']-exact);b.save();return s
            else:exact=None
        raise TimeoutError(('exact input',label))
    try:
        b.setup(0);b.gateway(1830,1);b.gateway(1831,3)
        b.config({**HEAT,127:0,416:100,417:1,418:0,411:200,1333:300,1334:150,1337:10,1338:10,1339:0})
        b.temperature(0,290);cond([290,290]);b.reset_faults()
        inp=Inputs(b,e);inp.temperatures({0:200});b.start()
        b.wait('typeII recovery actual cooling',lambda s:s['outdoor_status'][0]==[2,2],210)
        for label,ambient,temps in (('environment_above10',101,[290,290]),('system1_above42',79,[421,290]),('system2_above42',79,[290,421])):
            row=dict(label=label);e['cases'].append(row)
            s=observe(row,'establish_lowfan_off',79,[290,290],55)
            assert not any(s['output'][i] for i in (2,3,7)),('lowfan-off precondition',s)
            if label=='environment_above10':
                s=observe(row,'equal10_no_restart',100,[290,290],35)
                assert not s['output'][3]
            s=observe(row,'recovery_continuous_compressors',ambient,temps,55)
            row.update(passed=[s['output'][i] for i in (2,3,7)]==[0,1,0],finished=now());b.save()
            print('TYPEII RECOVERY',label,row['passed'],flush=True)
        # Change only the normal AI signal type, preserving original config.
        inp.adc({0:745,1:745})
        for ch in range(2):write(2681+12*ch,1);span(ch,pressure(290),pressure(421))
        row=dict(label='independent_OR_handover');e['cases'].append(row)
        s=observe(row,'both_false_lowfan_off',79,[290,290],55,745)
        assert not s['output'][3]
        observe(row,'environment_only',101,[290,290],18,745)
        observe(row,'both_true_overlap',101,[421,290],3,3724)
        s=observe(row,'condensing_only_short',79,[421,290],16,3724)
        row['no_restart_before_individual30s']=not bool(s['output'][3])
        active=[s for seg in row['segments'][1:] for s in seg['samples']]
        truth=lambda s:signed16(s['params']['1422'])>100 or max(s['condensing10'])>420
        first=next(i for i,s in enumerate(active) if truth(s))
        row['OR_continuous']=all(truth(s) for s in active[first:])
        s=observe(row,'condensing_independent30s_plus_stage_delay',79,[421,290],35,3724)
        row.update(passed=row['no_restart_before_individual30s'] and row['OR_continuous'] and bool(s['output'][3]),finished=now())
        b.save();print('TYPEII INDEPENDENT OR',row['passed'],flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            for ch in range(2):
                span(ch,signed16(original[2684+12*ch]),signed16(original[2685+12*ch]))
                write(2681+12*ch,original[2681+12*ch])
            p=b.outsy['Parameter'][0]
            e['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(p+2*(302+a-2680)) for a,v in original.items())
            assert e['ai_restore_verified'],'AI restoration mismatch'
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    pause_module.paused();run()
    import bench_restart_fix_20261112 as runner
    runner.audit('after_typeII_recovery_audit')
