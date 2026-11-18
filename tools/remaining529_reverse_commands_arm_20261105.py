"""Normal stop/start command reversals; current ARM, simulated scheduler time."""
import importlib.util,json,traceback
from remaining529_offline_matrix_20261105 import init,ck,checks,cases,D
from test_indoor_3133_arm import out,ao
loader=importlib.util.spec_from_file_location('current_modes',D.parents[2]/'.codex-tmp/v1052_expanded_modes_ARM.py')
mod=importlib.util.module_from_spec(loader);loader.loader.exec_module(mod)

def run():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
    for scenario,cid in (('valve','T13-059'),('pressure','T13-060'),('blowdown','T13-062')):
        mode=1 if scenario=='blowdown' else 2
        f=mod.board(profile,mode)
        f.p(135,30);f.p(386,1 if scenario=='pressure' else 0)
        f.var('X_15',1);f.var('X_14',1)
        valve=5 if profile=='BENCH_ONLY_3S' else 150
        gap=3 if profile=='BENCH_ONLY_3S' else 30
        when=valve+gap*2+1 if scenario=='pressure' else 241
        if scenario=='valve':
            for sec in range(30):
                mod.cycle(f,sec)
                if f.p(709)==1:
                    when=sec;break
        else:
            for sec in range(when+1):mod.cycle(f,sec)
        ck(cid,profile+' genuine precondition step',f.p(709),2 if scenario=='blowdown' else 1)
        f.p(398,0);f.p(700,0);mod.cycle(f,when+1)
        state_on_stop=f.p(709)
        f.p(398,1);f.p(700,4)
        trace=[];saw_off=False;saw_running=False
        for sec in range(when+2,when+602):
            mod.cycle(f,sec)
            state=[f.p(709),*[out(f,ch) for ch in (3,6,10)]]
            if not trace or trace[-1]['state']!=state:trace.append({'simulated_s':sec,'state':state})
            saw_off|=f.p(709)==0
            if f.p(709)==2:
                saw_running=True;break
        # Switch.c explicitly discards a start command until SysStep==0.
        # Characterize that behavior without inventing queued-start semantics.
        ck(cid,profile+' reversal completes normal shutdown without bypass',saw_off,True)
        ck(cid,profile+' start during shutdown is not queued',saw_running,False)
        f.p(398,1)
        for sec2 in range(sec+1,sec+301):
            mod.cycle(f,sec2)
            if f.p(709)==2:break
        ck(cid,profile+' new command after shutdown can start normally',f.p(709),2)
        ck(cid,profile+' reversal does not energize thermal AO',
           [ao(f,ch) for ch in (0,1,2,9)],[0]*4)
        cases[cid].append({'profile':profile,'scenario':scenario,'stop_step':state_on_stop,
                           'saw_intermediate_off':saw_off,'trace':trace,'passed':saw_running})
    # A requested compressor has not yet reached its running ACK. Normal stop
    # must withdraw it rather than wait for a compressor that never started.
    f=init(profile)
    f.field(False,1,'CompStatus',0,0)
    f.call('CompLoading')
    ck('T13-061',profile+' one start request actually pending',f.field(True,1,'CompControl',0),1)
    f.p(709,3);f.call('CompNormalStopAction')
    ck('T13-061',profile+' stop withdraws unconfirmed start',f.field(True,1,'CompControl',0),0)

def main():
 errors=[]
 try:run()
 except Exception:errors.append(traceback.format_exc());traceback.print_exc()
 (D/'remaining529_reverse_commands_ARM.json').write_text(json.dumps(
     {'hardware_access':False,'time_is_simulated':True,'cases':cases,'checks':checks,'errors':errors,
      'limits':'No transport/physical output; startup during shutdown is discarded by Switch.c, not queued. Loading covers pending-request cancellation only, not full live loaded reversal.'},
     ensure_ascii=False,indent=2),'utf8')
 print('COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)

if __name__=='__main__':main()
