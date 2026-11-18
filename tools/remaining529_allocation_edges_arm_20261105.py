"""Exact-image compressor selection and EEV initialization, emulator only."""
import json
import traceback
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D


def selection():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for shortest,cid in ((0,'T10-010'),(1,'T10-011')):
            f=init(profile)
            f.p(214,2)
            for c in range(2):f.field(False,1,'CompTotalRunSeconds',c,100 if c==shortest else 1000,width=4)
            f.call('CompLoading')
            ck(cid,profile+' shortest compressor first',[f.field(True,1,'CompControl',c) for c in range(2)],[int(c==shortest) for c in range(2)])
            for c in range(2):
                f.field(True,1,'CompControl',c,1)
                f.field(False,1,'CompStatus',c,2)
            f.call('Unloading')
            ck(cid,profile+' longest compressor off first',[f.field(True,1,'CompControl',c) for c in range(2)],[int(c==shortest) for c in range(2)])
        for longest,cid in ((1,'T10-012'),(2,'T10-013')):
            f=init(profile)
            f.p(214,3)
            for m in (1,2):
                f.field(False,m,'OutdoorTotalRunSeconds',value=20000 if m==longest else 1000,width=4)
                for c in range(2):
                    f.field(True,m,'CompControl',c,1)
                    f.field(False,m,'CompStatus',c,2)
            f.call('Unloading')
            ck(cid,profile+' longest outdoor unloaded first',
               [f.field(True,m,'CompControl',1) for m in (1,2)],[int(m!=longest) for m in (1,2)])
        for reheat,start in ((0,23),(1,26)):
            for delta,offset in ((10,0),(-10,1)):
                f=init(profile)
                for a,v in {880:500,879:delta,127:reheat,332:reheat,125:0,315:0}.items():f.p(a,v)
                fn='IndoorCompTargetFromN' if delta>0 else 'IndoorCompTargetDn'
                ck(f'T09-{start+offset:03d}',profile+' N500 CN8 signed target',f.call(fn,500,8,reheat),4)


def eev_initial():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for maximum in (200,500):
            for starting in (0,200,500):
                f=init(profile)
                for a,v in {12:maximum,411:starting,365:1,1145:0,1153:0}.items():f.p(a,v)
                f.field(True,1,'CompControl',0,1)
                f.field(False,1,'CompStatus',0,2)
                ptr=0x20060000
                f.write(ptr,1)
                f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
                ck('T12-026',profile+f' max{maximum} start{starting} clamped',f.p(1145),min(maximum,starting))
                ck('T12-027',profile+f' start{starting} initial flag consumed',f.read(ptr),0)
                if maximum==500 and starting==200:
                    ck('T12-001',profile+' cooling initial200',f.p(1145),200)
        f=init(profile,1)
        f.p(12,500)
        ptr=0x20060000
        for i in range(4):f.write(ptr+4*i,1)
        f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
        ck('T12-002',profile+' ordinary heat seeds 20-step seating closure',f.p(1145),20)
        f.var('uc1s',1)
        f.call('EEVSpecAutoAction',0,ptr,ptr+4,ptr+8,ptr+12)
        ck('T12-002',profile+' ordinary heat completes indoor seating closure',f.p(1145),0)


def main():
    errors=[]
    for fn in (selection,eev_initial):
        try:fn()
        except Exception:
            errors.append({'function':fn.__name__,'traceback':traceback.format_exc()})
            traceback.print_exc()
    report={'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors}
    (D/'remaining529_allocation_edges_ARM.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)


if __name__=='__main__':main()
