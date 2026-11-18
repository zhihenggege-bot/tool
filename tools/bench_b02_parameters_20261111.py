"""Stopped V10.58 check of the four-way valve source and shared/individual routes."""
from contextlib import ExitStack
import time
import traceback
from joint_v1058_context_20261111 import DAY, runtime, BOARDS, ConnectHelper, now, dump
from joint_precondition_20261110 import symbols


def run():
    evidence = DAY/('B02_parameters_'+time.strftime('%H%M%S')+'.json')
    log = dict(started=now(), cases=[])
    with ExitStack() as stack:
        c = runtime.client(); stack.callback(c.close)
        rd = lambda a,n=1: c.read_holding_registers(1,a,n)
        wr = lambda a,v: c.write_single_register(1,a,v&65535)
        assert rd(2622,18)==runtime.EXPECTED and rd(1298,2)==[3,15107]
        assert rd(398)==[0] and rd(709)==[0] and not any(rd(2598,2))
        sources = {a:rd(a)[0] for a in (41,1319,1340,1343,1344)}
        assert sources[1319]==1
        boards = []
        for board in BOARDS[:2]:
            ss = stack.enter_context(ConnectHelper.session_with_chosen_probe(unique_id=board[1], target_override=board[2],
                     options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            boards.append((ss.target,symbols(board)))
        def state(p):
            s=runtime.snap(c)
            outputs=[list(t.read_memory_block8(*sy['output'])) for t,sy in boards]
            assert rd(398)==[0] and s['state'][9]==0 and runtime.loads_off(s) and not any(map(any,outputs)),s
            return dict(at=now(), mirror=[rd(a+p-165)[0] for a in (1830,1878)],
                        actual=[t.read16(sy['Parameter'][0]+p*2) for t,sy in boards],
                        diag=[rd(a+42,6) for a in (1830,1878)],layer=rd(2598,2),outputs=outputs)
        originals={p:state(p) for p in (165,166,176,193)}
        assert all(s['actual']==s['mirror'] for s in originals.values())
        assert originals[193]['actual']==[sources[41]]*2 and originals[176]['actual']==[sources[1340]]*2
        log.update(sources=sources, original=originals); dump(evidence,log)

        def observe(row,key,p,expected,seconds=60,stable=2.0):
            start=time.monotonic(); since=None; data=row.setdefault(key,[])
            while time.monotonic()-start<seconds:
                s=state(p); data.append(s)
                good=s['actual']==s['mirror']==expected and all(d[1]!=1 for d in s['diag'])
                if good:
                    if since is None: since=time.monotonic()
                    if time.monotonic()-since>=stable: return s
                else: since=None
                time.sleep(.4)
            raise TimeoutError((key,p,expected,data[-1]))

        for cid,p,source,address,test in [('O-LINK-002',193,41,1858,60 if sources[41]!=60 else 30),
                                          ('O-LINK-001',176,1340,1841,40 if sources[1340]!=40 else 45)]:
            row=dict(id=cid, parameter=p, source=source, request=test, started=now()); log['cases'].append(row)
            dump(evidence,log)
            try:
                try: wr(address,test)
                except Exception as exc: row['shared_gateway_exception']=repr(exc)
                settled=observe(row,'shared_individual_request',p,originals[p]['actual'],stable=4)
                row['shared_diagnostic']=settled['diag'][0]
                assert rd(source)==[sources[source]]
                if p!=193: assert row['shared_diagnostic'][2]==9
                wr(source,test)
                observe(row,'shared_source_propagation',p,[test,test]); assert rd(source)==[test]
                wr(source,sources[source]); observe(row,'shared_before_individual',p,originals[p]['actual'])
                wr(1319,0); assert rd(1319)==[0]
                try: wr(address,test)
                except Exception as exc: row['independent_gateway_exception']=repr(exc)
                expected=originals[p]['actual'] if p==193 else [test,originals[p]['actual'][1]]
                observe(row,'independent_first_unit',p,expected,stable=4)
                row['status']='软件子范围通过'
            except Exception as exc:
                row.update(status='实测有待核对',error=repr(exc))
            finally:
                try:
                    if rd(1319)==[0]:
                        if state(p)['actual'][0]!=originals[p]['actual'][0]: wr(address,originals[p]['actual'][0])
                        observe(row,'restore_individual',p,originals[p]['actual'])
                        wr(1319,1)
                    wr(source,sources[source]); observe(row,'restore_shared',p,originals[p]['actual'])
                    assert all(rd(a)==[v] for a,v in sources.items())
                    row['recovery_verified']=True
                except Exception:
                    row.update(recovery_verified=False,recovery_error=traceback.format_exc())
                row['finished']=now(); dump(evidence,log)
                print('PARAM',cid,row['status'],'restored',row['recovery_verified'],flush=True)
            if not row['recovery_verified']: break
        if all(r['recovery_verified'] for r in log['cases']) and originals[166]['actual']==[1,1] and sources[1343]==0:
            row=dict(id='O-PROTECT-019',parameter=165,source=1343,request=1,started=now()); log['cases'].append(row)
            dump(evidence,log)
            try:
                wr(1343,1)
                observe(row,'invalid_pair_present',165,[1,1]); assert rd(1344)==[1]
                end=time.monotonic()+35
                while time.monotonic()<end:
                    s=state(165); row.setdefault('invalid_layer',[]).append(s)
                    if all(v&64 for v in s['layer']): break
                    time.sleep(.4)
                else: raise TimeoutError('invalid-pair layer bit did not appear')
                row['status']='软件子范围通过'
            except Exception as exc:
                row.update(status='实测有待核对',error=repr(exc))
            finally:
                try:
                    wr(1343,sources[1343]); observe(row,'restore_type',165,originals[165]['actual'])
                    end=time.monotonic()+35
                    while time.monotonic()<end:
                        s=state(165); row.setdefault('clear_layer',[]).append(s)
                        if not any(s['layer']): break
                        time.sleep(.4)
                    else: raise TimeoutError('invalid-pair layer did not clear')
                    assert all(rd(a)==[v] for a,v in sources.items())
                    wr(524,1); time.sleep(.3); wr(524,0)
                    end=time.monotonic()+18
                    while any(rd(2618,2)):
                        assert time.monotonic()<end,'latched invalid-pair fault did not clear'
                        time.sleep(.4)
                    row['recovery_verified']=True
                except Exception:
                    row.update(recovery_verified=False,recovery_error=traceback.format_exc())
                row['finished']=now(); dump(evidence,log)
                print('PARAM',row['id'],row['status'],'restored',row['recovery_verified'],flush=True)
    log['finished']=now(); dump(evidence,log); print('EVIDENCE',evidence,flush=True)


if __name__=='__main__':
    run()
