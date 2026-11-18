"""Whole-board fixed/VFD chart checks using normal AI mapping inputs.

The high-pressure input engineering span is deliberately narrow (1 kPa),
so both possible endpoints map to the same exact condensing temperature.
No demands, timers, control states or outputs are written.
"""
from joint_v1058_context_20261111 import *
from app import Psc330MonitorApp
import struct

CurrentBench=current_bench_class()


def run(pair=(2,4)):
    b=CurrentBench('B03_pressure_fan_'+str(pair[0])+'_'+str(pair[1]))
    e=dict(started=now(),status='running',points=[],input_writes=[],ai_original={},
        pair=pair,ids=(['O-FANCURVE-016','O-FANCURVE-017','O-FANCURVE-018','O-FANCURVE-019','O-FANCURVE-020'] if pair[1]==4 else
            ['O-FANCURVE-012','O-FANCURVE-013','O-FANCURVE-014','O-FANCURVE-015'] if pair[1]==2 else
            ['O-FANCURVE-005','O-FANCURVE-006','O-FANCURVE-007']),
        scope='Normal330 cooling start; normal330 gateway pressure-AI engineering-span input fixture. Both endpoints have identical PT result; real316 fan state, software output and exact elapsed time. Not pressure calibrator/terminal/PRODUCTION acceptance.')
    b.log['fixed_vfd']=e;b.save()
    m=object.__new__(Psc330MonitorApp);m.values={}
    def retry_read(a,n=1):
        for attempt in range(3):
            try:return b.rd(a,n)
            except Exception:
                if attempt==2:raise
                time.sleep(.25)
    m.read_now=retry_read
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v & 65535)
    p=b.outsy['Parameter'][0]

    def ai_write(address,value,restore=False):
        target=302+address-2680
        if not restore:assert str(address) in e['ai_original'],'Capture entire input span before first write'
        if signed16(retry_read(address)[0])!=value:
            try:m.write_outdoor_gateway_register(1830,address,target,value)
            except Exception as exc:
                e.setdefault('gateway_exceptions',[]).append(dict(address=address,value=value,restore=restore,error=repr(exc)));b.save()
        began=time.monotonic()
        while True:
            actual=signed16(b.ot.read16(p+2*target));mirror=signed16(retry_read(address)[0])
            if actual==mirror==value:break
            assert time.monotonic()-began<55,('AI write did not settle',address,value,actual,mirror)
            time.sleep(.2)
        e['input_writes'].append(dict(at=now(),hmi=address,parameter316=target,value=value,actual=actual,mirror=mirror,restore=restore));b.save()

    def map_span(ch,low,high,restore=False):
        base=2680+ch*12;old_high=signed16(retry_read(base+5)[0])
        if low>=old_high:ai_write(base+5,max(low+1,high),restore)
        ai_write(base+4,low,restore);ai_write(base+5,high,restore)

    def pt10(pressure):
        j=min(870,(pressure+100)//5);rest=pressure%5
        return table[j]+rest*(table[j+1]-table[j])//5

    def pressure_for(temp10):
        matches=[a for a in range(100,3400) if pt10(a)==pt10(a+1)==temp10]
        assert matches,('no exact 1kPa PT span',temp10)
        return matches[len(matches)//2]

    def read():
        row=dict(at=now(),t=time.monotonic(),output=list(b.ot.read_memory_block8(b.outsy['output'][0],8)),
            pressure=[signed16(b.ot.read16(p+2*a)) for a in (1443,1445)],
            params={str(a):signed16(b.ot.read16(p+2*a)) for a in (1422,1425,1426,1463,1468,1501)},
            alarms=[b.ot.read16(p+2*a) for a in range(600,628)])
        row['condensing10']=[pt10(a) for a in row['pressure']]
        for name in ('OutdoorVfdOn','OutdoorFixedOn','OutdoorVfdSpeed','OutdoorVfdLoadCount','OutdoorVfdUnloadCount',
                     'OutdoorVfdForceFullCount','OutdoorFanChangeSeconds','OutdoorFanRunSeconds','OutdoorFanStopSeconds',
                     'OutdoorFanStage','OutdoorTypeIIForceHighEnable','OutdoorTypeIIForceHighCount'):
            if name in b.outsy:
                a,n=b.outsy[name];raw=bytes(b.ot.read_memory_block8(a,n))
                row[name]=struct.unpack('<H',raw)[0] if n==2 else (struct.unpack('<I',raw)[0] if n==4 else (raw[0] if n==1 else list(raw)))
        row['ao']=b.ot.read16(p+2*1468)
        return row

    def point(label,temps,seconds,kind):
        row=dict(label=label,requested_t=time.monotonic(),at=now(),temperatures10=temps,
                 seconds=seconds,kind=kind,samples=[])
        e['points'].append(row);b.save()
        for ch,temp in enumerate(temps):
            pressure=pressure_for(temp);map_span(ch,pressure,pressure+1)
        began=time.monotonic();exact=None
        while True:
            s=read();row['samples'].append(s)
            assert not any(s['alarms']),('unexpected outdoor fault',label,s)
            if s['condensing10']==temps:
                if exact is None:exact=s['t'];row['first_exact_t']=exact
                if s['t']-exact>=seconds:break
            elif exact is not None:raise AssertionError(('PT input continuity interrupted',label,s))
            assert time.monotonic()-began<seconds+20,('exact PT span not achieved',label,s)
            time.sleep(.20)
        row['final']=s;row['observed_exact_s']=s['t']-exact
        exact_samples=[q for q in row['samples'] if q['t']>=exact]
        row['first_speed10']=exact_samples[0]['OutdoorVfdSpeed'];row['last_speed10']=s['OutdoorVfdSpeed']
        row['positive_step_0p1hz']=[dict(fixed=bool(a['OutdoorFixedOn']),delta=z['OutdoorVfdSpeed']-a['OutdoorVfdSpeed'],dt_s=z['t']-a['t'])
                                   for a,z in zip(exact_samples,exact_samples[1:])
                                   if a['OutdoorFixedOn']==z['OutdoorFixedOn'] and 50<=a['OutdoorVfdSpeed']<z['OutdoorVfdSpeed']<500]
        if kind=='hold':row['behavior_matches']=row['first_speed10']==row['last_speed10']
        elif kind=='chart_load':row['behavior_matches']=row['last_speed10']>row['first_speed10']
        else:row['behavior_matches']=None
        b.save();print('FIXED VFD',label,'speed',row['first_speed10'],row['last_speed10'],
            'on',s['OutdoorVfdOn'],s['OutdoorFixedOn'],'matches',row['behavior_matches'],flush=True)
        return row

    try:
        expected_ai={2684:0,2685:5000,2696:0,2697:5000}
        actual_ai={a:b.ot.read16(p+2*(302+a-2680)) for a in expected_ai}
        e['baseline_ai_direct']=actual_ai;b.save()
        assert actual_ai==expected_ai,('pressure fixture baseline needs restoration',actual_ai,expected_ai)
        b.setup(0);b.gateway(1830,pair[0]);b.gateway(1831,pair[1])
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
            365:1,411:200,10:500,12:500,1333:300,1334:150,1337:30,1338:30})
        b.gateway(1841,50);b.gateway(1842,5);b.gateway(1843,10)
        b.temperature(0,290);b.reset_faults()
        assert b.rd(39)==[3] and b.ot.read16(p+2*107)==1,'requires existingR410A and pressure mode'
        a,n=b.outsy['R410ATemp'];table=struct.unpack('<'+'h'*(n//2),bytes(b.ot.read_memory_block8(a,n)))
        e['settings']={str(a):b.ot.read16(p+2*a) for a in (165,166,176,177,178,179,180)}
        # Read both endpoints on the actual controller before changing either.
        for ch in range(2):
            base=2680+ch*12
            for a in (base+4,base+5):
                original=retry_read(a)[0]
                assert original==b.ot.read16(p+2*(302+a-2680)),('incoherent original AI setting',a,original)
                e['ai_original'][str(a)]=original
        b.save()
        # Establish a valid input before the ordinary indoor start.
        for ch in range(2):
            pressure=pressure_for(350);map_span(ch,pressure,pressure+1)
        b.start();b.wait('fixed/VFD four actual cooling feedback',lambda s:all(v==2 for pair in s['outdoor_status'] for v in pair),180)
        e['normal_start']=b.snapshot('fixed/VFD ordinary330 start')
        if pair[1]==3:
            for label,temps,stage in [('TL',[300,440],1),('TL_plus_half',[375,440],2),
                                      ('TL_plus_TLD',[450,450],3),('above_TL_plus_TLD',[451,451],4),
                                      ('lower_temp_selects_stage',[375,490],2),('force_at_50',[375,500],4)]:
                z=point(label,temps,62,'observe')
                z['expected_stage']=stage; z['behavior_matches']=z['final']['OutdoorFanStage']==stage
                b.save()
        else:
            point('35C_initial_hold',[350,350],33,'hold')
            point('37C_establish_full_load',[370,370],110 if pair[1]==4 else 80,'observe')
            point('33C_establish_intermediate_speed',[330,330],20,'observe')
            intermediate=point('35C_intermediate_hold',[350,350],33,'hold')
            e['intermediate_established']=50<intermediate['last_speed10']<500
            point('36C_both_hold_boundary',[360,360],35,'hold')
            point('35C_36C_hold_boundary',[350,360],35,'hold')
            if pair[1]==2: point('34C_both_hold_boundary',[340,340],35,'hold')
            point('37C_full_load_switch_and_rate',[370,370],110 if pair[1]==4 else 80,'observe')
            point('33C_unload_switch_to_fans_off',[330,330],150 if pair[1]==4 else 115,'observe')
            point('off_hold_below_34',[330,330],35,'observe')
            point('45_1C_after_verified_off',[451,451],42,'observe')
        e['status']='completed_see_per_point';b.save()
    except BaseException:
        e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.stop()
            for ch in range(2):
                base=2680+ch*12
                if all(str(base+i) in e['ai_original'] for i in (4,5)):
                    low=signed16(e['ai_original'][str(base+4)]); high=signed16(e['ai_original'][str(base+5)])
                    map_span(ch,low,high,True)
            e['ai_restore_verified']={a:retry_read(int(a))[0]==v and b.ot.read16(p+2*(302+int(a)-2680))==v for a,v in e['ai_original'].items()}
            assert all(e['ai_restore_verified'].values())
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('pair',choices=('13','12','22','24'),default='24',nargs='?')
    run(tuple(map(int,parser.parse_args().pair)))
