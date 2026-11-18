"""Type-I cooling fan bench curves, driven by normal330 run/config inputs.

Raw acquisition/filter fixture only; counters, outputs and control states are
read-only. Each point retains the complete trace and exact-temperature onset.
"""
from joint_v1057_context_20261110 import *
import multiprocessing as mp
import struct, math, queue

CurrentBench = current_bench_class()


def fixture(board, sy, values, stop, out):
    ss = None
    try:
        # The parent may stop consuming after its final point. Do not wait for
        # an unconsumed multiprocessing pipe to flush during worker shutdown.
        out.cancel_join_thread()
        ss = ConnectHelper.session_with_chosen_probe(unique_id=board[1], target_override=board[2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        ss.open(); t=ss.target; p=sy['Parameter'][0]
        out.put(('ready', True)); began=time.monotonic(); previous=began; longest=0; next_read=0
        while not stop.is_set():
            assert time.monotonic()-began<2400, 'fixture duration bound'
            with values.get_lock(): active={i:v for i,v in enumerate(values[:]) if v>=0}
            for ch,v in active.items():
                t.write16(sy['ADbuffer'][0]+2*ch,v)
                t.write_memory_block8(sy['NTC_Val_Filter'][0]+40*ch,list(struct.pack('<20H',*([v]*20))))
                t.write16(sy['NTC_AD'][0]+2*ch,v)
            t.flush(); nt=time.monotonic(); longest=max(longest,nt-previous); previous=nt
            if nt>=next_read:
                row=dict(at=now(),t=nt,input_gap_s=longest,
                    temperatures=[signed16(t.read16(p+2*a)) for a in (1422,1431,1432)],
                    output=list(t.read_memory_block8(sy['output'][0],8)),
                    params={str(a):t.read16(p+2*a) for a in (1400,1403,1425,1426,1501)},
                    alarms=[t.read16(p+2*a) for a in range(600,628)])
                for k in ('OutdoorTypeIHighStage','OutdoorTypeIEnvHighCount','OutdoorTypeICondHighCount',
                          'OutdoorTypeILowCount','OutdoorFanStage','OutdoorFanChangeSeconds',
                          'OutdoorFanTotalRun','OutdoorPrestartOwnsFans','OutdoorFanRunSeconds','OutdoorFanStopSeconds'):
                    if k in sy:
                        a,n=sy[k]; raw=bytes(t.read_memory_block8(a,n))
                        row[k]=list(struct.unpack('<'+'I'*(n//4),raw)) if n%4==0 else list(raw)
                out.put(('sample',row)); next_read=nt+.20; longest=0
            stop.wait(.002)
    except BaseException: out.put(('error',traceback.format_exc()))
    finally:
        if ss: ss.close()


def run(typ):
    b=CurrentBench('typeI_cooling_fan_curve_pair0_'+str(typ))
    e=dict(started=now(),ids=['O-FANCURVE-001','O-FANCURVE-002','O-FANCURVE-003'],
        type_pair=[0,typ],status='running',points=[],
        scope='330 ordinary cooling start; WJ1 raw NTC0/1/2 acquisition input fixture. Software DO and exact real-duration traces; not physical terminals or PRODUCTION acceptance.')
    b.log['fan_curves']=e; b.save(); proc=stop=values=None
    def sample(after=0):
        while True:
            try: kind,s=out.get(timeout=3)
            except queue.Empty:
                assert proc.is_alive(),'input fixture exited'; continue
            if kind=='error': raise RuntimeError(s)
            if kind=='sample' and s['t']>=after: return s
    def high(s):
        return bool(s['output'][7]) if typ==0 else bool(s['output'][2] and s['output'][3])
    def low(s):
        return bool(s['output'][2] and not s['output'][7]) if typ==0 else (sum(bool(s['output'][i]) for i in (2,3))==1)
    def point(label,temps,duration,wanted,transition_min=None,expected_systems=None):
        raw=[]
        for ch,temp in enumerate(temps):
            v=temp-cal[ch]; i=math.floor(v/10)+50; f=v/10-(i-50)
            resistance=table[i]+f*(table[i+1]-table[i]); raw.append(round(2.048*resistance/(5.1+resistance)/.0000625))
        r=dict(label=label,temperatures10=temps,raw_inputs=raw,seconds=duration,wanted=wanted,
               requested_t=time.monotonic(),at=now(),samples=[])
        e['points'].append(r); b.save()
        with values.get_lock():
            for ch,v in enumerate(raw): values[ch]=v
        exact=None; previous=None; first_transition=None
        while True:
            s=sample(r['requested_t']); r['samples'].append(s)
            assert not any(s['alarms']),('unexpected outdoor fault',label,s)
            if s['temperatures']==temps:
                if exact is None: exact=s['t']; r['first_exact_t']=exact
                dt=s['t']-exact
                actual='high' if high(s) else 'low' if low(s) else 'off/transition'
                if actual==wanted and first_transition is None: first_transition=dt
                if transition_min is not None and dt<transition_min-.9 and actual==wanted:
                    r.setdefault('early_observations',[]).append(s)
                if dt>=duration:
                    r.update(final=s,final_stage=actual,observed_exact_s=dt,
                        transition_first_seen_s=first_transition,
                        passed=actual==wanted and not r.get('early_observations'))
                    if expected_systems is not None:
                        r['passed']=r['passed'] and s['output'][:2]==expected_systems
                    break
            elif exact is not None:
                raise AssertionError(('exact input continuity interrupted',label,s['temperatures'],temps))
            assert time.monotonic()-r['requested_t']<duration+25,('input settling timeout',label,s)
        b.save(); print('FAN CURVE',typ,label,'PASS' if r['passed'] else 'OBSERVED DIFFERENCE',
            'stage',r['final_stage'],'first_s',r['transition_first_seen_s'],flush=True)
        return r
    try:
        b.setup(0); b.gateway(1830,0); b.gateway(1831,typ)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
            365:1,411:200,10:500,12:500,1331:150,1333:300,1334:150,
            1337:30,1338:30,1339:60})
        b.temperature(0,290); b.reset_faults()
        table=struct.unpack('<201f',bytes(b.ot.read_memory_block8(b.outsy['NTCtable'][0],804)))
        cal=[signed16(b.ot.read16(b.outsy['Parameter'][0]+2*(493-ch))) for ch in range(3)]
        e['settings']={str(a):b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (165,166,172,173,179,180,181)}
        assert [e['settings'][str(a)] for a in (172,173,179,180,181)]==[300,150,30,30,60]
        b.outss.close(); b.outss=None
        ctx=mp.get_context('spawn'); values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue()
        proc=ctx.Process(target=fixture,args=(BOARDS[0],b.outsy,values,stop,out),daemon=True);proc.start()
        kind,val=out.get(timeout=30);assert kind=='ready',(kind,val)
        # All initial analog values are established before submitting the indoor command.
        point('stopped_input_establishment',[240,350,350],1,'off/transition')
        b.start(); b.wait('normal indoor cooling both outdoor systems',
            lambda s:all(v==2 for pair in s['outdoor_status'] for v in pair),180)
        e['normal_indoor_start']=b.snapshot('normal330 startup, both316 cooling')
        point('initial_middle_band',[240,350,350],32,'low')
        point('condensing_equal45_no_raise',[240,450,449],8,'low')
        point('condensing_above45_5seconds',[240,451,449],19,'high',5)
        point('condensing_equal30_no_lower',[240,300,299],63,'high')
        point('low29seconds_interrupted',[240,299,299],29,'high')
        point('equal30_resets_low_hold',[240,300,299],2,'high')
        point('all_below30_full60seconds',[240,299,299],63,'low',60)
        point('ambient_equal25_no_raise',[250,350,350],32,'low')
        point('ambient_high29seconds_interrupted',[251,350,350],28,'low')
        point('ambient_equal25_resets_hold',[250,350,350],2,'low')
        point('ambient_above25_full30seconds',[251,350,350],33,'high',30)
        point('middle_band_retains_high',[240,350,350],32,'high')
        point('reset_to_low_for_single_system',[240,299,299],63,'low',60)
        # Disable via the normal330 gateway, not a forced compressor output.
        def gateway_with_worker(a,v):
            orig=b.ot; b.ot=None
            try:
                from app import Psc330MonitorApp
                m=object.__new__(Psc330MonitorApp);m.values={}
                m.read_now=lambda a,n:b.rd(a,n);m.write_single=lambda a,v:b.c.write_single_register(1,a,v & 65535)
                b.gateway_original.setdefault(a,b.rd(a)[0])
                m.write_outdoor_gateway_register(1830,a,165+a-1830,v)
            finally: b.ot=orig
        gateway_with_worker(1834,1)
        point('system2_disabled_cold_ignored',[240,451,100],34,'high',5,[1,0])
        gateway_with_worker(1834,0); gateway_with_worker(1833,1)
        point('system1_disabled_cold_ignored',[240,100,451],34,'high',None,[0,1])
        gateway_with_worker(1833,0)
        e['status']='completed_see_per_point';e['all_point_expectations']=all(r['passed'] for r in e['points']);b.save()
    except BaseException:
        e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc:
                with values.get_lock():
                    for i in range(8):values[i]=-1
                time.sleep(1); stop.set()
                until_exit=time.monotonic()+12
                while proc.is_alive() and time.monotonic()<until_exit:
                    try: out.get(timeout=.1)
                    except queue.Empty: pass
                    proc.join(.05)
                e['fixture_exitcode']=proc.exitcode
                assert not proc.is_alive() and proc.exitcode==0,'fixture failed to exit'
            if b.outss is None:
                b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
                    options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
                b.outss.open();b.ot=b.outss.target
            time.sleep(2);b.finish()
        finally:
            e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('fan_type',type=int,choices=[0,1]);run(p.parse_args().fan_type)
