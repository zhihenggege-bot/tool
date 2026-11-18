"""PID humidity compensation, auxiliary gates and strict switch boundaries.

Offline linked production/BENCH code. Clock ticks are simulated.
"""
import json
import traceback
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D


def ys():
    variants=({}, {125:0}, {892:1}, {890:1000}, {738:261}, {501:600}, {501:601})
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for i,change in enumerate(variants):
            f=init(profile)
            for a,v in {125:1,248:1,501:601,162:500,361:200,738:250,739:250,890:0,892:0,412:5,127:1,332:1}.items():f.p(a,v)
            for a,v in change.items():f.p(a,v)
            f.var('uc100ms',1)
            for _ in range(50):f.call('SysNergryAction_PID')
            ck(f'T11-{57+i:03d}',profile+' humidity compensation YS',f.p(877),20 if i in (0,6) else 0)


def auxiliary():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for i in range(4):
            f=init(profile,1)
            for a,v in {128:1,127:1,129:1,332:1,738:124,739:250,512:50,346:0}.items():f.p(a,v)
            for m in range(1,5):
                for c in range(2):f.field(False,m,'CompStatus',c,3)
            if i in (1,2):f.field(False,4,'CompStatus',1,0)
            if i==2:f.p(1978,1) # Outdoor4 base1974 +4 = compressor2 disabled.
            if i==3:
                for c in range(2):f.field(False,4,'CompStatus',c,0)
                f.p(1976,1)
            f.call('HeatControl_UP')
            ck(f'T11-{85+i:03d}',profile+' available-capacity auxiliary gate',f.p(890),0 if i==1 else 1000)


def switching():
    scenarios=[
        ('T11-095',0,0,{738:240},False),('T11-095',0,0,{738:239},True),
        ('T11-096',1,0,{738:260},False),('T11-096',1,0,{738:261},True),
        ('T11-097',1,1,{738:250,501:600},False),('T11-097',1,1,{738:250,501:601},True),
        ('T11-098',0,1,{127:1,332:1,890:500,119:1},False),
        ('T11-098',0,1,{127:1,332:1,890:501,119:1},True),
        ('T11-099',0,1,{127:1,332:1,890:501,119:1},True),
        ('T11-099',0,1,{127:1,332:1,890:501,119:2},False),
        ('T11-100',1,1,{738:250,501:601,892:1},False),
        ('T11-100',1,1,{738:250,501:601,892:0},True)]
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for cid,mode,humidity,change,expected in scenarios:
            f=init(profile,mode)
            for a,v in {128:0,127:0,332:0,125:humidity,126:humidity,248:1,320:1,321:50,322:60,315:0,
                        738:239 if mode==0 else 261,739:250,162:500,501:500,361:200,890:0,892:0,119:0}.items():f.p(a,v)
            for a,v in change.items():f.p(a,v)
            f.var('uc1s',1)
            for _ in range(59):f.call('IndoorAutoCoolHeatSwitchAction')
            ck(cid,profile+f' {change} before60',f.p(236),mode)
            f.call('IndoorAutoCoolHeatSwitchAction')
            ck(cid,profile+f' {change} at60 strict threshold',f.p(236),1-mode if expected else mode)


def main():
    errors=[]
    for fn in (ys,auxiliary,switching):
        print('START',fn.__name__,flush=True)
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    (D/'remaining529_gates_ARM.json').write_text(json.dumps({'hardware_access':False,'time_is_simulated':True,
        'cases':cases,'checks':checks,'errors':errors},ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)


if __name__=='__main__':main()
