"""Natural elapsed defrost qualification; acquisition inputs, never timer/state writes."""
from bench_remaining_outdoor_20261111 import *


def run(kind):
    b=current_bench_class()('remaining_defrost_qualification_'+kind);inp=None
    e=b.log['remaining_functional']=dict(kind='defrost_qualification_'+kind,cases=[],
        scope='Ordinary330 heat, raw NTC inputs, actual15/20-minute gap; BENCH outputs and recovery, not physical terminals or formal recovery timing')
    try:
        b.setup(1);b.config(HEAT)
        b.config({1392:5,1393:65516,1394:100,1395:15,1396:15,
                  1389:150,1390:20,1391:2,1398:4,1399:3})
        b.temperature(0,220);b.reset_faults();b.attach_extra()
        inp=Inputs(b,e)
        inp.temperatures({0:150 if kind=='timed' else 100,1:100,2:100})
        b.start()

        def enrich(s):
            s['owner330']=b.extra[1][1].target.read8(b.sy['PSC316DefrostOwner'][0])
            return s

        def wait(label,predicate,seconds,row):
            end=time.monotonic()+seconds;heartbeat=0
            while time.monotonic()<end:
                s=enrich(inp.sample());row.setdefault('samples',[]).append(s)
                if predicate(s):row[label]=s;b.save();return s
                if time.monotonic()-heartbeat>25:
                    heartbeat=time.monotonic();b.save()
                    print('DEFROST QUALIFY',kind,label,s.get('DefGapCount'),s.get('CompRunTime'),s.get('PSC316DefrostState'),flush=True)
            raise TimeoutError(label)

        def duration(label,seconds):
            row=dict(id='O-DEFROST-016' if kind=='timed' else 'O-DEFROST-012',
                     label=label,samples=[])
            e['cases'].append(row)
            active=wait('actual_active_for_timeout',lambda s:s.get('PSC316DefrostState')==[1],35,row)
            start=active['t'];counter=active.get('PSC316DefrostRunTime',[0,0])
            ended=wait('actual_timeout_recovery',lambda s:s.get('PSC316DefrostState')==[2],seconds+35,row)
            maximum=[max(s.get('PSC316DefrostRunTime',[0,0])[i] for s in row['samples']) for i in range(2)]
            eligible=[i for i in range(2) if any(s['output'][i] for s in row['samples'])]
            row.update(final=ended,expected_seconds=seconds,observed_from_active_s=ended['t']-start,
                       starting_counters=counter,maximum_actual_counters=maximum,
                       passed=bool(eligible) and all(seconds-1<=maximum[i]<=seconds+1 for i in eligible)
                           and ended['output'][:2]==[0,0],finished=now(),
                       limit='Natural duration from actual output/runtime, BENCH common recovery5s only; formal60s, strict preceding-second boundaries and unspecified0/4/6C branches separate')
            wait('owner_and_common_recovery_clear',lambda s:s.get('PSC316DefrostState')==[0] and s['owner330']==0,55,row)
            b.save()

        pre={}
        wait('both_healthy_heating',lambda s:s['output'][:2]==[1,1] and not any(s['alarms']),210,pre)
        e['precondition']=pre
        if kind=='timed':
            with inp.values.get_lock():inp.values[5]=0
            e['raw_fault_input']=dict(channel=5,raw=0,at=now(),t=time.monotonic())
            wait('nonambient_fault_and_healthy_peer',lambda s:s['alarms'][17]==1 and s['output'][:2]==[0,1],40,pre)
            wait('actual20minute_gap',lambda s:s.get('DefGapCount',[0,0])[1]>=1200 and
                 s.get('CompRunTime',[0,0])[1]>=300,1350,pre)
            for label,temp in (('above15',151),('equal15',150)):
                row=inp.point('O-DEFROST-015',label,temp,12,allow_fault=True)
                # Internal state 1 means defrost; published phase 8 is a
                # separate interface. Do not compare internal RAM with 8.
                row['passed']=not any(q.get('PSC316DefrostState')==[1] for q in row['samples'])
            row=dict(id='O-DEFROST-015',label='12C_with15C_setting_no_added60s',samples=[])
            e['cases'].append(row);issued=inp.temperatures({0:120})
            s=wait('timed_request_or_active',lambda s:s['t']>=issued and signed16(s['params']['1422'])==120 and
                   (s['params']['1421'] in (1,5,8) or s.get('PSC316DefrostState')==[1]),95,row)
            row.update(final=s,first_observed_after_input_s=s['t']-issued,
                       passed=s['t']-issued<60,finished=now())
            row['limit']='Sub60s observation establishes absence of an added60s gate only for this eligible NTC5 fault case'
            evidence=dict(id='O-DEFROST-014',label='NTC5_timed_fallback_other_system_healthy',final=s,
                passed=s['alarms'][17]==1 and s['output'][0]==0,finished=now())
            e['cases'].append(evidence)
            duration('timed12C_set2minutes_reduces_to60seconds',60)
        elif kind=='negative':
            qualified=wait('negative_case_real_gap_qualified',lambda s:all(q>=900 for q in s.get('DefGapCount',[0,0])[:2])
                           and all(q>=300 for q in s.get('CompRunTime',[0,0])[:2]),1100,pre)
            row=dict(id='O-DEFROST-012',label='normal_negative_ambient_natural_entrance',samples=[])
            e['cases'].append(row)
            issued=inp.temperatures({0:-1,1:-150,2:-150})
            s=wait('negative_actual_defrost',lambda s:s['t']>=issued and s.get('PSC316DefrostState')==[1],120,row)
            row.update(final=s,passed=True,finished=now(),limit='Negative0.1C only; exactly0C is an unspecified boundary retained separately')
            duration('normal_negative_ambient_set3minutes',180)
        else:
            qualified=wait('actual15minute_gap',lambda s:all(q>=900 for q in s.get('DefGapCount',[0,0])[:2]) and
                 all(q>=300 for q in s.get('CompRunTime',[0,0])[:2]),1100,pre)
            e['cases'].append(dict(id='O-DEFROST-004',label='actual_gap_and_runtime_qualified_readback',
                final=qualified,passed=True,finished=now(),limit='Actual accumulated counters may include earlier healthy running; strict preceding-second entrance boundaries remain separate'))
            # Environmental10C blocks entry while the fin counter is exercised.
            fin=dict(id='O-DEFROST-003',label='fin29s_break_then31s_while_environment_blocks_entry',samples=[])
            e['cases'].append(fin)
            for temp,seconds in ((-21,28),(-20,2),(-21,32)):
                at=inp.temperatures({1:temp,2:100});end=time.monotonic()+seconds
                while time.monotonic()<end:
                    s=enrich(inp.sample(at));fin['samples'].append(s)
                fin.setdefault('segment_ends',[]).append(s)
            fin.update(final=s,finished=now())
            fin['limit']='Input continuity and counter trace only; environmental gate intentionally blocks independent entrance acceptance'
            diff=dict(id='O-DEFROST-005',label='equal_and_below10C_difference_block_normal_entrance',samples=[])
            e['cases'].append(diff)
            # Both temperatures are valid and fin<-2C. After real60s ambient
            # qualification, equality100 and below99 differ only in this gate.
            for temp,seconds in ((-30,66),(-29,8)):
                at=inp.temperatures({0:70,1:temp,2:100});end=time.monotonic()+seconds
                while time.monotonic()<end:
                    s=enrich(inp.sample(at));diff['samples'].append(s)
                diff.setdefault('segment_ends',[]).append(s)
            diff.update(final=s,passed=all(q.get('PSC316DefrostState')==[0] for q in diff['samples']),finished=now(),
                limit='Equality/below exclusion only; subsequent environment case supplies a larger-than threshold entrance, not an isolated10.1C boundary')
            at=inp.temperatures({0:100})
            wait('reset_environment_after_difference',lambda s:s['t']>=at and signed16(s['params']['1422'])==100
                 and s.get('NormalEnvLowCount')==[0],12,diff)
            # A much colder fin supplies the required temperature difference.
            inp.temperatures({1:-60,2:100})
            env=dict(id='O-DEFROST-002',label='ambient59s_break_then60s_real_gap_qualified',samples=[])
            e['cases'].append(env)
            at=inp.temperatures({0:99});end=time.monotonic()+58
            while time.monotonic()<end:
                s=enrich(inp.sample(at));env['samples'].append(s)
                if s.get('PSC316DefrostState')==[1]:env['early_active_seen']=True
            at=inp.temperatures({0:100})
            wait('environment_reset',lambda s:s['t']>=at and signed16(s['params']['1422'])==100 and
                 s.get('NormalEnvLowCount')==[0],12,env)
            at=inp.temperatures({0:99});start=None;end=time.monotonic()+120
            while time.monotonic()<end:
                s=enrich(inp.sample(at));env['samples'].append(s)
                if signed16(s['params']['1422'])==99 and start is None:start=s['t']
                if s.get('PSC316DefrostState')==[1]:
                    env.update(final=s,observed_qualify_s=s['t']-start,
                        passed=not env.get('early_active_seen') and s['t']-start>=58,finished=now());break
            else:env.update(passed=False,error='no actual defrost after continuous environment qualification',finished=now())
            if env.get('passed'):duration('normal_positive_ambient_set4minutes',240)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=('timed','normal','negative'));run(p.parse_args().kind)
