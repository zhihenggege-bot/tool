"""Special-mode abort and emergency matrix in linked ARM, simulated time only."""
import importlib.util
import json
import traceback
from remaining529_offline_matrix_20261105 import ck,checks,cases,D
from test_indoor_3133_arm import out,ao

loader=importlib.util.spec_from_file_location('current_modes',D.parents[2]/'.codex-tmp/v1052_expanded_modes_ARM.py')
mod=importlib.util.module_from_spec(loader)
loader.loader.exec_module(mod)


def matrix():
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
        for mode,start in ((3,47),(4,51),(5,55)):
            # Dedicated special-mode times remain real specification values in
            # both profiles; the exhaust fan stagger is profile dependent.
            at=(100,150,180,240 if mode!=4 else 215)
            for offset,when in enumerate(at):
                cid=f'T13-{start+offset:03d}'
                for emergency in (False,True):
                    f=mod.board(profile,mode)
                    f.p(323,1)
                    f.p(324,1)
                    for sec in range(when+1):mod.cycle(f,sec)
                    before=[f.p(709),f.p(885),*[out(f,ch) for ch in (3,10,12)]]
                    if emergency:f.p(710,1)
                    else:
                        f.p(398,0)
                        f.p(700,0)
                    trace=[]
                    stopped=False
                    for sec in range(when+1,when+101):
                        mod.cycle(f,sec)
                        state=[f.p(709),f.p(885),*[out(f,ch) for ch in (3,4,6,7,10,11,12,14)]]
                        if not trace or trace[-1]['state']!=state:trace.append({'simulated_s':sec,'state':state})
                        if f.p(709)==0 and not any(out(f,ch) for ch in (3,4,6,7,10,11,12,14)):
                            stopped=True
                            break
                    ck(cid,profile+f' emergency{emergency} at{when}s reaches off',stopped,True)
                    ck(cid,profile+f' emergency{emergency} clears thermal AOs',
                       [ao(f,ch) for ch in (0,1,2,9)],[0]*4)
                    cases[cid].append({'profile':profile,'emergency':emergency,'before':before,'trace':trace,'passed':stopped})


def main():
    errors=[]
    try:matrix()
    except Exception:
        errors.append(traceback.format_exc())
        traceback.print_exc()
    (D/'remaining529_special_abort_ARM.json').write_text(json.dumps(
        {'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors},
        ensure_ascii=False,indent=2),'utf8')
    print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)


if __name__=='__main__':main()
