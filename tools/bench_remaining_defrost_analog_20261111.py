"""Analog high-pressure input during actual defrost; alarms/output never forced."""
from bench_remaining_adc_20261111 import *
from bench_remaining_outdoor_20261111 import HEAT
from app import Psc330MonitorApp
from remaining529_manual_defrost_input_20261105 import manual_defrost


def run(channel):
    b=current_bench_class()('remaining_defrost_analog_HP'+str(channel));inp=None
    e=b.log['remaining_functional']=dict(kind='defrost_analog_HP'+str(channel),cases=[],
        scope='Normal330 pressure AI span and raw ADC input; actual defrost entrance via legacy HMI request, software alarm/output readback; no invented analog exit threshold or physical pressure qualification')
    base=2680+12*channel;old={a:b.rd(a)[0] for a in (base+4,base+5)};e['ai_original']=old
    m=object.__new__(Psc330MonitorApp);m.values={};m.read_now=lambda a,n=1:b.rd(a,n)
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)

    def write(a,v):m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
    def scale(low,high):
        if low>=signed16(b.rd(base+5)[0]):write(base+5,max(low+1,high))
        write(base+4,low);write(base+5,high)

    def wait(label,predicate,seconds,row):
        end=time.monotonic()+seconds;last=0
        while time.monotonic()<end:
            s=inp.sample();s.update(mirror_phase=b.rd(1550,2),mirror_fault=b.rd(2028+channel)[0])
            row.setdefault('samples',[]).append(s)
            if predicate(s):row[label]=s;b.save();return s
            if time.monotonic()-last>25:last=time.monotonic();b.save();print('DEFROST ANALOG',channel,label,s['phase'],s['pressures'],flush=True)
        raise TimeoutError(label)

    try:
        b.setup(1);b.config({**HEAT,56:3800});b.temperature(0,220)
        assert b.rd(base+2,2)==[400,2000]
        scale(3000,4600);b.gateway(1856,2);b.gateway(1857,2)
        b.attach_extra();inp=ADCInputs(b);inp.apply(channel,1000)
        pre={}
        wait('healthy3600_before_start',lambda s:s['pressures'][channel]==3600 and not any(s['alarms']),15,pre)
        e['precondition']=pre;b.reset_faults();b.start()
        b.wait('analog defrost four heating',lambda s:all(v==3 for q in s['outdoor_status'] for v in q),240)
        b.wr(540,1);manual_defrost(b,True,session=b.extra[1][1])
        wait('actual_defrost',lambda s:s['phase']==s['mirror_phase']==[8,8] and s['output'][:2]==[1,1],70,pre)
        row=dict(id='O-DEFROST-011',label='AI'+str(channel)+'_3801kPa_during_defrost',samples=[])
        e['cases'].append(row);issued=inp.apply(channel,1201)
        wait('exact3801',lambda s:s['t']>=issued and s['pressures'][channel]==3801,15,row)
        began=time.monotonic()
        while time.monotonic()-began<5:
            s=inp.sample();row['samples'].append(s)
        exact=[s for s in row['samples'] if s['pressures'][channel]==3801 and s['defrost_state']==[1]]
        row.update(final=s,finished=now(),
            limit='Only samples in actual defrost judge alarm masking; an early analog-pressure exit has no specified threshold and is retained as observation, not automatically a defect')
        if exact and exact[-1]['t']-exact[0]['t']>=3:
            row['passed']=all(s['alarms'][6+channel]==0 for s in exact)
        else:row['incomplete_exposure']='Actual defrost with3801kPa was not observed continuously for3s'
        inp.apply(channel,1000);b.save();print('DEFROST ANALOG RESULT',channel,row.get('passed','observation only'),flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
            scale(signed16(old[base+4]),signed16(old[base+5]))
            p=b.outsy['Parameter'][0]
            e['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(p+2*(302+a-2680)) for a,v in old.items())
            assert e['ai_restore_verified'];b.reset_faults()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('channel',type=int,choices=(0,1));run(p.parse_args().channel)
