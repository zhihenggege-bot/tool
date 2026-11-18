"""Focused VFD limits, rate, hold and unloading evidence via normal330 gateway."""
import argparse
import shutil
import struct
import time
import traceback
import vfd_min30_fix_context_20261117 as ctx
from app import Psc330MonitorApp

g=ctx.g


def run(pair,minimum30_only=False):
    b=g.Bench('targeted_vfd_'+''.join(map(str,pair)))
    out=ctx.DAY/('targeted_vfd_'+''.join(map(str,pair))+'_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=g.now(),pair=pair,minimum30_only=minimum30_only,checks={},points=[],driver_sha256=g.runtime.sha(ctx.R/'tools/retest_vfd_unload_v1246_20261117.py'),
        firmware_versions=b.rd(2622,18),profile=b.rd(1298,2),
        scope='Normal330 pressure engineering-span fixture; actual316 state and software AO. No physical voltage or formal timing acceptance.')
    b.log['targeted_vfd']=q
    driver_dir=ctx.DAY/'drivers'/q['driver_sha256'];driver_dir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ctx.R/'tools/retest_vfd_unload_v1246_20261117.py',driver_dir/'retest_vfd_unload_v1246_20261117.py')
    def save():b.save();g.dump(out,q)
    def read_with_retry(a,n=1):
        # Reads are safe to repeat; retain each failed exchange in events.jsonl.
        for attempt in range(3):
            try:return b.rd(a,n)
            except Exception:
                if attempt==2:raise
                g.event('vfd_read_retry',address=a,count=n,attempt=attempt+1)
                time.sleep(.2)
    m=object.__new__(Psc330MonitorApp);m.values={};m.read_now=read_with_retry
    m.write_single=lambda a,v:b.c.write_single_register(1,a,v&65535)
    p=b.outsy['Parameter'][0];original={};table=None
    q['default_tables_on_board']={}
    for address in (176,177):
        q['default_tables_on_board'][str(address)]={
            name:b.ot.read16(b.outsy[name][0]+2*address)
            for name in ('Parameter_def','Parameter_min','Parameter_max')}
    assert q['default_tables_on_board']['177']=={'Parameter_def':30,'Parameter_min':0,'Parameter_max':30}
    assert q['default_tables_on_board']['176']=={'Parameter_def':50,'Parameter_min':30,'Parameter_max':50}
    def ai(a,v):
        if g.signed16(b.rd(a)[0])!=v:m.write_outdoor_gateway_register(1830,a,302+a-2680,v)
        end=time.monotonic()+50
        while g.signed16(b.rd(a)[0])!=v or g.signed16(b.ot.read16(p+2*(302+a-2680)))!=v:
            assert time.monotonic()<end,('AI span not delivered',a,v);time.sleep(.15)
        g.event('vfd_pressure_span_write',address=a,value=v)
    def span(ch,lo,hi):
        a=2680+12*ch
        if lo>=g.signed16(b.rd(a+5)[0]):ai(a+5,hi)
        ai(a+4,lo);ai(a+5,hi)
    def pt(pressure):
        j=min(870,(pressure+100)//5)
        return table[j]+(pressure%5)*(table[j+1]-table[j])//5
    def temperature(t10):
        matches=[v for v in range(100,3400) if pt(v)==pt(v+1)==t10]
        assert matches,t10
        v=matches[len(matches)//2]
        for ch in range(2):span(ch,v,v+1)
    def sample():
        s=dict(at=g.now(),t=time.monotonic(),output=list(b.ot.read_memory_block8(*b.outsy['output'])),
               pressure=[b.ot.read16(p+2*a) for a in (1443,1445)],
               ao=b.ot.read16(p+2*1468),faults=[b.ot.read16(p+2*a) for a in range(600,628)])
        s['condensing10']=[pt(v) for v in s['pressure']]
        for name in ('OutdoorVfdSpeed','OutdoorVfdOn','OutdoorFixedOn','OutdoorVfdLoadCount','OutdoorVfdUnloadCount',
                     'OutdoorVfdForceFullCount','OutdoorFanRunSeconds','OutdoorFanStopSeconds','OutdoorFanRegulationStop'):
            a,n=b.outsy[name];raw=bytes(b.ot.read_memory_block8(a,n))
            s[name]=int.from_bytes(raw,'little',signed=name=='OutdoorVfdSpeed') if n<=4 else list(struct.unpack('<'+'I'*(n//4),raw))
        g.event('targeted_vfd_sample',pair=pair,sample=s)
        return s
    def capture(label,t10,seconds,predicate=None):
        row=dict(label=label,requested_t10=t10,samples=[]);q['points'].append(row);save()
        temperature(t10);start=time.monotonic();first=None;hold=None;heartbeat=0
        while time.monotonic()-start<seconds:
            s=sample();row['samples'].append(s)
            assert not any(s['faults']),('Unexpected fault during curve input fixture',s)
            if s['condensing10']==[t10,t10]:
                if first is None:first=s['t']
                if predicate and predicate(s):
                    if hold is None:hold=s['t']
                    if s['t']-hold>=3:row['predicate_met']=True;break
                else:hold=None
            if time.monotonic()-heartbeat>22:
                heartbeat=time.monotonic();save();print('VFD CAPTURE',pair,label,s['OutdoorVfdSpeed'],s['ao'],flush=True)
            time.sleep(.18)
        row['final']=s;row['first_exact_t']=first;row['finished']=g.now();save()
        return row
    try:
        b.setup(0)
        b.gateway(1830,pair[0]);b.gateway(1831,pair[1])
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,160:250,161:250,120:20,412:1,
                  416:100,417:1,418:0,315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
                  365:1,411:200,10:500,12:500,1337:30,1338:30})
        b.gateway(1841,40);b.gateway(1842,10);b.gateway(1843,10)
        b.temperature(0,290);b.reset_faults()
        assert b.rd(39)==[3] and b.ot.read16(p+214)==1
        a,n=b.outsy['R410ATemp'];table=struct.unpack('<'+'h'*(n//2),bytes(b.ot.read_memory_block8(a,n)))
        for ch in range(2):
            for a in (2684+12*ch,2685+12*ch):
                original[a]=b.rd(a)[0]
                assert original[a]==b.ot.read16(p+2*(302+a-2680))
        q['ai_original']=original;save();temperature(350)
        b.start();b.wait('VFD normal cooling established',lambda s:all(v==2 for row in s['outdoor_status'] for v in row),200)
        if minimum30_only:
            b.gateway(1842,30)
            minimum=capture('configured_minimum30Hz_software6V',350,65,
                lambda s:s['OutdoorVfdOn']==1 and s['OutdoorVfdSpeed']==300 and s['ao']==600)
            q['checks']['configured_minimum30_reached']=minimum.get('predicate_met',False)
            loaded=capture('minimum30_reload37C_to40Hz',370,80,
                lambda s:s['OutdoorVfdSpeed']==400 and s['ao']==800)
            q['checks']['minimum30_reload40_reached']=loaded.get('predicate_met',False)
            unload=capture('minimum30_unload33C_to_off',330,75,lambda s:not s['OutdoorVfdOn'])
            steps=[];edges=[]
            for a,z in zip(unload['samples'],unload['samples'][1:]):
                if a['OutdoorVfdOn'] and not z['OutdoorVfdOn']:
                    edges.append(dict(at=z['at'],previous_speed10=a['OutdoorVfdSpeed'],previous_ao=a['ao']))
                delta=a['OutdoorVfdSpeed']-z['OutdoorVfdSpeed']
                if delta>0 and a['OutdoorVfdOn'] and z['OutdoorVfdOn']:
                    steps.append(dict(t=z['t'],delta10=delta))
            rate=sum(e['delta10'] for e in steps[1:])/10/(steps[-1]['t']-steps[0]['t']) if len(steps)>=5 else None
            q['minimum30_off_edges']=edges;q['minimum30_unload_steps']=steps;q['minimum30_unload_rate_Hz_per_s']=rate
            q['checks']['minimum30_unload_reaches_minimum_before_off']=unload.get('predicate_met',False) and bool(edges) and all(e['previous_speed10']<=310 for e in edges)
            q['checks']['minimum30_unload_1Hz_per_s']=rate is not None and abs(rate-1)<=.15 and all(e['delta10']==10 for e in steps)
            samples=[s for point in q['points'] for s in point['samples']]
            q['checks']['frequency_bounds']=all(s['OutdoorVfdSpeed']==0 or 300<=s['OutdoorVfdSpeed']<=400 for s in samples)
            stable=[z for a,z in zip(samples,samples[1:]) if a['OutdoorVfdSpeed']==z['OutdoorVfdSpeed']]
            q['checks']['software_AO_fixed_50Hz_scaling']=bool(stable) and all(s['ao']==2*s['OutdoorVfdSpeed'] for s in stable)
            q['passed']=all(q['checks'].values());save()
            print('MINIMUM30 TARGETED RESULT',pair,q['checks'],flush=True)
            return
        minimum=capture('minimum_10Hz_at_35C',350,8)
        q['checks']['minimum_frequency']=all(s['OutdoorVfdSpeed']==100 and s['ao']==200 for s in minimum['samples'])
        loaded=capture('normal_loading_37C_maximum40Hz',370,105,
                       lambda s:s['OutdoorVfdSpeed']==400 and (pair[1]!=4 or s['OutdoorFixedOn']==1))
        q['checks']['maximum40_reached']=loaded.get('predicate_met',False)
        rows=loaded['samples'];edges=[]
        for a,z in zip(rows,rows[1:]):
            delta=z['OutdoorVfdSpeed']-a['OutdoorVfdSpeed']
            if delta>0 and a['OutdoorFixedOn']==z['OutdoorFixedOn'] and a['OutdoorVfdSpeed']>=100 and z['OutdoorVfdSpeed']<=400:
                edges.append(dict(at=z['at'],t=z['t'],delta_0p1Hz=delta,fixed=a['OutdoorFixedOn']))
        q['load_edges']=edges
        q['checks']['normal_load_step_1Hz']=len([e for e in edges if not e['fixed']])>=5 and all(e['delta_0p1Hz']==10 for e in edges if not e['fixed'])
        if pair[1]==4:q['checks']['fixed_fan_load_step_2Hz']=len([e for e in edges if e['fixed']])>=5 and all(e['delta_0p1Hz']==20 for e in edges if e['fixed'])
        q['measured_load_rates_Hz_per_s']={}
        for fixed,expected in ((0,1.0),(1,2.0)):
            selected=[edge for edge in edges if bool(edge['fixed'])==bool(fixed)]
            if fixed and pair[1]!=4:continue
            rate=(sum(edge['delta_0p1Hz'] for edge in selected[1:])/10/(selected[-1]['t']-selected[0]['t'])) if len(selected)>=5 else None
            q['measured_load_rates_Hz_per_s'][str(fixed)]=rate
            q['checks']['load_rate_'+str(expected)+'Hz_per_s']=rate is not None and abs(rate-expected)<=0.15
        hold=capture('hold35C_after_loading',350,12)
        stable=[s for s in hold['samples'] if s['t']>=hold['first_exact_t']+2]
        q['checks']['hold_35C']=bool(stable) and len({s['OutdoorVfdSpeed'] for s in stable})==1
        # Establish a genuine intermediate speed without relying on the
        # unloading path under test: temporarily lower the normal maximum,
        # then raise it again while the condensation input remains in hold.
        b.gateway(1841,30)
        limited=capture('maximum30Hz_at35C',350,8,lambda s:s['OutdoorVfdSpeed']==300 and s['ao']==600)
        q['checks']['maximum30_software6V']=limited.get('predicate_met',False)
        b.gateway(1841,40)
        intermediate=capture('intermediate30Hz_hold_at35C_maximum40',350,12)
        stable=[s for s in intermediate['samples'] if s['t']>=intermediate['first_exact_t']+2]
        q['checks']['intermediate_hold_35C']=bool(stable) and all(s['OutdoorVfdSpeed']==300 and s['ao']==600 for s in stable)
        if pair==(2,2):
            reloaded=capture('reload_from30_to40_before_primary_unload',370,80,
                lambda s:s['OutdoorVfdSpeed']==400 and s['ao']==800)
            q['checks']['primary_unload_from40_established']=reloaded.get('predicate_met',False)
        unload=capture('unload33C_to_fans_off',330,115,lambda s:not s['OutdoorVfdOn'] and not s['OutdoorFixedOn'])
        q['checks']['unload_to_off']=unload.get('predicate_met',False)
        drops=[]
        for a,z in zip(unload['samples'],unload['samples'][1:]):
            if a['OutdoorVfdOn'] and not z['OutdoorVfdOn']:
                drops.append(dict(at=z['at'],previous_speed10=a['OutdoorVfdSpeed'],previous_ao=a['ao'],
                                  unload_count=z['OutdoorVfdUnloadCount'],run_s=z['OutdoorFanRunSeconds']))
        q['off_edges']=drops
        q['checks']['unload_reaches_minimum_before_off']=bool(drops) and all(e['previous_speed10']<=110 for e in drops)
        # Keep the original 10Hz defect reproduction separate from the newly
        # requested 30Hz minimum setting; use normal protocol writes for both.
        if pair==(2,2):
            b.gateway(1842,30)
            configured_min=capture('configured_minimum30Hz_software6V',350,65,
                lambda s:s['OutdoorVfdOn']==1 and s['OutdoorVfdSpeed']==300 and s['ao']==600)
            q['checks']['configured_minimum30_reached']=configured_min.get('predicate_met',False)
            reload30=capture('minimum30_reload37C_to40Hz',370,80,
                lambda s:s['OutdoorVfdSpeed']==400 and s['ao']==800)
            q['checks']['minimum30_reload40_reached']=reload30.get('predicate_met',False)
            decline30=capture('minimum30_unload33C_to_off',330,75,
                lambda s:not s['OutdoorVfdOn'])
            edge30=[];steps30=[]
            for a,z in zip(decline30['samples'],decline30['samples'][1:]):
                if a['OutdoorVfdOn'] and not z['OutdoorVfdOn']:
                    edge30.append(dict(at=z['at'],previous_speed10=a['OutdoorVfdSpeed'],previous_ao=a['ao']))
                delta=a['OutdoorVfdSpeed']-z['OutdoorVfdSpeed']
                if delta>0 and a['OutdoorVfdOn'] and z['OutdoorVfdOn']:
                    steps30.append(dict(t=z['t'],delta10=delta))
            q['minimum30_off_edges']=edge30;q['minimum30_unload_steps']=steps30
            q['checks']['minimum30_unload_reaches_minimum_before_off']=decline30.get('predicate_met',False) and bool(edge30) and all(e['previous_speed10']<=310 for e in edge30)
            rate30=sum(e['delta10'] for e in steps30[1:])/10/(steps30[-1]['t']-steps30[0]['t']) if len(steps30)>=5 else None
            q['minimum30_unload_rate_Hz_per_s']=rate30
            q['checks']['minimum30_unload_1Hz_per_s']=rate30 is not None and abs(rate30-1)<=.15 and all(e['delta10']==10 for e in steps30)
        all_samples=[s for point in q['points'] for s in point['samples']]
        decline_edges=[]
        for a,z in zip(unload['samples'],unload['samples'][1:]):
            delta=a['OutdoorVfdSpeed']-z['OutdoorVfdSpeed']
            if delta>0 and a['OutdoorFixedOn']==z['OutdoorFixedOn'] and a['OutdoorVfdOn'] and z['OutdoorVfdOn']:
                decline_edges.append(dict(t=z['t'],fixed=z['OutdoorFixedOn'],delta10=delta))
        q['unload_edges']=decline_edges;q['measured_unload_rates_Hz_per_s']={}
        for fixed in ((0,1) if pair[1]==4 else (0,)):
            selected=[e for e in decline_edges if e['fixed']==fixed]
            rate=(sum(e['delta10'] for e in selected[1:])/10/(selected[-1]['t']-selected[0]['t'])) if len(selected)>=5 else None
            q['measured_unload_rates_Hz_per_s'][str(fixed)]=rate
            q['checks']['unload_1Hz_per_s_fixed_'+str(fixed)]=rate is not None and abs(rate-1)<=0.15
            q['checks']['unload_step_1Hz_fixed_'+str(fixed)]=len(selected)>=5 and all(e['delta10']==10 for e in selected)
        q['checks']['frequency_bounds']=all(s['OutdoorVfdSpeed']==0 or 100<=s['OutdoorVfdSpeed']<=400 for s in all_samples)
        # Sampled speed and AO reads are separate; exclude a sample straddling a
        # frequency edge when comparing their fixed0-50Hz scaling.
        scale=[]
        for a,z in zip(all_samples,all_samples[1:]):
            if a['OutdoorVfdSpeed']==z['OutdoorVfdSpeed']:scale.append(z['ao']==2*z['OutdoorVfdSpeed'])
        q['checks']['software_AO_fixed_50Hz_scaling']=bool(scale) and all(scale)
        q['passed']=all(q['checks'].values());save()
        print('VFD TARGETED RESULT',pair,q['checks'],flush=True)
    except BaseException:q['error']=traceback.format_exc();save();raise
    finally:
        try:
            b.stop()
            for ch in range(2):
                if 2684+12*ch in original:span(ch,g.signed16(original[2684+12*ch]),g.signed16(original[2685+12*ch]))
            q['ai_restore_verified']=all(b.rd(a)[0]==v==b.ot.read16(p+2*(302+a-2680)) for a,v in original.items())
            assert q['ai_restore_verified']
        finally:
            try:b.finish()
            finally:q['restored']=b.log.get('restored',False);q['finished']=g.now();save()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('pair',choices=('12','22','24'))
    parser.add_argument('--minimum30-only',action='store_true')
    args=parser.parse_args();pair=tuple(map(int,args.pair))
    try:run(pair,args.minimum30_only)
    finally:g.audit_module.audit('after_vfd_'+''.join(map(str,pair)),True)
