"""Affected fan feedback plus wall-clock pressure protection, normal protocol.

DI polarity simulates contacts; live SWD only READS raw DI and never halts/writes.
"""
import time,traceback
from remaining571_common_20261105 import Bench,case_error,now
from run_indoor_bench_20261105 import axf_symbols,BOARDS,ConnectHelper

def main():
 b=Bench('529_fan_pressure');sy=axf_symbols()
 try:
  for mode,basis,cid in [(0,1,'T08-001'),(0,0,'T08-002'),(1,1,'T08-003'),(1,0,'T08-004')]:
   try:
    b.setup(mode);b.config({329:3,133:basis,339:60,340:60,341:30,342:90,290:2,291:10,
       343:720,344:100,345:100,295:0,311:0})
    b.ai(3,50,10);s=b.start();initial=s['ao'][7]
    raised=b.wait(cid+' low feedback',lambda s:s['ao'][7]>initial,10)
    b.ai(3,150,30);high=b.sample(cid+' high')['ao'][7]
    lowered=b.wait(cid+' high feedback',lambda s:s['ao'][7]<high,10)
    b.ai(3,100,20);time.sleep(.5);hold=b.sample(cid+' target')['ao'][7]
    rows=b.observe(cid+' hold',5)
    assert all(s['ao'][7]==hold and 300<=s['ao'][7]<=900 and s['do'][3] and s['do'][6] and s['ao'][4]==500 for s in rows)
    b.record(cid,'部分通过',f'V10.52 冷热模式{mode}/依据{basis}：低反馈升{initial}→{raised["ao"][7]}，高反馈降至{lowered["ao"][7]}；目标5秒保持及手动回风5V、DO许可符合。',
     '公开工程量映射；实际传感器/端子、正式档待测',dict(raised=raised,lowered=lowered,hold=rows))
   except Exception as e:case_error(b,cid,e)
  with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
   def raw(ch):return ss.target.read8(sy['X_'+str(ch)][0])
   def contact(ch,value):
    reg=397 if ch==15 else 396
    if raw(ch)!=value:b.wr(reg,1-b.rd(reg)[0])
    end=time.monotonic()+5
    while raw(ch)!=value:
     assert time.monotonic()<end,(ch,'polarity did not change raw DI');time.sleep(.1)
    return {'at':now(),'monotonic':time.monotonic(),'raw':raw(ch),'polarity':b.rd(reg)[0]}
   for ch in (15,14):
    ids=['T04-001','T04-002','T04-003'] if ch==15 else ['T04-004','T04-005','T04-006']
    alltraces=[]
    for fanmode in (2,3):
     entry={'ch':ch,'fanmode':fanmode,'started':now(),'events':[]};alltraces.append(entry)
     b.log['cases']['pressure_'+str(ch)+'_'+str(fanmode)]=entry
     b.setup(2);b.config({329:fanmode,330:2,386:2 if ch==15 else 3,133:1,345:100,339:60,341:30,342:90})
     if fanmode==3:b.ai(3,100,20)
     contact(ch,0);b.reset_faults();b.wr(398,1)
     s=b.wait('pressure fan active',lambda s:s['do'][3 if ch==15 else 6]==1,20)
     on=time.monotonic();entry['fan_started']=s;entry['fan_started_monotonic']=on
     entry['events'].append(contact(ch,1));time.sleep(1.8)
     entry['events'].append(contact(ch,0));time.sleep(.6)
     okreg=888 if ch==15 else 889;faultreg=912 if ch==15 else 913
     entry['interrupted_qualification']=b.sample('qualification interrupted')
     assert b.rd(okreg)[0]==0 and b.rd(709)[0]==1
     closed=time.monotonic();entry['events'].append(contact(ch,1))
     ready=b.wait('qualification continuous3s',lambda s:s['state'][9]==2,12)
     entry['ready_elapsed_s']=time.monotonic()-closed;entry['ready']=ready
     assert entry['ready_elapsed_s']>=2.5
     # A bad input before the real 60s runtime gate must not trigger a fault.
     entry['events'].append(contact(ch,0));early=b.observe('pressure before60',2)
     assert all(not b.rd(faultreg)[0] for _ in range(2)) and b.rd(709)[0]==2
     entry['events'].append(contact(ch,1));entry['early_bad']=early
     while time.monotonic()-on<61:
      assert b.rd(faultreg)[0]==0
      s=b.sample('pressure waiting real60');entry.setdefault('gate_wait',[]).append(s)
      if len(entry['gate_wait'])%20==0:print('PRESSURE REAL WAIT',ch,fanmode,round(time.monotonic()-on,1),flush=True);b.save()
      time.sleep(.7)
     entry['events'].append(contact(ch,0));short=b.observe('pressure short9s',9)
     assert b.rd(faultreg)[0]==0
     entry['events'].append(contact(ch,1));time.sleep(.8)
     entry['events'].append(contact(ch,0));badstart=time.monotonic()
     trip=b.wait('pressure10s trip',lambda s:b.rd(faultreg)[0]==1,15,True)
     entry['fault_after_s']=time.monotonic()-badstart;entry['fault']=trip;entry['short_bad']=short
     assert entry['fault_after_s']>=9.5
     stopped=b.wait('pressure stops fan chain',lambda s:s['state'][9]==0 and not any(s['do'][i] for i in (3,6,8)),15,True)
     entry['stopped']=stopped
     # A pressure contact normally opens when its fan stops. Unlike overload
     # inputs, an open stopped-fan contact cannot prove a persistent fault.
     # First prove the latch survives signal restoration without a reset.
     entry['events'].append(contact(ch,1));time.sleep(2);entry['healthy_no_reset']=b.sample('pressure healthy without reset')
     assert b.rd(faultreg)[0]==1
     entry['events'].append(contact(ch,0));b.reset_faults();time.sleep(.8)
     entry['reset_with_stopped_open_contact']=b.sample('stopped open contact reset')
     entry['reset_allows_new_qualification']=b.rd(faultreg)[0]==0
     if entry['reset_allows_new_qualification']:
      b.wr(398,1);b.wait('retry fan running',lambda s:s['do'][3 if ch==15 else 6]==1,20)
      rows=b.observe('retry still requires pressure qualification',2)
      assert all(s['state'][9]==1 for s in rows) and b.rd(okreg)[0]==0
      entry['unqualified_retry']=rows;b.stop()
     entry['events'].append(contact(ch,1));b.wr(398,0);b.reset_faults();entry['reset_healthy']=b.sample('pressure reset healthy')
     assert b.rd(faultreg)[0]==0
     b.start();entry['restored_running']=b.sample('pressure restored run');b.stop();entry['passed']=True;b.save()
    for cid in ids:b.record(cid,'部分通过',f'V10.52 X{ch}极性模拟，送风手动/自动两档：起机连续3s确认，中断重计；实等60s后9s中断不报，重新连续10s报警停风机链；接点恢复未复位仍锁存；停机开接点复位后的重试仍需起机压差确认，恢复接点后可启动。',
      'BENCH DI极性模拟/软件回读；真实接点、正式10s启动确认、冷热带载和端子待补；停机开接点正常，不作为必须禁止复位的依据',{'runs':alltraces})
  b.log['passed']=True
 except BaseException:b.log['error']=traceback.format_exc();b.save();raise
 finally:b.finish()
 print('FAN PRESSURE COMPLETE',b.path,flush=True)
if __name__=='__main__':main()
