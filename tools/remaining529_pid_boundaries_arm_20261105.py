"""Per-case numerical/simulated-time evidence from actual common firmware.

No board access. Does not qualify physical timing or scheduler accuracy.
"""
import sys,json,math,traceback
from fractions import Fraction as Q
from remaining529_offline_matrix_20261105 import init,ck,cases,checks,D,P
sys.path.insert(0,str(P.parents[1]/'.codex-tmp'))
import spec3438_arm as oracle

def step_controller(f,family,error,t,kp,ti,td,width):
 if family<2:
  for a,v in {1:family,236:family,412:t,416:kp,417:ti,418:td,426:kp,427:ti,428:td,125:0,127:0,332:0,315:0,738:250+error if family==0 else 250-error,739:250,120:width}.items():f.p(a,v)
  fn='SysNergryAction_PID';reg=880;zreg=879
 else:
  for a,v in {1:1,236:1,412:t,128:2,127:1,129:1,332:1,333:1,374:1,375:50,376:width,513:50-error,
   126:1,248:1,334:1,501:500-error,162:500,168:0,738:250-error,739:250,120:width,361:width,512:50,
   347:kp,348:ti,349:td,350:kp,351:ti,352:td,353:kp,354:ti,355:td,346:0}.items():f.p(a,v)
  fn,reg,zreg=(('HeatControl_UP',890,903),('PreHeatControl',891,905),('HumidtCtrl',892,907))[family-2]
 f.var('uc100ms',1)
 for _ in range(t*10):f.call(fn)
 return f.p(reg),oracle.signed(f.p(zreg))

