"""Current-image hardware tests; mutate only test inputs/config, never firmware.

Use one action at a time. Every action saves its evidence and restores settings.
"""
from joint_v1056_context_20261110 import *
import argparse
import struct
from remaining529_manual_defrost_input_20261105 import manual_defrost
CurrentBench = current_bench_class()
import continuous_special_stages_v1055_20261109 as special
special.PAUSE=DAY/'pause.request'


def parameters():
    b=CurrentBench('fixed_minimum_frequency')
    e=dict(ids=['O-PARAM-008'],started=now(),points=[],scope='Initialized table and normal330 gateway writes; existing EEPROM defaults not erased')
    b.log['retest']=e;b.save()
    try:
        assert loads_off(b.snapshot('stopped minimum frequency'))
        e['table']=[b.ot.read16(b.outsy[n][0]+177*2) for n in ('Parameter_min','Parameter_def','Parameter_max')]
        assert e['table']==[0,5,30],e['table']
        for v in (0,5,30):
            b.gateway(1842,v)
            samples=[];began=time.monotonic()
            while time.monotonic()-began<3:
                p=b.ot.read16(b.outsy['Parameter'][0]+177*2)
                r=dict(at=now(),requested=v,mirror=b.rd(1842)[0],destination=p,diag=b.rd(1872,6))
                samples.append(r);assert p==r['mirror']==v,r;time.sleep(.25)
            e['points'].append(dict(requested=v,samples=samples));b.save()
            print('MINFREQ PASS',v,flush=True)
        e['status']='软件子范围通过：参数表及0/5/30Hz正常网关写入回读；保存/端子另验'
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def emergency():
    b=CurrentBench('fixed_emergency_defrost')
    e=dict(ids=['O-DEFROST-020','T16-005'],started=now(),samples=[])
    b.log['retest']=e;b.save()
    try:
        b.prepare();b.attach_extra()
        e['before']=b.detailed('defrost8 before emergency')
        b.wr(156,1-b.polarities[156]);began=time.monotonic();cleared=None
        while time.monotonic()-began<18:
            s=b.detailed('fire urgent stop, heating selection unchanged');e['samples'].append(s)
            indoor=next(x for x in s['direct'] if x['board']=='330')
            outdoor=next(x for x in s['direct'] if x['board']=='316_WJ1')
            good=s['state'][9]==0 and loads_off(s) and s['phase']==[0,0] and outdoor['PSC316DefrostState']==[0] and indoor['PSC316DefrostOwner']==[0] and not any(outdoor['output'])
            if good and cleared is None:cleared=time.monotonic()-began
            if cleared is not None:assert good,('cleared lifecycle reentered during emergency',s)
            assert time.monotonic()-began<13 or cleared is not None,('emergency did not abort',s)
            b.save();time.sleep(.2)
        e['clear_after_s']=cleared;assert cleared is not None
        # Remove the emergency source and reset normally, without switching to
        # cooling to clear defrost (the old workaround is deliberately absent).
        b.wr(156,b.polarities[156]);b.reset_faults()
        began=time.monotonic();e['after_release']=[]
        while time.monotonic()-began<5:
            s=b.detailed('emergency released, no old defrost resumed');e['after_release'].append(s)
            assert s['phase']==[0,0] and s['outdoor_comp']==[0,0],s
            time.sleep(.25)
        e['status']='软件子范围通过：急停关负载并清本轮，330释放占用；解除后无旧化霜续跑'
        print('EMERGENCY PASS clear_after_s',cleared,flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def fans():
    b=CurrentBench('fixed_fan_minimum_stop')
    e=dict(started=now(),pairs=[],scope='Normal316 demand inputs while330 stopped; physical-fan software output edges; no runtime/counter/output writes')
    b.log['retest']=e;b.save()
    def request(v):
        for a in (1400,1403):b.ot.write16(b.outsy['Parameter'][0]+2*a,v)
        b.ot.flush()
    def read():
        return dict(at=now(),t=time.monotonic(),tick=b.ot.read32(b.outsy['Systick_1ms'][0]),
                    output=list(b.ot.read_memory_block8(b.outsy['output'][0],8)),
                    params={str(a):b.ot.read16(b.outsy['Parameter'][0]+2*a) for a in (1,165,166,179,180,1400,1403,1406,1501)})
    def active(s,typ):return [bool(s['output'][2] or (s['output'][7] if typ==0 else 0)),bool(s['output'][3])]
    def wait(label,typ,pred,timeout,r):
        began=time.monotonic()
        while True:
            s=read();r.setdefault(label,[]).append(s)
            if pred(s):return s
            assert time.monotonic()-began<timeout,(label,s)
            time.sleep(.08)
    try:
        b.setup(0);b.config({1333:200,1334:100,1337:10,1338:30})
        for pos,(unit,typ) in enumerate(((0,0),(0,1),(1,2),(1,3),(2,2),(2,4))):
            r=dict(ids=[f'O-FANTIME-{pos*4+1:03d}'],unit_type=unit,fan_type=typ,started=now());e['pairs'].append(r)
            request(0);wait('off_before_config',typ,lambda s:not any(active(s,typ)),60,r)
            b.gateway(1830,unit);b.gateway(1831,typ);time.sleep(.5)
            assert b.ot.read16(b.outsy['Parameter'][0]+360)==30
            request(1);wait('first_start',typ,lambda s:any(active(s,typ)),45,r)
            began=time.monotonic()
            while time.monotonic()-began<11:r.setdefault('first_run',[]).append(read());time.sleep(.2)
            request(0);last_on=[None,None];off_edge=[None,None];began=time.monotonic()
            while True:
                s=read();r.setdefault('stop_samples',[]).append(s);on=active(s,typ)
                for i in range(2):
                    if on[i]:last_on[i]=s['t'];off_edge[i]=None
                    elif last_on[i] is not None and off_edge[i] is None:off_edge[i]=s['t']
                if not any(on):break
                assert time.monotonic()-began<60,('fan stop failed',s)
                time.sleep(.08)
            assert any(v is not None for v in off_edge),'Need at least one same-fan off edge'
            time.sleep(1);request(1);began=time.monotonic();restarts={}
            while time.monotonic()-began<38:
                s=read();r.setdefault('restart_samples',[]).append(s);on=active(s,typ)
                for i in range(2):
                    if on[i] and off_edge[i] is not None and i not in restarts:
                        elapsed=s['t']-off_edge[i];restarts[i]=elapsed
                        # Polling brackets the off edge; tolerate only the
                        # measurement interval, never the old1..4s restart.
                        assert elapsed>=29.6,('same fan restarted before30s',i,elapsed,s)
                time.sleep(.08)
            assert restarts,('same fan never restarted',off_edge,r)
            r.update(status='软件子范围通过：同路停机约30秒后重启',off_edges=off_edge,restart_off_seconds=restarts,finished=now());b.save()
            print('FAN MINSTOP PASS',unit,typ,restarts,flush=True)
            request(0);wait('final_off',typ,lambda s:not any(active(s,typ)),60,r)
        e['status']='six_pairs_completed_cooling_prestart';b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            request(0)
            if e['pairs']:wait('cleanup_fans_off',e['pairs'][-1]['fan_type'],lambda s:not any(active(s,e['pairs'][-1]['fan_type'])),60,e)
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def timed(target_unit=1):
    # Wait the actual minimum legal20-minute interval, keeping ambient ABOVE
    # the configured15C threshold. Only then cross to12C, proving absence of
    # both the obsolete10C gate and an added60-second temperature hold.
    import multiprocessing as mp
    import math,queue
    from joint_timed_defrost_20261110 import worker
    b=CurrentBench('fixed_timed_defrost15');proc=None;stop=None;values=None
    e=dict(ids=['O-DEFROST-015','O-DEFROST-014','O-DEFROST-016'],started=now(),target_unit=target_unit,
           diagnostics=[],snapshots=[],input_events=[],scope='Naturally accumulated20-minute gap (may include preceding actual heating); rawNTC0/NTC5 input simulation; no timer/phase/output writes; >6C duration branch only')
    b.log['retest']=e;b.save()
    try:
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
            315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,428:0,
            347:100,348:1,349:0,346:0,320:0,245:1,247:0,329:2,330:0,331:0,
            365:1,372:350,10:500,12:500,1389:150,1390:20,1391:2})
        b.temperature(0,220);b.reset_faults()
        b.outss.close();b.outss=None
        ctx=mp.get_context('spawn');values=ctx.Array('i',[-1]*8);stop=ctx.Event();out=ctx.Queue()
        proc=ctx.Process(target=worker,args=(BOARDS[target_unit-1],b.outsy,values,stop,out),daemon=True);proc.start()
        kind,ready=out.get(timeout=30);assert kind=='ready',(kind,ready)
        def inputs(temp,fault):
            val=temp-ready['environment_calibration'];idx=math.floor(val/10)+50;frac=val/10-(idx-50)
            resistance=ready['table'][idx]+frac*(ready['table'][idx+1]-ready['table'][idx])
            raw=round(2.048*resistance/(5.1+resistance)/.0000625)
            with values.get_lock():values[0]=raw;values[5]=0 if fault else -1
            e['input_events'].append(dict(at=now(),t=time.monotonic(),temp10=temp,nonambient_ntc5_fault=fault,raw_adc0=raw));b.save()
        inputs(160,False);b.start();began=time.monotonic();last_print=began;last_snapshot=0;fault=False;crossed=None;active=None
        while True:
            try:kind,row=out.get(timeout=3)
            except queue.Empty:assert proc.is_alive(),'input worker stopped';continue
            if kind=='error':raise RuntimeError(row)
            if kind!='diagnostic':continue
            e['diagnostics'].append(row);p=row['params']
            if time.monotonic()-last_snapshot>=5:
                z=b.snapshot('normal indoor demand and defrost arbitration')
                z['defrost_mirrors']=[b.rd(1550,2),b.rd(1620,2)]
                e['snapshots'].append(z);last_snapshot=time.monotonic()
            if not fault and row['output'][:2]==[1,1] and p['617']==0:
                e['healthy_before_fault']=row;inputs(160,True);fault=True
            if crossed is None and fault and row['DefGapCount'][1]>=1200 and p['617']==1 and row['output'][1]:
                assert signed16(p['1422'])==160 and p['1421']==0,('requested above configured15C',row)
                e['interval_met_above_threshold']=row;inputs(120,True);crossed=time.monotonic()
            if crossed is not None and 'first_request' not in e and p['1421'] in (1,5,8):
                dt=row['t']-e['input_events'][-1]['t']
                assert dt<20,('first request unexpectedly delayed',dt,row)
                e['first_request_after_threshold_s']=dt;e['first_request']=row
            if crossed is not None and active is None and p['1421']==8:
                active=row['t'];e['active']=row
            if crossed is not None and active is None:
                assert time.monotonic()-crossed<120,('330 permit/active-entry timeout, distinct from temperature gate',row)
            if active is not None and p['1421']==7:
                e['recovery']=row;e['active_to_recovery_s']=row['t']-active
                assert 57<=e['active_to_recovery_s']<=65,('timed2min above6C must use1min',e['active_to_recovery_s'])
                e['status']='软件子范围通过：自然累计20分钟间隔（可含前序实际制热）后16→12℃在20秒内申请；无固定10℃或60秒温度保持；>6℃按设定2分钟减1分钟运行'
                b.save();print('TIMED15 PASS',e['first_request_after_threshold_s'],e['active_to_recovery_s'],flush=True);break
            assert time.monotonic()-began<1440,('timed test deadline',row)
            if not fault:assert time.monotonic()-began<180,('healthy heating precondition failed',row)
            if time.monotonic()-last_print>=25:
                print('TIMED WAIT',round(time.monotonic()-began),'env',signed16(p['1422']),'gap',row['DefGapCount'][:2],'phase',p['1420'],p['1421'],flush=True)
                last_print=time.monotonic();b.save()
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if proc:
                # Keep the fault input until the actual lifecycle has ended.
                # Releasing it during pending1 could change the *entry* to
                # normal defrost and invalidate the timed-duration fixture.
                cleanup_started=time.monotonic();cancelled=False;urgent=False
                while proc.is_alive():
                    phase=b.rd(1550+(target_unit-1)*70,2)
                    if any(v==8 for v in phase) and not cancelled:
                        b.wr(540,target_unit);manual_defrost(b,False);cancelled=True
                    if all(v in (0,6) for v in phase) and b.rd(709)[0]==0:break
                    if time.monotonic()-cleanup_started>120 and not urgent:
                        e['cleanup_emergency_fallback']=dict(at=now(),reason='Normal cleanup did not finish; valid fire input, never a lifecycle/output write')
                        b.wr(156,1-b.polarities[156]);urgent=True
                    assert time.monotonic()-cleanup_started<145,('cleanup lifecycle timeout',phase)
                    time.sleep(.3)
                with values.get_lock():
                    for i in range(8):values[i]=-1
                time.sleep(1);stop.set();proc.join(10);assert not proc.is_alive();e['worker_exitcode']=proc.exitcode
            b.outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            b.outss.open();b.ot=b.outss.target;time.sleep(2);b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('parameters','emergency','fans','timed','timed2','allocation','refrigerant','da8','ntc','heatfans','coils'))
    a=parser.parse_args()
    if a.action=='timed2':timed(2);return
    if a.action in ('parameters','emergency','fans','timed'):globals()[a.action]();return
    if a.action in ('allocation','refrigerant','da8'):
        import joint_indoor_followups_20261110 as m
        m.TodayBench=CurrentBench;getattr(m,a.action)();return
    name={'ntc':'joint_outdoor_ntc_protection_20261110','heatfans':'joint_outdoor_heatfans_20261110','coils':'joint_indoor_coils_20261110'}[a.action]
    m=__import__(name);m.TodayBench=CurrentBench
    if a.action=='coils':
        m.DAY=DAY
        def record_current(self,cid,passed,actual,entry):
            return m.CoilBench.record_local(self,cid,passed,actual.replace('V10.55','V10.56'),entry)
        m.matrix.CheckedBench=type('CurrentCoilBench',(CurrentBench,),{'record_local':record_current})
        m.matrix.RawNtcInput=m.ProcessNtcInput;m.matrix.RESULTS=DAY/'coil_case_results.json'
        dump(m.matrix.RESULTS,{f'T15-{i:03d}':{} for i in range(1,5)});m.matrix.run()
    else:m.run()


if __name__=='__main__':main()
