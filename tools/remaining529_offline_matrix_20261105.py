"""Actual linked V10.52/V12.39 ARM matrices. No physical hardware access.

Per-case evidence is staged here; import into case journal only after the COM6
writer finishes, to avoid racing its CSV/JSON update. Time below is simulated.
"""
import json,hashlib,traceback,math
from fractions import Fraction as Q
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware,ROOT
P=ROOT/'.codex-tmp/fan_zero_target_v1052_v1239_20261105'
D=ROOT/'测试证据/内机实测_20261105/BENCH_V1052_V1239'
cases={};checks=[]

def ck(cid,label,got,want):
    row=dict(case=cid,label=label,got=got,expected=want,passed=got==want)
    checks.append(row);cases.setdefault(cid,[]).append(row)
    if got!=want:print('MISMATCH',cid,label,got,want,flush=True)

def init(profile,mode=0,out=False):
    path=P/profile/f'PSC{316 if out else 330}_V{ "12.39" if out else "10.52"}_{profile}.axf'
    f=Firmware(str(path));f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
    for a in range(500):f.p(a,f.var('Parameter_def',index=a,width=2))
    f.var('Systick_1ms',30000)
    if out:f.var('BoardAddressSet',1);return f
    for a,v in {1:mode,236:mode,214:5,709:2,700:4,738:250,739:250,
        329:3,330:2,331:1,381:0,386:0,128:2,127:1,332:1,333:0,315:0,
        512:50,1229:1,1241:1,1253:1,1265:1,1277:1}.items():f.p(a,v)
    for a in range(250,258):f.p(a,1)
    for i in range(17):f.var('SensorStatus',0,i,1)
    f.var('X_02',1)
    for m in range(1,5):
        f.var('PSC316SetValid',1,m-1,1)
        f.field(False,m,'CompRuntimeValid',value=1,width=1)
        for j,v in enumerate((316,12,39)):f.field(False,m,'Version',j,v)
        f.field(False,m,'OutdoorTotalRunSeconds',value=m*20000,width=4)
        for c in range(2):
            f.var('CompMinStopCount',1000,2*m+c,4);f.var('CompMinRunCount',1000,2*m+c,4)
            f.field(False,m,'CompTotalRunSeconds',c,1000*(c+1),width=4)
    return f

def sensors():
    # All raw NTCS channels and their masking rules, both electrical extremes.
    ai_raw_index=(3,4,5,6,7)
    for profile in ('PRODUCTION','BENCH_ONLY_3S'):
      for sensor in range(18):
       actual=3 if sensor==4 else sensor-1 if sensor>4 else sensor
       for mode in range(3):
        for bad in range(2):
         cid=f'T03-{9+sensor*6+mode*2+bad:03d}'
         f=init(profile,mode);f.var('uc10ms',1);f.var('uc100ms',1)
         f.p(25,0)
         # Enable the function that uses this sensor, with all other raw inputs healthy.
         if actual==0:f.p(335,2);f.p(377,0)
         if actual==1:f.p(125,1);f.p(126,1);f.p(248,1);f.p(334,1)
         if actual in (2,4):f.p(335,2);f.p(377,1);f.p(381,1)
         if actual==7:f.p(315,1);f.p(327,1)
         if actual==8:f.p(333,1);f.p(374,1)
         if actual<5:
          f.p(459+actual,0)
          for i in range(8):f.var('ADC_Val',2000,i,2)
          for _ in range(20):f.call('ADProcess')
          ck(cid,profile+' healthy raw input',f.var('SensorStatus',index=actual,width=1),0)
          f.var('ADC_Val',4095 if bad==0 else 0,ai_raw_index[actual],2)
          for _ in range(20):f.call('ADProcess')
         else:
          # Valid raw is about 1.07V; all NTCs populated in this fixture.
          for i in range(12):f.var('NTC_AD',17000,i,2)
          f.call('Get_temp16')
          ck(cid,profile+' healthy NTC',f.var('SensorStatus',index=actual,width=1),0)
          f.var('NTC_AD',32767 if bad==0 else 0,actual-5,2);f.call('Get_temp16')
         ck(cid,profile+' invalid raw detected',f.var('SensorStatus',index=actual,width=1),1)
         # Existing diagnostic delay counted at the real 100ms task cadence.
         delay=(f.p(25)+3)*10
         for _ in range(delay):f.call('SensorErrAction')
         ck(cid,profile+' fault latched',f.var('SensorErr',index=actual,width=1),1)
         f.call('BoardErrAction')
         # NTC0/1 have no thermal function in ventilation; no stop required.
         ck(cid,profile+' partial stop scope',f.var('IndoorSensorPartialStopFlag',width=1),int(mode!=2))
         f.var('SensorStatus',0,actual,1);f.call('SensorErrAction')
         ck(cid,profile+' healthy again does not clear latch',f.var('SensorErr',index=actual,width=1),1)
         f.p(524,1);f.call('ErrorReset');f.p(524,0);f.call('ErrorReset');f.call('SensorErrAction');f.call('BoardErrAction')
         ck(cid,profile+' reset clears fault',f.var('SensorErr',index=actual,width=1),0)
         ck(cid,profile+' reset releases stop flag',f.var('IndoorSensorPartialStopFlag',width=1),0)
         print('SENSOR',cid,profile,flush=True)

