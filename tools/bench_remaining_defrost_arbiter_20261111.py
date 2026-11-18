"""Two actual boards qualify naturally,330 alone arbitrates defrost ownership."""
from bench_remaining_outdoor_20261111 import *
from types import SimpleNamespace


def run():
    b=current_bench_class()('remaining_two_board_natural_defrost');fixtures=[];proxy=None
    e=b.log['remaining_functional']=dict(kind='two_board_natural_defrost_arbiter',cases=[],
        scope='Both installed316s receive rawNTC acquisition inputs and actual15minute elapsed qualification; normal330 Owner/grant remains read-only; BENCH5s common recovery and software feedback, no formal60s or physical terminals')
    row=dict(id='O-DEFROST-017',label='both_boards_natural_requests_one_owner',samples=[])
    e['cases'].append(row)

    def sample():
        states=[f.sample() for f in fixtures]
        it=b.extra[1][1].target
        s=dict(at=now(),t=time.monotonic(),boards=states,
            owner=it.read8(b.sy['PSC316DefrostOwner'][0]),
            mirrors=[b.rd(1550,2),b.rd(1620,2)])
        row['samples'].append(s);return s

    def wait(label,predicate,seconds):
        end=time.monotonic()+seconds;heartbeat=0
        while time.monotonic()<end:
            paused();s=sample()
            assert not any(any(q['alarms']) for q in s['boards']),('healthy natural arbiter precondition lost',s)
            if predicate(s):row[label]=s;b.save();return s
            if time.monotonic()-heartbeat>25:
                heartbeat=time.monotonic();b.save()
                print('NATURAL ARBITER',label,s['owner'],[q.get('PSC316DefrostState') for q in s['boards']],flush=True)
        raise TimeoutError(label)

    try:
        b.setup(1);b.config(HEAT)
        b.config({1392:5,1393:65516,1394:100,1395:15,1396:15,1398:2,1399:2})
        b.temperature(0,220);b.reset_faults();b.attach_extra()
        board,session,sy=b.extra[0]
        proxy=SimpleNamespace(outss=session,ot=session.target,outsy=sy,save=b.save,_cleaning_up=False)
        fixtures.append(Inputs(b,e))
        fixtures.append(Inputs(proxy,e,board=board))
        for f in fixtures:f.temperatures({0:100,1:100,2:100})
        b.start()
        wait('both_boards_real_gap_qualified',lambda s:all(q['output'][:2]==[1,1] and
             all(v>=900 for v in q.get('DefGapCount',[0,0])[:2]) and
             all(v>=300 for v in q.get('CompRunTime',[0,0])[:2]) for q in s['boards']),1350)
        row['simultaneous_input_request_at']=now()
        for f in fixtures:f.temperatures({0:99,1:-60,2:-60})
        first=wait('first_owner_and_actual_defrost',lambda s:s['owner'] in (1,2) and
                   any(q.get('PSC316DefrostState')==[1] for q in s['boards']),130)
        unit=first['owner'];other=3-unit
        end=time.monotonic()+20
        while time.monotonic()<end:sample();time.sleep(.1)
        row['no_simultaneous_active']=all(sum(q.get('PSC316DefrostState')==[1] for q in s['boards'])<=1 for s in row['samples'])
        # Finish the actual first owner using its real fin inputs. The other
        # remains cold/qualified, so330 must release then allocate the next one.
        fixtures[unit-1].temperatures({0:100,1:400,2:400})
        second=wait('second_owner_and_actual_defrost',lambda s:s['owner']==other and
                    s['boards'][other-1].get('PSC316DefrostState')==[1] and
                    s['boards'][unit-1].get('PSC316DefrostState')==[0],100)
        fixtures[other-1].temperatures({0:100,1:400,2:400})
        ended=wait('both_recovered_and_owner_clear',lambda s:s['owner']==0 and
                   all(q.get('PSC316DefrostState')==[0] for q in s['boards']),80)
        row.update(final=ended,first_owner=unit,second_owner=other,
            passed=row['no_simultaneous_active'] and all(sum(q.get('PSC316DefrostState')==[1] for q in s['boards'])<=1 for s in row['samples']),
            finished=now(),limit='Inputs were submitted consecutively before real60s ambient qualification, not wire-level simultaneous; only installed units1/2 and BENCH recovery are covered')
    except BaseException:e['error']=traceback.format_exc();row.setdefault('passed',False);b.save();raise
    finally:
        try:
            b.wr(398,0)
            for f in reversed(fixtures):f.close()
            if proxy and proxy.outss:
                board,_,sy=b.extra[0];b.extra[0]=(board,proxy.outss,sy)
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
