"""HP functional boundaries from normal AI spans; acquisition remains read-only."""
import full_queue_context_20261113
from full_queue_context_20261113 import *
from bench_remaining_outdoor_20261111 import HEAT
from bench_remaining_adc_20261111 import ADCInputs
from app import Psc330MonitorApp

def run():
    b=current_bench_class()('Q03_HP_normal_gateway_span_recheck');inp=None
    e=b.log['remaining_functional']=dict(kind='HP_normal_gateway_span',cases=[],
        scope='Normal330 AI engineering spans create pressure test values; raw acquisition read-only, no pressure/fault/timer/output RAM writes; software boundaries only, not physical pressure calibration')
    original={a:b.rd(a)[0] for a in (2684,2685)};e['ai_original']=original
    m=object.__new__(Psc330MonitorApp);m.values={};m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)
    def write(a,v):
        if signed16(b.rd(a)[0])!=v:m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
    def span(low,high):
        if low>=signed16(b.rd(2685)[0]):write(2685,high)
        write(2684,low);write(2685,high)
    def sample(after=0):
        s=inp.sample(after);s.update(mirror=b.rd(2028)[0],summary=b.rd(737)[0],peer=b.rd(1625,2))
        return s
    row=dict(id='O-PROTECT-012',label='3799_3800_3801_normal_gateway',samples=[],segments=[])
    e['cases'].append(row)
    def hold(pressure,seconds):
        issued=time.monotonic();span(pressure,pressure+1)
        part=dict(pressure_kPa=pressure,issued_t=issued,samples=[]);row['segments'].append(part)
        end=time.monotonic()+seconds+20;exact=None
        while time.monotonic()<end:
            s=sample(issued);row['samples'].append(s);part['samples'].append(s)
            if s['pressures'][0]==pressure:
                if exact is None:exact=s['t']
                if s['t']-exact>=seconds:part.update(first_exact_t=exact,final=s);b.save();return part
            else:exact=None
        raise TimeoutError(('stable engineering input',pressure))
    try:
        b.setup(1);b.config({**HEAT,56:3800});b.temperature(0,220)
        span(3799,3800)
        inp=ADCInputs(b)  # values remain all-1: worker observes without writes.
        baseline=hold(3799,3)
        e['pre_reset_after_span_settled']=baseline['final']
        b.reset_faults()
        baseline=hold(3799,3)
        assert not any(baseline['final']['sensor_status'][:4]) and not any(baseline['final']['alarms'])
        b.reset_faults();b.start()
        b.wait('HP gateway four actual heating',lambda s:all(v==3 for p in s['outdoor_status'] for v in p),240)
        below=hold(3799,3);equal=hold(3800,3)
        row['no_trip_below_or_equal']=all(not s['alarms'][6] for part in (below,equal) for s in part['samples'])
        high=hold(3801,4)
        row['corresponding_protection']=high['final']['alarms'][6]==1 and high['final']['output'][:2]==[0,1]
        exact=[s for s in high['samples'] if s['pressures'][0]==3801]
        first_trip=next((s for s in exact if s['alarms'][6]),None)
        row['observed_trip_after_first_sample_s']=first_trip['t']-exact[0]['t'] if first_trip else None
        row['first_high_counter']=exact[0]['high_press_counts']
        row['timing_limit']='Gateway writes may precede first high sample; retain counter/trace, do not claim precise2s or subsecond pulse coverage'
        b.reset_faults();active=hold(3801,3)
        row['reset_active_stays_protected']=active['final']['alarms'][6]==1 and active['final']['output'][0]==0
        released=hold(3800,3)
        row['latched_before_reset']=released['final']['alarms'][6]==1
        b.reset_faults();end=time.monotonic()+55
        while time.monotonic()<end:
            s=sample();row['samples'].append(s)
            if not s['alarms'][6] and not s['mirror']:row['recovery_verified']=True;break
        row['passed']=all(row.get(k,False) for k in ('no_trip_below_or_equal','corresponding_protection','reset_active_stays_protected','latched_before_reset','recovery_verified'))
        row['finished']=now();b.save();print('HP GATEWAY FUNCTIONAL',row['passed'],flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            span(signed16(original[2684]),signed16(original[2685]))
            e['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(b.outsy['Parameter'][0]+2*(302+a-2680)) for a,v in original.items())
            assert e['ai_restore_verified'];b.reset_faults()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':run()