def eev():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  for out in (False,True):
   f=init(profile,out=out);who=profile+('/316' if out else '/330');ptr=0x20060000
   regs=(198,202,199,203,204,205,206) if out else (366,367,368,16,369,370,371)
   for a,v in zip(regs,(50,20,5,5,100,0,20)):f.p(a,v)
   def sample(cid,sh,ev,td=0,limit=20,errors=None):
    f.call('EEVSpecPidReset',0);f.p(regs[5],td);f.p(regs[6],limit)
    h=[0,0,0];valid=0;res=0;rows=[]
    for real in (errors if errors is not None else [sh]*7):
     err=real-50;h=[err]+h[:2]
     if valid<2:expected=-min(limit,5) if ev>120 else 0;valid+=1
     else:
      z=5*(Q(h[0]-h[1],10)+Q(5,100)*Q(h[0],10)+Q(td,5)*Q(h[0]-2*(h[0]-h[1])+h[2],10))
      total=res+int(z*1000);expected=int(Q(total,1000));res=total-expected*1000
      if ev>120 and total>=0:expected=-5;res=0
      elif 100<=ev<=120 and total>=0:expected=0;res=0
      elif -10<=err<=10:expected=0;res=0
      if expected>=limit:expected=limit;res=0
      if expected<=-limit:expected=-limit;res=0
     f.var('EEVSpecPidCount',49,0,4);f.var('uc100ms',1)
     got=f.call('EEVSpecPidStep',0,real,ev,ptr) if out else f.call('EEVSpecPidStep',0,real,50,ev,ptr)
     if got&0x80000000:got-=2**32
     ck(cid,who+f' SH{real}/EV{ev}/TD{td} sample{len(rows)+1}',[got,f.read(ptr,1)],[expected,1]);rows.append(got)
    return rows
   for i,sh in enumerate((39,40,41,50,59,60,61,100,0)):sample(f'T12-{6+i:03d}',sh,90)
   for i,ev in enumerate((99,100,120,121)):
    sample(f'T12-{15+i*2:03d}',100,ev)
    sample(f'T12-{16+i*2:03d}',0,ev)
   sample('T12-023',100,90,errors=[50,50,70])
   sample('T12-024',100,90,td=10,errors=[50,50,70,60,80,60,50])
   for limit in (3,20,50):sample('T12-025',200,90,limit=limit)
   for emergency in (False,True):
    cid='T12-029' if emergency else 'T12-028'
    # Each channel isolated; no artificial transport or motor-position claim.
    c=init(profile,out=out);c.p(10,500);c.p(12,500)
    if not out:c.p(1426,int(emergency));c.p(710,int(emergency))
    c.var('uc1s',0)
    def close(current):
     return c.call('EEVCloseStepTarget',0,current,2 if emergency else 1) if out else c.call('EEVCloseStepTarget',0,current,500)
    ck(cid,who+' close seeds overtravel',close(200),210 if emergency else 220)
    for tick in range(1,13):
     c.var('uc1s',0);close(200);c.var('uc1s',1)
     want=max(0,(210 if emergency else 220)-20*tick)
     ck(cid,who+f' tick{tick}',close(200),want)
     ck(cid,who+f' duplicate tick{tick}',close(200),want)

def allocation():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  for i,(diff,short) in enumerate((d,s) for d in (7199,7200,7201) for s in (1,2)):
   cid=f'T10-{4+i:03d}';f=init(profile);f.p(214,3)
   f.field(False,short,'OutdoorTotalRunSeconds',value=20000-diff,width=4)
   f.field(False,3-short,'OutdoorTotalRunSeconds',value=20000,width=4)
   chosen=short if diff>7200 else 1
   f.call('CompLoading');got=[f.field(True,m,'CompControl',0) for m in (1,2)]
   ck(cid,profile+' choose runtime/sequence',got,[int(chosen==1),int(chosen==2)])
  for kind,cid in [('compdisabled','T10-014'),('unitdisabled','T10-015'),('fault','T10-016'),('comm','T10-017'),('defrost','T10-018'),('recovery','T10-019')]:
   f=init(profile)
   if kind=='compdisabled':f.p(1833,1)
   if kind=='unitdisabled':f.p(1832,1)
   if kind=='fault':f.p(2598,1)
   if kind=='comm':f.var('UnitCommErr',1,1,2)
   if kind=='defrost':f.field(False,1,'CanDefrost',value=8)
   if kind=='recovery':f.field(False,1,'CanDefrost',value=7)
   ck(cid,profile+' excluded from load',f.call('CompCanLoad',1,0),0)
   f.call('CompLoading');ck(cid,profile+' unavailable circuit not selected',f.field(True,1,'CompControl',0),0)
  for target in (1,2,3):
   cid=f'T10-{target:03d}';f=init(profile)
   f.field(False,3,'CompStatus',0,2);f.field(True,3,'CompControl',0,1)
   f.call('CompLoading');ck(cid,profile+' fill running unit before idle',f.field(True,3,'CompControl',1),1)
  f=init(profile)
  for n in range(8):
   f.call('CompLoading');selected=[]
   for m in range(1,5):
    for c in range(2):
     if f.field(True,m,'CompControl',c):selected.append([m,c]);f.field(False,m,'CompStatus',c,2)
   ck('T10-020',profile+f' 4 units loading step{n+1}',len(selected),n+1)
   f.var('Systick_1ms',40000+(n+1)*31000)

def main():
 errors=[]
 for fn in (sensors,eev,allocation):
  print('MATRIX START',fn.__name__,flush=True)
  try:fn()
  except Exception:errors.append(dict(function=fn.__name__,traceback=traceback.format_exc()));traceback.print_exc()
 report=dict(hardware_access=False,time_is_simulated=True,version='330 V10.52 /316 V12.39',cases=cases,checks=checks,errors=errors,
  image_sha256={str(p.relative_to(P)):hashlib.sha256(p.read_bytes()).hexdigest() for p in P.glob('*/*.axf')})
 (D/'remaining529_offline_matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
 print('MATRIX COMPLETE',len(cases),'cases',len(checks),'checks','mismatches',sum(not x['passed'] for x in checks),'errors',len(errors),flush=True)
if __name__=='__main__':main()
