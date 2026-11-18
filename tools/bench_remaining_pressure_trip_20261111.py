"""Analog HP threshold via ordinary AI scaling and raw ADC input, not a calibrator."""
from bench_remaining_adc_20261111 import *
from bench_remaining_outdoor_20261111 import HEAT
from app import Psc330MonitorApp


def run():
    b=current_bench_class()('remaining_analog_HP_trip');inp=None
    e=b.log['remaining_functional']=dict(kind='analog_HP_threshold',cases=[],
        scope='AI0 normal330 engineering-span setting and acquisition ADC; threshold/timer/output readback, no physical pressure or terminal measurement')
    old={a:b.rd(a)[0] for a in (2684,2685)}
    e['ai_original']=old
    m=object.__new__(Psc330MonitorApp);m.values={}
    m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)

    def write_ai(a,v):
        m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
        end=time.monotonic()+60
        while b.rd(a)[0]!=(v&65535):
            assert time.monotonic()<end,('AI mirror settle',a,v)
            time.sleep(.2)

    def scale(low,high):
        if low>=signed16(b.rd(2685)[0]):write_ai(2685,max(low+1,high))
        write_ai(2684,low);write_ai(2685,high)

    try:
        b.setup(1);b.config(HEAT);b.config({56:3800});b.temperature(0,220)
        end=time.monotonic()+40
        while b.ot.read16(b.outsy['Parameter'][0]+2*56)!=3800:
            assert time.monotonic()<end,'normal broadcast pressure threshold did not settle'
            time.sleep(.2)
        assert b.rd(2682,2)==[400,2000],('ADC input endpoints differ',b.rd(2682,2))
        scale(3000,4600)
        inp=ADCInputs(b);at=inp.apply(0,1000)
        end=time.monotonic()+12
        while time.monotonic()<end:
            s=inp.sample(at)
            if s['pressures'][0]==3600 and s['sensor_status'][0]==0:break
        else:raise RuntimeError(('one kPa per ADC count calibration precondition absent',s))
        b.reset_faults();b.start()
        b.wait('analog HP ordinary four heat',lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),210)
        row=dict(id='O-PROTECT-012',label='3799_3800_hold_and3801_continuous_trip',samples=[],segments=[])
        e['cases'].append(row);b.save()

        def segment(pressure,seconds):
            issued=inp.apply(0,pressure-2600);end=time.monotonic()+seconds+10;exact=None
            part=dict(pressure_kPa=pressure,seconds=seconds,issued=issued,samples=[]);row['segments'].append(part)
            while time.monotonic()<end:
                s=inp.sample(issued);part['samples'].append(s);row['samples'].append(s)
                if s['pressures'][0]==pressure:
                    if exact is None:exact=s['t']
                    if s['t']-exact>=seconds:part['final']=s;return part
                else:exact=None
            raise TimeoutError(('exact pressure segment',pressure))

        below=segment(3799,3);equal=segment(3800,3)
        row['no_trip_below_or_equal']=all(not s['alarms'][6] for part in (below,equal) for s in part['samples'])
        short=segment(3801,.9);broken=segment(3800,2)
        row['interrupted_short_no_trip']=not any(s['alarms'][6] for part in (short,broken) for s in part['samples'])
        at=inp.apply(0,1201);end=time.monotonic()+12;exact=None
        while time.monotonic()<end:
            s=inp.sample(at);row['samples'].append(s)
            if s['pressures'][0]==3801 and exact is None:exact=s['t']
            if s['alarms'][6] and s['output'][:2]==[0,1]:
                row.update(trip=s,observed_trip_after_exact_s=s['t']-exact);break
        else:raise TimeoutError('analog3801 pressure did not stop corresponding compressor')
        b.reset_faults();held=segment(3801,3)
        row['active_source_reset_retains']=held['final']['alarms'][6]==1 and held['final']['output'][0]==0
        released=segment(3800,3)
        row['retained_until_reset']=released['final']['alarms'][6]==1
        b.reset_faults();end=time.monotonic()+70
        while time.monotonic()<end:
            s=inp.sample();row['samples'].append(s)
            if not s['alarms'][6] and not b.rd(2028)[0]:row['recovery_verified']=True;break
        row.update(final=s,finished=now(),
            passed=all(row.get(k) for k in ('no_trip_below_or_equal','interrupted_short_no_trip',
                'active_source_reset_retains','retained_until_reset','recovery_verified')))
        row['limit']='Subsecond fixture sampling does not close exact1.9/2.0/2.1s timing; original timestamp and high-pressure counter retained'
        b.save();print('ANALOG HP',row['passed'],row.get('observed_trip_after_exact_s'),flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            scale(signed16(old[2684]),signed16(old[2685]))
            p=b.outsy['Parameter'][0]
            e['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(p+2*(302+a-2680)) for a,v in old.items())
            assert e['ai_restore_verified'],'AI span restore did not verify at destination'
            b.reset_faults()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
