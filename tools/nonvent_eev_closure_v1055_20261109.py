"""Non-ventilation EEV closure: genuine commands and input polarity only.

Read EEV state from the selected AXF; never write valve position, demand,
compressor status, PID history, runtime counters, or protection timers.
"""
from v1055_bench_context_20261109 import *
from nonvent_defrost_v1055_20261109 import DefrostBench, paused, restored_latest
import struct, subprocess, sys


def run(kind):
    b=DefrostBench('eev_closure_'+kind)
    cid={'normal':'T12-028','emergency':'T12-029','disabled':'T12-030','fault':'T10-016'}[kind]
    e=dict(passed=False,kind=kind,trace=[],snapshots=[],
        scope='BENCH software valve state and real clock; no pulse/terminal/mechanical travel measurement')
    b.log['cases'][cid]=e;b.save()
    try:
        b.swd=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        b.swd.open();t=b.swd.target
        def read():
            for _ in range(20):
                closing=list(t.read_memory_block8(b.sy['EEVSpecClosing'][0],8))
                target=list(struct.unpack('<8i',bytes(t.read_memory_block8(b.sy['EEVSpecCloseTarget'][0],32))))
                values=list(struct.unpack('<16h',bytes(t.read_memory_block8(b.sy['Parameter'][0]+1145*2,32))))
                if closing==list(t.read_memory_block8(b.sy['EEVSpecClosing'][0],8)) and target==list(struct.unpack('<8i',bytes(t.read_memory_block8(b.sy['EEVSpecCloseTarget'][0],32)))):
                    return dict(t=time.monotonic(),at=now(),closing=closing,close_target=target,new=values[:8],current=values[8:])
            raise AssertionError('Unable to read coherent EEV closure state')
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            160:250,161:250,120:20,412:1,416:100,417:1,418:0,
            315:0,320:0,346:0,245:1,247:0,329:2,330:0,331:0,
            365:1,366:50,367:50,368:1,369:1000,370:0,16:10,
            411:500,371:20,10:500,12:500})
        b.temperature(0,290);b.reset_faults();b.start()
        b.wait('EEV closure precondition four actual cooling feedback',
            lambda s:all(v==2 for pair in s['outdoor_status'] for v in pair),180)
        began=time.monotonic()
        while True:
            z=read()
            if all(z['closing'][i]==0 and z['current'][i]>=80 for i in range(4)):break
            assert time.monotonic()-began<40,('open valve precondition',z)
            time.sleep(.05)
        e['before']=z;e['trace'].append(z);e['before_status']=b.sample('established cooling before EEV closure')
        if kind=='normal':b.wr(398,0)
        elif kind=='emergency':b.wr(156,1-b.polarities[156])
        elif kind=='disabled':b.gateway(1833,1)
        else:
            addr=b.outsy['Parameter'][0]+4
            assert b.ot.read8(b.outsy['X_00'][0])==0
            b.ot.write16(addr,1-b.hp_original);b.ot.flush()
            e['stimulus']=dict(parameter=2,address=addr,width=2,value=1-b.hp_original,meaning='raw HP1 input polarity simulation')
        began=time.monotonic();heartbeat=began;snapshot_at=began;observed=set();last=z
        affected=range(4) if kind in ('normal','emergency') else (0,)
        expected_mode=2 if kind=='emergency' else 1
        while True:
            paused();z=read();e['trace'].append(z)
            for i in affected:
                if z['closing'][i]==expected_mode:observed.add(i)
            if time.monotonic()-snapshot_at>=3:
                s=b.sample('EEV closure status');e['snapshots'].append(s);snapshot_at=time.monotonic()
                if kind in ('disabled','fault') and z['current'][0]==0:
                    assert s['outdoor_comp'][0]==0,('retired compressor output not off',s)
            if time.monotonic()-heartbeat>=20:
                print('EEV CLOSURE',kind,round(time.monotonic()-began,1),z['new'][:4],z['current'][:4],flush=True)
                heartbeat=time.monotonic();b.save()
            if set(affected)<=observed and all(z['new'][i]==z['current'][i]==0 for i in affected):break
            assert time.monotonic()-began<170,('EEV closure incomplete',kind,z)
            last=z;time.sleep(.02)
        e['closed']=z;e['closing_modes_seen']=sorted(observed)
        # Compare actual target transitions, not nominal timeout alone. The
        # final remaining step can be smaller than 20.
        edges=[]
        for i in affected:
            prev=None;events=[]
            for row in e['trace']:
                if row['closing'][i]!=expected_mode:continue
                value=row['close_target'][i]
                if prev is not None and value!=prev['value']:
                    events.append(dict(before=prev['value'],after=value,delta=value-prev['value'],dt=row['t']-prev['t']))
                if prev is None or value!=prev['value']:prev=dict(value=value,t=row['t'])
            assert len(events)>=3,('too few actual closure edges',i,events)
            assert all(v['delta']==-20 or v['after']==0 and -20<=v['delta']<0 for v in events),('unexpected closure target decrement',i,events)
            timing=[v['dt'] for v in events[1:]]
            assert all(.72<=v<=1.28 for v in timing),('closure target real-second interval mismatch',i,timing)
            edges.append(dict(channel=i,events=events))
        e['edges']=edges
        # Seating offset is observable as a software position discontinuity at
        # the transition, bracketed by adjacent coherent reads. Do not call it
        # a measured motor overtravel.
        offset=10 if kind=='emergency' else 20;offsets=[]
        for i in affected:
            before=e['before'];entry=None
            for row in e['trace']:
                if row['closing'][i]==expected_mode and before['closing'][i]==0:
                    delta=row['close_target'][i]-before['current'][i]
                    entry=dict(channel=i,delta=delta,expected_offset=offset,
                        compatible=any(abs(delta-v)<=3 for v in (offset,offset-20)),before=before,after=row)
                    break
                before=row
            # A normal gateway write waits for destination acknowledgement;
            # closure can start during that wait. Never infer an initial
            # seating offset from a late sample in that subcase.
            if kind!='disabled':
                assert entry and entry['compatible'],('seating offset not established by adjacent samples',i,entry)
            offsets.append(entry)
        e['seating_offset_brackets']=offsets
        if kind in ('disabled','fault'):
            s=b.sample('one retired circuit closed, other compressors retained')
            assert s['outdoor_comp']==[0,1] and s['actual_count']==3 and all(v==2 for v in [s['outdoor_status'][0][1],*s['outdoor_status'][1]]),s
            e['other_circuits_retained']=s
            if kind=='fault':assert s['hp_alarms'][0]==1,s
        elif kind=='emergency':
            s=b.sample('emergency final state');assert s['state'][9]==0 and loads_off(s) and s['outdoor_comp']==[0,0],s
            e['stopped']=s
        else:e['stopped']=b.wait('normal final stop after EEV closure',lambda s:s['state'][9]==0 and loads_off(s),100,True)
        e['passed']=True
        seating='网关确认期间的首个超关偏移不判定' if kind=='disabled' else f'观测+{offset}软件超关偏移'
        message=f'V10.55/V12.39真实4台制冷反馈和室内阀开度先建立；{kind}输入后，'+('4路' if kind in ('normal','emergency') else '对应回路1')+f'实际软件关阀目标逐真实秒减20至0，关阀模式{expected_mode}；{seating}；目标/当前软件步数最终0。'+('其余3台制冷反馈保持。' if kind in ('disabled','fault') else '')+'原始轨迹与逐步差分留证；未测电机脉冲、机械位置或端子。'
        b.record_local(cid,True,message,e)
        if kind=='fault':b.record_local('T12-030',True,message+'仅高压故障子范围；禁用/通信另记。',e)
        records=json.loads(RESULTS.read_text('utf8'));records[cid]['inputs']='Normal command, gateway disable or raw HP polarity INPUT only; EEV state read-only';dump(RESULTS,records)
    except BaseException:e['error']=traceback.format_exc();b.log['error']=e['error'];b.save();raise
    finally:
        try:
            b.ot.write16(b.outsy['Parameter'][0]+4,b.hp_original);b.ot.flush()
            b.config({156:b.polarities[156]});b.reset_faults()
        finally:b.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after.resolve();journal=D/('nonvent_eev_closure_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],ventilation='Deferred by user');dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    assert previous.get('status')=='completed',previous
    restored_latest();q['status']='running';dump(journal,q)
    try:
        for kind in ('normal','emergency','disabled','fault'):
            paused();restored_latest();row=dict(kind=kind,started=now(),status='running');q['actions'].append(row);dump(journal,q)
            try:run(kind);row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q);restored_latest()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
            assert proc.returncode==0,(script,proc.stderr)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('NONVENT EEV CLOSURE FINISHED',journal,flush=True)


if __name__=='__main__':main()
