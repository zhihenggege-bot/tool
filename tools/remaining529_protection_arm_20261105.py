"""Linked-image input filtering, protection scopes and eight coil timer tests.

Emulator only. Simulated GPIO/RAM inputs and time do not qualify a board test.
Keep failures and fixture issues in the JSON instead of stopping the matrix.
"""
import json
import traceback
from remaining529_offline_matrix_20261105 import init, ck, checks, cases, D


def reset(f):
    f.p(524, 1)
    f.call('ErrorReset')
    f.p(524, 0)
    f.call('ErrorReset')


def protections():
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        for kind, start, var, flag in (
            ('phase', 1, 'X00_En', 911),
            ('remote', 7, 'X_02', None),
            ('supply overload', 13, 'X03_En', 601),
            ('filter', 19, 'X_05', 909),
            ('valve', 25, 'X04_En', 605),
            ('fire', 31, 'X01_En', 605),
        ):
            for mode in range(6):
                cid = f'T05-{start+mode:03d}'
                f = init(profile, mode)
                f.var('uc100ms', 1)
                f.var('uc1s', 0)
                f.p(510, 250)
                for m in range(1, 5):
                    for c in range(2):
                        f.field(True, m, 'CompControl', c, 1)
                if kind == 'remote':
                    f.var(var, 0)
                    for _ in range(29):
                        f.call('BoardErrAction')
                    ck(cid, profile+' before 3s', f.var('RemoteInterlockStopFlag', width=1), 0)
                    f.call('BoardErrAction')
                    ck(cid, profile+' 3s normal-stop request', [f.var('RemoteInterlockStopFlag', width=1), f.p(709)], [1, 3])
                    f.var(var, 1)
                    f.call('BoardErrAction')
                    ck(cid, profile+' input return releases stop without reset', f.var('RemoteInterlockStopFlag', width=1), 0)
                    continue
                if kind == 'filter':
                    f.var('uc1s', 1)
                    f.var(var, 1)
                    for _ in range(14):
                        f.call('BoardErrAction')
                    ck(cid, profile+' 14s no filter alarm', f.p(flag), 0)
                    f.call('BoardErrAction')
                    ck(cid, profile+' 15s filter alarm only', [f.p(flag), f.p(710), f.p(709)], [1, 0, 2])
                else:
                    f.var(var, 1)
                    f.call('BoardErrAction')
                    ck(cid, profile+' latched alarm', f.p(flag), 1)
                    ck(cid, profile+' clears all outdoor requests',
                       [f.field(True,m,'CompControl',c) for m in range(1,5) for c in range(2)], [0]*8)
                    ck(cid, profile+' stop classification', f.p(710), 1)
                f.var(var, 0)
                f.call('BoardErrAction')
                ck(cid, profile+' input restoration alone keeps latch', f.p(flag), 1)
                reset(f)
                f.call('BoardErrAction')
                ck(cid, profile+' healthy reset clears latch', f.p(flag), 0)


def input_filter():
    for profile in ('PRODUCTION', 'BENCH_ONLY_3S'):
        for ch, start in ((0,1),(1,31),(3,13),(4,25)):
            f=init(profile)
            f.call('InputStartCheck')
            f.var('uc100ms', 1)
            # Active-high polarity and emulated physical input array.
            f.p(155+ch, 1)
            f.var('input',1,ch,1)
            for _ in range(29):
                f.call('DI_Points_Process')
            for mode in range(6):
                ck(f'T05-{start+mode:03d}', profile+' common DI filter not before 2.9s', f.var(f'X0{ch}_En',width=1),0)
            f.var('input',0,ch,1)
            f.call('DI_Points_Process')
            ck(f'T05-{start:03d}',profile+' pulse interruption clears count',f.var(f'X0{ch}_Cnt',width=2),0)
            f.var('input',1,ch,1)
            for _ in range(31):
                f.call('DI_Points_Process')
            ck(f'T05-{start:03d}',profile+' DI filter asserted by 3.1s scan',f.var(f'X0{ch}_En',width=1),1)


def coils():
    # B1/B2 retain legacy display aliases 514/517, not adjacent 518/519.
    temps=(515,516,514,517,520,521,522,523)
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for circuit in range(8):
            cid=f'T15-{circuit+1:03d}'
            f=init(profile)
            for reg in temps:
                f.p(reg,100)
            for a,v in {110:5,111:-20,112:50,114:2,510:250}.items():
                f.p(a,v)
            f.var('uc1s',1)
            f.p(temps[circuit],-21)
            for _ in range(299):
                f.call('BoardErrAction')
            ck(cid,profile+' 299s no low trip',f.p(640+circuit),0)
            f.call('BoardErrAction')
            ck(cid,profile+' 300s only matching circuit trips',[f.p(640+i) for i in range(8)],[int(i==circuit) for i in range(8)])
            ck(cid,profile+' low trip blocks matching load',f.call('CompCanLoad',circuit//2+1,circuit%2),0)
            f.p(temps[circuit],50)
            for _ in range(119):
                f.call('BoardErrAction')
            ck(cid,profile+' 119s still inhibited',f.p(640+circuit),1)
            f.p(temps[circuit],49)
            f.call('BoardErrAction')
            f.p(temps[circuit],50)
            for _ in range(119):
                f.call('BoardErrAction')
            ck(cid,profile+' interrupted recovery requires full new interval',f.p(640+circuit),1)
            f.call('BoardErrAction')
            ck(cid,profile+' 120s at release threshold clears fault',f.p(640+circuit),0)


def main():
    errors=[]
    for fn in (protections,input_filter,coils):
        print('START',fn.__name__,flush=True)
        try:
            fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    report={'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors}
    (D/'remaining529_protection_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),'cases',len(checks),'checks','mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)


if __name__=='__main__':
    main()