def pid():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  for family in range(5):
   width=200 if family==4 else 40 if family==3 else 20
   for kind in range(8):
    cid=f'T11-{family*8+kind+1:03d}'
    if kind==4:
     # Independent shared PID routine with seeded past demand, in emulator only.
     for n0 in (1,100,101,200,201,400,401,500,501,1000):
      f=init(profile);a=0x20060000;n=n0;h=[0]*3;v=0;res=0
      f.write(a+16,n0)
      for e in (20,20,20,100,-100):
       f.write(a+20,50);f.p(412,5)
       f.call('IndoorPidDemandStep',e,a,a+16,a+20,a+24,a+32,5,100,0,width,a+48,a+52)
       n,h,v,res,z=oracle.oracle_step(n,h,v,res,e,5,100,0,5,width)
       ck(cid,profile+f' shared BX N0{n0} E{e}',f.read(a+16),n)
     continue
    periods=(1,5,10) if kind==6 else (5,)
    for t in periods:
     kp,ti,td=(13,41,7) if kind==5 else (100,1,0) if kind in (3,7) else (5,100,0)
     es=([20,20,20] if kind==0 else [20]*12 if kind==1 else [20]*12+[-20]*20 if kind==2 else
         [20]*4+[0,width//4-1,-width//4+1,width//4,-width//4] if kind==3 else
         [20,20,30,10,40,-20,0] if kind==5 else [20]*4 if kind==6 else [100]*20+[-100]*20)
     f=init(profile);n=0;h=[0]*3;v=0;res=0
     for i,e in enumerate(es):
      got,_=step_controller(f,family,e,t,kp,ti,td,width)
      if family<2:
       h=[e]+h[:2]
       if v<2:n=0 if e<=width//4 else 200 if e<=width else 300 if e<=2*width else 400 if e<=Q(5,2)*width else 500;v+=1;res=0
       elif abs(e)*4<width:res=0
       else:
        delta=Q(kp,100)*oracle.bx(n)*(Q(h[0]-h[1],10)+Q(t,ti)*Q(h[0],10)+Q(td,t)*Q(h[0]-2*h[1]+h[2],10))*1000
        total=res+int(delta*1000);z=int(Q(total,1000));res=total-z*1000;n=max(0,min(1000,n+z))
        if n==0 and total<0 or n==1000 and total>0:res=0
      else:n,h,v,res,z=oracle.oracle_step(n,h,v,res,e,kp,ti,td,t,width)
      ck(cid,profile+f' family{family} T{t} sample{i+1} E{e}',got,n)
  for mode in (0,1):
   for i,e in enumerate((5,6,20,21,40,41,50,51)):
    f=init(profile);got,_=step_controller(f,mode,e,5,5,100,0,20)
    want=(0,200,200,300,300,400,400,500)[i]
    ck(f'T11-{41+mode*8+i:03d}',profile+f' initial mode{mode} error{e}',got,want)
  for i,room in enumerate((124,125,126,312,313,320)):
   f=init(profile,1);f.p(738,room);f.p(739,250);f.p(512,50);f.call('HeatControl_UP')
   ck(f'T11-{64+i:03d}',profile+f' literal WD room{room}',f.p(890),1000 if room<125 else 0)
  for i,temp in enumerate((1,0,-1,-10,-25,-49,-50,-51)):
   f=init(profile,1)
   for a,v in {333:1,374:0,356:0,357:-50,512:temp,346:0}.items():f.p(a,v)
   f.call('PreHeatControl');ck(f'T11-{70+i:03d}',profile+f' ambient preheat{temp}',f.p(891),max(0,min(1000,-temp*20)))
  for i,temp in enumerate((39,40,41,50,59,60,61)):
   f=init(profile,1)
   for a,v in {333:1,374:1,375:50,376:40,513:temp,350:5,351:100,352:0,346:0}.items():f.p(a,v)
   f.var('uc100ms',1);n=0;h=[0]*3;v=0;res=0
   for sample in range(6):
    for _ in range(50):f.call('PreHeatControl')
    n,h,v,res,z=oracle.oracle_step(n,h,v,res,50-temp,5,100,0,5,40)
    ck(f'T11-{78+i:03d}',profile+f' postpreheat temp{temp} sample{sample}',f.p(891),n)

def ambient():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  for mode,temps,start in ((0,(219,220,221,252,253,285,317,318,349,350,351),1),(1,(-1,0,1,30,60,90,119,120,121),12)):
   f=init(profile,mode)
   for a,v in {316:350,317:220,318:0,319:120}.items():f.p(a,v)
   for i,temp in enumerate(temps):
    want=max(0,min(8,math.ceil(8*(temp-220)/130))) if mode==0 else max(0,min(8,math.ceil(8*(120-temp)/120)))
    ck(f'T09-{start+i:03d}',profile+f' CN8 mode{mode} temp{temp}',f.call('IndoorEnvCompTargetFromTemp',temp),want)

def autoswitch():
 for profile in ('PRODUCTION','BENCH_ONLY_3S'):
  for cid,mode,humidity,room,rh,enabled in [('T11-089',0,0,239,500,1),('T11-092',1,0,261,500,1),('T11-093',1,1,261,500,1),('T11-094',1,1,250,601,1),('T11-101',0,0,239,500,0),('T11-104',0,0,239,500,1),('T11-105',0,0,239,500,1)]:
   f=init(profile,mode);qhs=600 if cid=='T11-104' else 1200 if cid=='T11-105' else 60
   for a,v in {128:0,127:0,332:0,126:humidity,125:humidity,248:1,320:enabled,321:50,322:qhs,315:0,738:room,739:250,162:500,501:rh,361:200,890:0,892:0,119:0}.items():f.p(a,v)
   f.var('uc1s',1)
   for _ in range(qhs-1):f.call('IndoorAutoCoolHeatSwitchAction')
   ck(cid,profile+' simulated QHS before',f.p(236),mode)
   f.call('IndoorAutoCoolHeatSwitchAction');ck(cid,profile+' simulated QHS at threshold',f.p(236),1-mode if enabled else mode)

def main():
 errors=[]
 for fn in (pid,ambient,autoswitch):
  print('START',fn.__name__,flush=True)
  try:fn()
  except Exception:errors.append(dict(function=fn.__name__,error=traceback.format_exc()));traceback.print_exc()
 (D/'remaining529_pid_boundaries_ARM.json').write_text(json.dumps(dict(hardware_access=False,time_is_simulated=True,cases=cases,checks=checks,errors=errors),ensure_ascii=False,indent=2),'utf8')
 print('PID MATRIX COMPLETE',len(cases),len(checks),'mismatches',sum(not c['passed'] for c in checks),'errors',len(errors),flush=True)
if __name__=='__main__':main()
