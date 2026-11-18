"""Allocation and defrost lifecycle on the isolated-load control-board bench.

Allocation uses normal protocol settings. Defrost uses legacy HMI command input
simulation because the normal Modbus validator rejects 570/572/573. Lifecycle,
outputs, requests, timers and runtime counters are never overwritten.
"""
import time,traceback,sys
from remaining571_common_20261105 import Bench,now
from run_indoor_bench_20261105 import signed16,BOARDS,I,ConnectHelper
from test_defrost_lifecycle_arm import Firmware
from remaining529_manual_defrost_input_20261105 import manual_defrost

def main():
 b=Bench('529_allocation_defrost');gw_original={}
 def gateway(a,value):
  if a not in gw_original:gw_original[a]=b.rd(a)[0]
  unit=(a-1830)//48;base=1830+unit*48
  end=time.monotonic()+40
  while b.rd(base+43)[0]==1:
   assert time.monotonic()<end,('gateway busy',a);time.sleep(.3)
  before=b.rd(a)[0]
  if before==(value&65535):return
  b.log.setdefault('gateway_writes',[]).append({'at':now(),'address':a,'before':before,'requested':value});b.save()
  b.c.write_single_register(1,a,value&65535);time.sleep(.5)
  end=time.monotonic()+45
  while True:
   actual=b.rd(a)[0];state=b.rd(base+43)[0]
   if actual==(value&65535) and state!=1:break
   assert time.monotonic()<end,('gateway readback',a,value,actual,state)
   time.sleep(.5)
  b.log['gateway_writes'][-1].update({'confirmed_at':now(),'actual':actual,'state':state});b.save()
 def statuses(s):return [x for pair in s['outdoor_status'] for x in pair]
 def observe_count(label,target,timeout=100):
  return b.wait(label,lambda s:sum(x in (2,3,4) for x in statuses(s))==target,timeout)
 def setup():
  b.setup(1);b.config({128:1,127:1,129:1,332:1,315:1,327:1,318:0,319:120,125:0,126:0,
    160:250,161:250,412:1,347:100,348:1,349:0,346:0,365:1,372:350,12:500,248:0})
  b.ntc(0,220);b.ntc(2,0);b.reset_faults()
 def sample(label):
  s=b.sample(label);s['runtime_comp']=b.rd(2602,8);s['runtime_units']=b.rd(2670,4)
  s['defrost']=[b.rd(1550,2),b.rd(1620,2)];s['indoor_EEV_target_actual']=b.rd(1145,16)
  return s
 try:
  if '--resume-after-runtime' not in sys.argv and '--only-defrost' not in sys.argv:
   setup();b.start();entry={'started':now(),'edges':[]};b.log['cases']['allocation_runtime']=entry
   full=observe_count('heat full actual4',4,130);entry['full']=sample('all4');entry['before']=sample('runtime before')
   entry['runtime_hold']=b.observe('actual run runtime20',20);entry['after']=sample('runtime after')
   def total(vals):return [(vals[i]<<16)|vals[i+1] for i in range(0,len(vals),2)]
   delta=[v-u for u,v in zip(total(entry['before']['runtime_comp']),total(entry['after']['runtime_comp']))]
   ud=[v-u for u,v in zip(total(entry['before']['runtime_units']),total(entry['after']['runtime_units']))]
   assert all(18<=x<=24 for x in delta+ud),(delta,ud)
   b.record('T10-022','部分通过',f'两外机各两压机真实运行反馈3，观察20s：各压机累计增量{delta}，外机累计增量{ud}，外机未按两压机重复累计。',
     '软件反馈/时间计数；累计持久化、真实断电、正式档及端子待补',entry)
   for fresh,target,cid in ((30,3,'T10-003'),(60,2,'T10-002'),(90,1,'T10-001')):
    before=sample('target change before');b.ntc(2,fresh);s=observe_count('ambient target'+str(target),target,75)
    assert b.rd(881)[0]==target
    after=sample('target change after')
    b.record(cid,'部分通过',f'当前2外机/4压机：环境制热目标{target}由合法新风校准{fresh/10}℃形成，真实运行反馈达到{target}；卸载前后压机/外机累计已留证。',
       '此轮覆盖4→3→2→1实际卸载；“优先补已运行外机”加载、7199/7200/7201s独立时长差及4外机需另验',{'before':before,'after':after})
   b.ntc(2,120);observe_count('ambient empty actual0',0,75);entry['all_empty']=sample('empty')
   # Status and cumulative runtime travel in separate outdoor poll blocks.
   # Preserve the transition samples, then give those blocks a bounded 10s
   # to converge before testing whether stopped counters keep increasing.
   entry['stop_poll_convergence']=b.observe('stopped runtime poll convergence',10)
   before=sample('stopped runtime before');time.sleep(4);after=sample('stopped runtime after')
   assert before['runtime_comp']==after['runtime_comp'] and before['runtime_units']==after['runtime_units']
   b.record('T10-023','部分通过','新风HRC=12℃空载后两外机压机反馈均0，观察4s压机/外机累计均不再增长。',
     '软件计时；断电保存与正式档待补',{'before':before,'after':after});b.stop()
  if '--only-defrost' not in sys.argv:
   # Disable selection through the real 330->316 gateway, with confirmed mirrors.
   for a,cid in ((1833,'T10-014'),(1832,'T10-015')):
    gateway(a,1);setup();b.start();want=3 if a==1833 else 2
    s=observe_count('disabled allocation'+str(a),want,140);rows=b.observe('disabled stays off',4)
    assert all(statuses(s)[0] not in (2,3,4) and (a!=1832 or statuses(s)[1] not in (2,3,4)) for s in rows)
    symbols=Firmware(str(I/'PSC316_V12.39_BENCH_ONLY_3S.axf')).symbols
    with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[0][1],target_override=BOARDS[0][2],
        options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
     comp_live=list(ss.target.read_memory_block8(symbols['Comp'][0],2))
     assert comp_live[0]==0 and (a!=1832 or comp_live[1]==0),comp_live
    b.record(cid,'部分通过',f'网关{a}=1并核实316镜像后，满载需求下实际剩余{want}台运行；被禁压机反馈允许专用禁用码5，SWD只读Comp={comp_live}确认未运行；未写目标/状态/累计RAM。',
       '两台外机软件反馈，动态禁用已运行设备、反向时长差和物理端子待补',{'running':s,'hold':rows,'Comp_read_only':comp_live})
    b.stop();gateway(a,gw_original[a])
  # Enable a bounded real defrost window using legal outdoor settings.
  for a in (1856,1857,1904,1905):gateway(a,2)
  for shutdown,cid in ((False,'T16-001'),(True,'T16-002')):
   setup();b.start();observe_count('defrost precondition all4',4,140)
   b.wr(540,1);manual_defrost(b,True)
   start=time.monotonic();entry={'started':now(),'shutdown_during_active':shutdown,'samples':[]};b.log['cases'][cid]=entry
   active=b.wait('manual defrost published8',lambda s:b.rd(1550)[0]==8,60)
   entry['active']=sample('defrost8')
   if shutdown:b.wr(398,0)
   else:
    rows=b.observe('defrost active hold',5);entry['active_hold']=rows;manual_defrost(b,False)
   seen7=False;seen0=False;last_print=time.monotonic();recovery_start=None
   end=time.monotonic()+340
   while True:
    s=sample('defrost lifecycle');entry['samples'].append(s);phase=s['defrost'][0][0]
    if phase in (7,8):
     assert all(v==350 for v in s['indoor_EEV_target_actual'][:2]),s
     if not shutdown:assert b.rd(890)[0]==1000
    if phase==7:
     if not seen7:recovery_start=time.monotonic()
     seen7=True
    if seen7 and phase==0:seen0=True
    if seen0 and (not shutdown or s['state'][9]==0):break
    assert time.monotonic()<end,('defrost timeout',cid,s)
    if time.monotonic()-last_print>=20:print('DEFROST WAIT',cid,round(time.monotonic()-start,1),phase,s['state'][9],flush=True);last_print=time.monotonic();b.save()
    time.sleep(.3)
   assert seen7 and seen0
   entry['passed']=True;entry['recovery_observed_s']=time.monotonic()-recovery_start;entry['final']=s;b.save()
   b.record(cid,'部分通过',f'模拟旧HMI手动化霜命令输入后，观察8→7→0；'+('化霜8阶段发正常关机，最终走到停机且负载清零。' if shutdown else '退出命令输入后完成恢复，内阀化霜开度及辅热门禁样本留证。'),
      'HMI命令字RAM模拟，普通Modbus对570/572/573的写入仍被只读校验拦截；BENCH恢复5s；正式60s、物理接点和阀驱动脉冲未测',entry)
   b.stop()
  b.log['passed']=True
 except BaseException:b.log['error']=traceback.format_exc();b.save();raise
 finally:
  try:
   b.wr(398,0)
   for a,v in gw_original.items():gateway(a,v)
   b.log['gateway_restored']={str(a):b.rd(a)[0]==v for a,v in gw_original.items()};b.save()
  finally:b.finish()
 print('ALLOCATION DEFROST COMPLETE',b.path,flush=True)
if __name__=='__main__':main()
