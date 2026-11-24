"""Execute actual ARM code: polarity/filter/latch/reset and old control equivalence."""
import hashlib
import json
import traceback
from itertools import product
from test_defrost_lifecycle_arm import Firmware
import build_di_faults_v1076_20261124 as build

NEW = build.OUT/'PRODUCTION/PSC330_V10.76_PRODUCTION.axf'
OLD = build.OLD/'PSC330_V10.75_PRODUCTION.axf'
DI = ((1,156,'X01_En',960), (4,159,'X04_En',962), (11,395,'X13_En',964))
FAULTS = (960,962,964)
checks = []


def check(name, ok, **details):
    checks.append(dict(name=name, passed=bool(ok), **details))
    assert ok, checks[-1]


def board(image=NEW, mode=2):
    f = Firmware(image)
    f.uc.mem_map(0x22000000, 0x100000)
    f.call('ParameterInit')
    f.var('BoardAddressSet', 0)
    for a in range(500):
        f.p(a, f.var('Parameter_def', index=a, width=2))
    for a,v in {1:mode,236:mode,709:2,214:5,386:0,346:0,128:0,127:0,
                332:0,333:0,248:0,315:0,163:0}.items():
        f.p(a,v)
    f.var('uc100ms',0)
    f.var('uc1s',0)
    f.call('InputStartCheck')
    for addr in (155,156,157,158,159,389,390,391,392,393,394,395,396,397):
        f.p(addr,1)
    return f


def faults(f):
    return [f.p(a) for a in FAULTS]


def reset(f):
    f.p(524,1-f.p(524))
    f.call('ErrorReset')
    f.call('BoardErrAction')


def old_outputs(f):
    p=[f.p(i) for i in range(f.symbols['Parameter'][1]//2)]
    for a in FAULTS:
        p[a]=0
    result={'Parameter':p}
    for name in ('output','DA','UnitWriteStatus','UnitReadStatus',
                 'RemoteInterlockStopFlag','IndoorSensorPartialStopFlag'):
        addr,size=f.symbols[name]
        result[name]=bytes(f.uc.mem_read(addr,size)).hex()
    return result


def main():
    report=dict(passed=False,hardware_access=False,checks=checks,
        image_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest())
    try:
        for index,polarity_addr,enable,fault in DI:
            for polarity in (0,1):
                f=board()
                f.p(polarity_addr,polarity)
                f.var('uc100ms',1)
                f.var('input',1-polarity,index,1)
                for _ in range(35):
                    f.call('DI_Points_Process');f.call('BoardErrAction')
                check(f'{fault} polarity{polarity} normal contact does not alarm',faults(f)==[0,0,0])
                f.var('input',polarity,index,1)
                for _ in range(29):
                    f.call('DI_Points_Process');f.call('BoardErrAction')
                check(f'{fault} polarity{polarity} before existing3s filter no fault',f.p(fault)==0)
                for _ in range(2):
                    f.call('DI_Points_Process');f.call('BoardErrAction')
                expected=[int(a==fault) for a in FAULTS]
                check(f'{fault} polarity{polarity} confirmed SAME fault register',
                    faults(f)==expected and f.var(enable)==1 and f.p(605)==1,
                    expected=expected,observed=faults(f))
                reset(f)
                check(f'{fault} polarity{polarity} reset while active reasserts',faults(f)==expected)
                f.var('input',1-polarity,index,1)
                for _ in range(3):
                    f.call('DI_Points_Process');f.call('BoardErrAction')
                check(f'{fault} polarity{polarity} contact restored retains cause',faults(f)==expected)
                reset(f)
                check(f'{fault} polarity{polarity} healthy reset clears cause and aggregate',
                    faults(f)==[0,0,0] and f.p(605)==0)
        # Simultaneous and successive causes remain individually visible.
        for mask in product((0,1),repeat=3):
            f=board()
            for bit,(_,_,enable,_) in zip(mask,DI):
                f.var(enable,bit)
            f.call('BoardErrAction')
            check(f'independent causes mask{mask}',faults(f)==list(mask))
        f=board()
        for _,_,enable,fault in DI:
            f.var(enable,1);f.call('BoardErrAction');f.var(enable,0)
        check('successive causes preserved until reset',faults(f)==[1,1,1])
        reset(f)
        check('single existing reset clears all resolved causes',faults(f)==[0,0,0] and f.p(605)==0)
        # Differential regression compares every existing Parameter, all output
        # arrays and all per-outdoor commands across modes and fault combinations.
        for mode in range(6):
            for mask in product((0,1),repeat=3):
                old,new=board(OLD,mode),board(NEW,mode)
                for f in (old,new):
                    for m in range(1,5):
                        for c in range(2):
                            f.field(True,m,'CompControl',c,1)
                    for bit,(_,_,enable,_) in zip(mask,DI):
                        f.var(enable,bit)
                    f.call('BoardErrAction')
                check(f'unchanged all control state mode{mode} mask{mask} active',old_outputs(old)==old_outputs(new))
                for f in (old,new):
                    for _,_,enable,_ in DI:
                        f.var(enable,0)
                    f.call('BoardErrAction')
                check(f'unchanged all control state mode{mode} mask{mask} released',old_outputs(old)==old_outputs(new))
                for f in (old,new):reset(f)
                check(f'unchanged all control state mode{mode} mask{mask} reset',old_outputs(old)==old_outputs(new))
        report['passed']=True
    except BaseException:
        report['error']=traceback.format_exc()
        raise
    finally:
        (build.DAY/'DI_ARM_regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('ARM PASS',len(checks),'checks; polarity and original control equivalence',flush=True)


if __name__=='__main__':main()
