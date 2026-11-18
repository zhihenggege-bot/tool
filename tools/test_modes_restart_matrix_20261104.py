"""Expanded 3.1/3.2/3.3 cases in actual final ARM images, no hardware access.
Long-duration boundaries and all 30 ordered transitions complement COM6 tests.
"""
import json,hashlib
from test_defrost_lifecycle_arm import Firmware,ROOT
from test_indoor_3133_arm import out,ao
D=ROOT/'.codex-tmp/spec3133_hardware_20261104'
BASE=ROOT/'.codex-tmp/sequence_timing_v1047_v1238_20261104'
rows=[]
def check(ok,label,details=None):
 rows.append({'label':label,'passed':bool(ok),'details':details})
 print('PASS' if ok else 'FAIL',label,details or '',flush=True)
 assert ok,(label,details)
def board(profile,mode=2):
 path=BASE/profile/f'PSC330_V10.47_{profile}.axf'
 f=Firmware(str(path.relative_to(ROOT)));f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
 for i in range(500):f.p(i,f.var('Parameter_def',index=i,width=2))
 for a,v in {38:0,214:3,236:mode,1:mode,700:4,709:0,163:0,164:1,166:1,398:1,329:1,330:1,331:1,381:0,386:0,153:0,335:1,336:1,337:1,338:1,328:30,132:30,135:0,125:0,126:0,127:0,128:0,129:0,332:0,333:0,334:0,323:999,324:999,325:0,315:0,160:250,161:250,511:250,512:150}.items():f.p(a,v)
 for i in range(250,258):f.p(i,1)
 f.var('OilCount',10000)
 return f
def cycle(f,s,*fn):
 f.var('Systick_1ms',30000+int(s*1000));f.var('uc1s',1)
 for name in (fn or ('UserAction',)):f.call(name)
def main():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  # A full mode permutation test: the source special modes have reached their
  # actual fan/disinfection phase, not merely SysStep=2 in the damper wait.
  for source in range(6):
   for target in range(6):
    if source==target:continue
    f=board(profile,source)
    for s in range(0,241):cycle(f,s)
    check(f.p(236)==source and f.p(709)==2,f'{profile} source{source} running before transition{target}')
    if source in (3,5):check(out(f,12)==1,f'{profile} source{source} disinfection active')
    if source==4:check(out(f,3) and out(f,10),f'{profile} source4 both purge fans active')
    f.p(236,target);seen_old=False;completed=False;trace=[]
    for s in range(241,741):
     cycle(f,s)
     state=(f.p(236),f.p(709),out(f,3),out(f,12),f.var('IndoorPendingWorkMode'))
     if not trace or trace[-1][1:]!=list(state):trace.append([s,*state])
     if f.p(236)==source:seen_old=True
     if f.p(236)==target and f.p(709)==2:
      completed=True;break
    check(seen_old and completed,f'{profile} complete shutdown then transition {source}->{target}',trace)
    check(not any(ao(f,i) for i in (0,1,2,9)),f'{profile} transition {source}->{target} no thermal leakage')
  # Bounds of 999-minute operation without asking a real board to run 16h39m.
  for mode in (3,4):
   f=board(profile,mode);f.p(709,0)
   # Call the isolated real special-mode sequencer with its normal run status.
   cycle(f,0,'IndoorDisinfectExhaustAction')
   cycle(f,150,'IndoorDisinfectExhaustAction')
   start=170 if mode==3 else (153 if profile=='BENCH_ONLY_3S' else 180)
   cycle(f,start,'IndoorDisinfectExhaustAction')
   cycle(f,start+999*60-.001,'IndoorDisinfectExhaustAction')
   check(bool(out(f,12) if mode==3 else out(f,3)),f'{profile} mode{mode} 999min one millisecond early still running')
   cycle(f,start+999*60,'IndoorDisinfectExhaustAction')
   check(not out(f,12) and not out(f,3),f'{profile} mode{mode} exact999min exits running phase')
  # Disabled combined stages must choose the remaining enabled stage.
  for dis,purge,phase in ((0,1,2),(1,0,1)):
   f=board(profile,5);f.p(323,dis);f.p(324,purge)
   cycle(f,0,'IndoorDisinfectExhaustAction')
   check((out(f,14),out(f,7))==((1,0) if phase==2 else (0,1)),f'{profile} combined zero stage {dis}/{purge} selects phase{phase}')
  # HMI parameter validation is executed, not inferred from comments.
  f=board(profile)
  for a,lo,hi in ((323,0,999),(324,0,999),(330,0,2),(329,1,3),(130,0,100),(131,0,100),(449,0,100)):
   check(all(f.call('ParamCanWriteFromHMI',a,v)==int(lo<=v<=hi) for v in (lo-1,lo,hi,hi+1)),f'{profile} writable bounds register{a}={lo}..{hi}')
 result={'hardware_access':False,'time_is_emulated':True,'checks':rows,'passed':all(x['passed'] for x in rows),'sha256':{p:hashlib.sha256((BASE/p/f'PSC330_V10.47_{p}.axf').read_bytes()).hexdigest() for p in ('PRODUCTION','BENCH_ONLY_3S')}}
 (D/'expanded_ARM_matrix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(len(rows),'expanded ARM checks passed')
if __name__=='__main__':main()
