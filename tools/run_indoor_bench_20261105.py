"""Authorized isolated-load BENCH flash and incremental test evidence.

Uses normal Modbus configuration for stimulation. No RAM protection pokes.
Run only one action at a time: preflight / flash / health / fans.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,re,struct,sys,time,traceback,os
from datetime import datetime,timezone,timedelta
from pathlib import Path

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/内机实测_20261105/BENCH_V1048_V1238'
D.mkdir(parents=True,exist_ok=True)
I=R/'.codex-tmp/fan_enable_v1048_v1238_20261104/BENCH_ONLY_3S'
sys.path.insert(0,str(R/'psc330_monitor_tool/psc330_monitor'))
sys.path.insert(0,str(R/'tools'))
from app import ModbusRtuClient,DEFAULT_BAUD,signed16
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from verify_board_flash_vs_hex import parse_hex,blocks_of

BOARDS=[('316_WJ1','56FF6E065067545548562587','stm32f103rc',0x414,256*1024,64*1024,'PSC316_V12.38_BENCH_ONLY_3S'),
 ('316_WJ2','30FF71064E4B323247481843','stm32f103rc',0x414,256*1024,64*1024,'PSC316_V12.38_BENCH_ONLY_3S'),
 ('330','50FF73067289515145451367','stm32f407ze',0x413,512*1024,128*1024,'PSC330_V10.48_BENCH_ONLY_3S')]
EXPECTED=[330,10,48,2026,11,4,316,12,38,2026,11,4,316,12,38,2026,11,4]
CASECSV=R/'内机明日全部待测复测用例_20261105.csv'
REPORT=R/'内机测试版逐项测试记录_20261105.md'
RESULTS=D/'case_results.json'
# Opt-in new runs keep old journals immutable and retain per-case history.
if os.environ.get('PSC_BENCH_PACKAGE'):
 I=R/os.environ['PSC_BENCH_PACKAGE']/'BENCH_ONLY_3S'
 D=R/'测试证据/内机实测_20261105/BENCH_V1049_V1239';D.mkdir(parents=True,exist_ok=True)
 BOARDS=[tuple(list(b[:-1])+[b[-1].replace('12.38','12.39').replace('10.48','10.49')]) for b in BOARDS]
 EXPECTED=[330,10,49,2026,11,5,316,12,39,2026,11,5,316,12,39,2026,11,5]
 RESULTS=D/'case_results.json'
 old=R/'测试证据/内机实测_20261105/BENCH_V1048_V1238/case_results.json'
 if not RESULTS.exists() and old.exists():RESULTS.write_bytes(old.read_bytes())


# Explicit indoor-only follow-up: retain original journals and unchanged outdoor image.
if os.environ.get('PSC_BENCH_INDOOR_VERSION'):
 assert os.environ.get('PSC_BENCH_PACKAGE'), 'Select the exact built package'
 version=os.environ['PSC_BENCH_INDOOR_VERSION'];major,minor=map(int,version.split('.'))
 previous_results=RESULTS
 D=R/f'测试证据/内机实测_20261105/BENCH_V{major}{minor:02d}_V1239';D.mkdir(parents=True,exist_ok=True)
 BOARDS[2]=tuple(list(BOARDS[2][:-1])+[f'PSC330_V{version}_BENCH_ONLY_3S'])
 EXPECTED[1:3]=[major,minor]
 RESULTS=D/'case_results.json'
 if not RESULTS.exists() and previous_results.exists():RESULTS.write_bytes(previous_results.read_bytes())

def now():return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
def replace_retry(src,dst):
 for attempt in range(20):
  try:src.replace(dst);return
  except PermissionError:
   if attempt==19:raise
   time.sleep(.1)
def dump(p,data):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');replace_retry(tmp,p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def client():
 c=ModbusRtuClient();c.open('COM6',DEFAULT_BAUD);return c
def result(case,status,actual,evidence,restored='',inputs=''):
 data=json.loads(RESULTS.read_text('utf-8')) if RESULTS.exists() else {}
 prior=data.get(case);history=(prior.get('history',[])+[{k:v for k,v in prior.items() if k!='history'}]) if prior else []
 data[case]={'status':status,'actual':actual,'evidence':str(evidence.relative_to(R)).replace('\\','/'),'restored':restored,'inputs':inputs,'at':now(),'history':history}
 dump(RESULTS,data)
 with CASECSV.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f));fields=list(rows[0])
 matches=[r for r in rows if r['用例编号']==case];assert len(matches)==1,case
 row=matches[0];row.update({'执行结论':status,'实际结果':actual,'证据文件及时间戳':data[case]['evidence']+' @ '+data[case]['at'],
  '恢复回读结果':restored,'测试输入实测值':inputs,'执行人及时间':'Codex @ '+data[case]['at'],
  '本次版本及SHA256':f'330 V10.{EXPECTED[2]} / 316 V12.{EXPECTED[8]} BENCH；逐板HEX哈希见{D.relative_to(R)}/flash.json'})
 temp=CASECSV.with_suffix('.csv.tmp')
 with temp.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 replace_retry(temp,CASECSV)
 lines=['# 内机测试版逐项测试记录（2026-11-05）','',
  '控制板、继电器/模拟负载；压机动力按用户确认已隔离。软件输出回读不等于物理端子测量。',
  '以下勾选代表执行完该次检查；只有“通过”代表该例所需证据完整，“部分通过”仍有验收缺口。',
  '','|执行|用例|结论|本次实际结果|恢复/剩余缺口|证据|','|---|---|---|---|---|---|']
 for cid,v in sorted(data.items()):
  esc=lambda s:str(s).replace('|','／').replace('\n',' ')
  lines.append(f"|[x]|{cid}|{esc(v['status'])}|{esc(v['actual'])}|{esc(v['restored'])}|[{cid}]({v['evidence']})|")
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
 plan=R/'明日实机验证方案_内机3.1-3.11_20261105.md'
 content=plan.read_text(encoding='utf-8');start='<!-- BENCH_EXECUTION_START -->';end='<!-- BENCH_EXECUTION_END -->'
 counts={s:sum(v['status']==s for v in data.values()) for s in ('通过','部分通过','失败','环境受限','按用户要求保留')}
 progress=start+'\n## 测试版执行进度（实时更新）\n\n'+f"更新时间：{now()}。已记录{len(data)}例：通过{counts['通过']}、部分通过{counts['部分通过']}、失败{counts['失败']}、环境受限{counts['环境受限']}、按用户要求保留{counts['按用户要求保留']}。勾选表示已执行，不把部分通过当完整验收通过；不同版本证据按逐项链接区分。\n\n"
 progress+='[逐项勾选、结果与证据](内机测试版逐项测试记录_20261105.md)；所有原始失败及复测历史保存在同目录case_results.json。\n\n'
 progress+='\n'.join(f"- [x] {cid}：{v['status']}" for cid,v in sorted(data.items()))+'\n'+end
 if start in content:content=re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda m:progress,content,flags=re.S)
 else:
  head,sep,rest=content.partition('\n');content=head+'\n\n'+progress+'\n'+rest
 plan.write_text(content,encoding='utf-8')
 print('RECORDED',case,status,actual,flush=True)

def snap(c):
 rd=lambda a,n=1:c.read_holding_registers(1,a,n)
 return {'at':now(),'state':rd(700,11),'do':rd(814,8)+rd(1366,8),'ao':rd(914,10),
  'outdoor_status':[rd(1555,2),rd(1625,2)],'outdoor_xy':[rd(1600),rd(1670)],'conflict':rd(940),'faults':rd(594,33)}

def loads_off(s):
 # Y05 is the alarm contact, not an actuator. Keep it asserted and documented
 # when the bench's unfitted outdoor pressure transmitters report faults.
 return not any(v for i,v in enumerate(s['do']) if i!=5) and not any(s['ao'])

def preflight():
 p=D/'preflight.json';assert not p.exists(),'Preserve previous run; use existing snapshot'
 c=client()
 try:
  data={'at':now(),'port':'COM6','baud':DEFAULT_BAUD,'compressor_power_isolated_user_confirmed':True,
   'probes':[{'uid':q.unique_id,'description':q.description} for q in ConnectHelper.get_all_connected_probes(blocking=False)],
   'versions_before':c.read_holding_registers(1,2622,18),'config':{},'snapshot':snap(c),'artifacts':{},'sources':{}}
  for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)]:
   data['config'].update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
  assert data['snapshot']['state'][9]==0 and c.read_holding_registers(1,398,1)==[0],'Normal stop required'
  assert loads_off(data['snapshot']),'Nonzero load outputs before flash'
  data['alarm_contact_before']=data['snapshot']['do'][5]
  data['outdoor_alarm_words_before']=[c.read_holding_registers(1,1601,8),c.read_holding_registers(1,1671,8)]
  manifest=json.loads((I/'manifest.json').read_text('utf-8'))
  for name,want in manifest['artifacts'].items():
   actual=sha(I/name);assert actual==want,(name,actual,want);data['artifacts'][name]=actual
  change=json.loads((I.parent/'change_manifest.json').read_text('utf-8'))
  for name,want in change['changed_common_sources'].items():
   actual=sha(R/name);data['sources'][name]={'current_sha256':actual,'built_sha256':want,'same':actual==want}
   assert actual==want,('Source changed since build; rebuild required',name)
  expected={x[1] for x in BOARDS};assert expected.issubset({x['uid'] for x in data['probes']})
  dump(p,data);print('PREFLIGHT OK',data['versions_before'],flush=True)
 finally:c.close()

def flash():
 assert (D/'preflight.json').exists()
 p=D/'flash.json';assert not p.exists(),'Flash journal already exists; inspect before resume'
 report={'started':now(),'profile':'BENCH_ONLY_3S','boards':[],'physical_terminal_measurement':False};dump(p,report)
 for label,uid,target,device,flash_size,ram_size,stem in BOARDS:
  image=I/(stem+'.hex');image_mem=parse_hex(image)
  entry={'board':label,'probe_uid':uid,'target':target,'image':str(image.relative_to(R)),
   'sha256':sha(image),'started':now(),'flash_verified':False};report['boards'].append(entry);dump(p,report)
  print('BACKUP',label,uid,flush=True)
  with ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override=target,
   options={'connect_mode':'attach','resume_on_disconnect':False,'frequency':1000000}) as ss:
   t=ss.target;assert t.read32(0xE0042000)&0xfff==device;t.halt()
   programming_started=False
   reg,bits=(0xE0042004,0x300) if device==0x414 else (0xE0042008,0x1800)
   old_debug=t.read32(reg)
   try:
    for suffix,addr,size in [('flash',0x08000000,flash_size),('sram',0x20000000,ram_size)]:
     dst=D/(label+'_before_'+suffix+'.bin');assert not dst.exists();dst.write_bytes(bytes(t.read_memory_block8(addr,size)))
     entry[suffix+'_backup']={'path':dst.name,'size':size,'sha256':sha(dst)};dump(p,report)
    t.write32(reg,old_debug|bits);t.reset_and_halt();t.write32(reg,t.read32(reg)|bits)
    print('PROGRAM',label,flush=True);programming_started=True
    FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(image))
    for start,end in blocks_of(image_mem):
     for addr in range(start,end,4096):
      n=min(4096,end-addr)
      assert bytes(t.read_memory_block8(addr,n))==bytes(image_mem[addr+i] for i in range(n)),(label,hex(addr))
    entry.update({'flash_verified':True,'verified_bytes':len(image_mem),'finished':now()});dump(p,report)
    t.write32(reg,old_debug);t.reset();print('FLASH VERIFIED',label,len(image_mem),flush=True)
   except BaseException:
    entry['error']=traceback.format_exc();dump(p,report)
    if not programming_started:t.write32(reg,old_debug);t.resume()
    raise
 report['finished']=now();dump(p,report)
 c=client()
 try:
  end=time.monotonic()+30
  while True:
   try:
    versions=c.read_holding_registers(1,2622,18)
    if versions==EXPECTED:break
   except Exception:versions=[]
   assert time.monotonic()<end,('Post-flash version mismatch',versions)
   time.sleep(.5)
  report['versions_after']=versions;report['profile_after']=c.read_holding_registers(1,1298,2)
  assert report['profile_after'][1]==15107
  report['snapshot_after']=snap(c);assert report['snapshot_after']['state'][9]==0
  dump(p,report)
 finally:c.close()
 result('T01-005','通过',f'三板测试版已烧录；HEX全部有效字节逐字节回读一致；330 10.{EXPECTED[2]}、两316 12.{EXPECTED[8]}、1299=15107',p,
  '保留BENCH供本轮测试；尚未恢复正式版。此例只确认构建/烧录，不确认所有功能符合')
 result('T01-002','部分通过','烧前已停机，备份330参数0~499和新AI配置；三板Flash/SRAM完整原值已保存并有SHA256',p,
  '原配置见preflight.json；外部EEPROM物理镜像及独立恢复演练未完成')

def health():
 p=D/'health120s.json';assert not p.exists()
 c=client();data={'started':now(),'reads':[],'errors':[],'duration_required_s':120};start=time.monotonic();last=-30
 try:
  while time.monotonic()-start<120:
   try:
    data['reads'].append({'elapsed':round(time.monotonic()-start,3),'versions':c.read_holding_registers(1,2622,18),
     'profiles':c.read_holding_registers(1,1298,2),'snapshot':snap(c)})
   except Exception as e:data['errors'].append({'elapsed':time.monotonic()-start,'error':repr(e)})
   if time.monotonic()-start-last>=20:
    dump(p,data);print('HEALTH',round(time.monotonic()-start,1),'reads',len(data['reads']),'errors',len(data['errors']),flush=True);last=time.monotonic()-start
   time.sleep(.3)
  data['elapsed_s']=time.monotonic()-start;data['finished']=now();dump(p,data)
  ok=not data['errors'] and all(r['versions']==EXPECTED and not any(r['snapshot']['faults']) for r in data['reads'])
  result('T01-001','通过' if ok else '失败',f"三板身份/档位持续回读{data['elapsed_s']:.1f}s，共{len(data['reads'])}组，串口异常{len(data['errors'])}次；逐样本记录外机状态/故障",p,
   '此项为当前通信及身份检查，端子原状仍只有软件回读')
 finally:c.close()

class ControlBench:
 def __init__(self,name='fan_batch'):
  self.c=client();self.original={};self.touched=set();self.path=D/(name+'_'+datetime.now().strftime('%H%M%S')+'.json')
  assert not self.path.exists(),'Inspect prior batch rather than overwrite'
  assert self.c.read_holding_registers(1,2622,18)==EXPECTED
  assert self.c.read_holding_registers(1,1299,1)==[15107]
  self.log={'started':now(),'sensor_stimulus':'Normal parameter writes; no raw engineering output/RAM writes',
   'physical_terminal_measurement':False,'original':self.original,'writes':[],'samples':[],'cases':{}}
  # Serial and the outdoor version cache may become available before the
  # indoor AI journal loads (it deliberately starts after six seconds).
  sy=axf_symbols();self.log['boot_readiness']=[]
  with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
   options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
   end=time.monotonic()+30
   while True:
    ready={'at':now(),'ai_loaded':ss.target.read8(sy['IndoorAiCfgLoaded'][0]),'eeprom_state':ss.target.read8(sy['eepromtt'][0])}
    self.log['boot_readiness'].append(ready)
    if ready['ai_loaded']==1 and ready['eeprom_state']==3:break
    assert time.monotonic()<end,('Board startup not complete',ready)
    time.sleep(.25)
  self.save()
 def save(self):dump(self.path,self.log)
 def rd(self,a,n=1):return self.c.read_holding_registers(1,a,n)
 def wr(self,a,value):
  if a not in self.touched:self.original[str(a)]=self.rd(a)[0];self.touched.add(a)
  self.c.write_single_register(1,a,value&65535);actual=self.rd(a)[0]
  self.log['writes'].append({'at':now(),'address':a,'value':value,'readback':actual})
  if a not in (398,524):assert actual==value&65535,(a,value,actual)
  self.save()
 def config(self,values):
  for a,v in values.items():
   if self.rd(a)[0]!=v&65535:self.wr(a,v)
 def snapshot(self,label):
  s=snap(self.c);s['label']=label;s['monotonic']=round(time.monotonic(),3)
  s['fan_manual_131_134']=self.rd(131,4);s['fan_config_329_342']=self.rd(329,14);s['mode_1_236']=[self.rd(1)[0],self.rd(236)[0]]
  self.log['samples'].append(s);return s
 def wait(self,label,predicate,timeout,allow_fault=False):
  start=time.monotonic();last=None
  while True:
   s=self.snapshot(label)
   key=(tuple(s['state']),tuple(s['do']),tuple(s['ao']))
   if key!=last:print(label,round(time.monotonic()-start,1),'sys/step',s['state'][0],s['state'][9],'DO',s['do'],'AO',s['ao'],flush=True);last=key;self.save()
   if not allow_fault:assert not any(s['faults']),(label,'fault',s)
   if predicate(s):self.save();return s
   assert time.monotonic()-start<timeout,(label,'timeout',s)
   time.sleep(.2)
 def stop(self):
  self.wr(398,0)
  return self.wait('normal stop',lambda s:s['state'][9]==0,180,True)
 def baseline(self,mode):
  self.stop()
  self.config({163:0,164:0,236:mode,125:0,126:0,127:0,128:0,129:0,
   320:0,328:0,132:0,135:0,329:2,330:2,331:1,332:0,333:0,334:0,
   335:0,336:0,337:0,338:0,381:0,382:0,386:0,315:0,327:0,
   160:320,161:150,248:0,168:0,134:50,131:50})
 def finish(self):
  try:
   final=self.stop();assert loads_off(final),final
   for a in sorted(self.touched):
    if a not in (398,236,164):self.c.write_single_register(1,a,self.original[str(a)])
   for a in (236,164):
    if a in self.touched:self.c.write_single_register(1,a,self.original[str(a)])
   self.c.write_single_register(1,398,0)
   mismatch={str(a):[self.original[str(a)],self.rd(a)[0]] for a in self.touched if a!=398 and self.original[str(a)]!=self.rd(a)[0]}
   self.log['restore_mismatches']=mismatch;self.log['restored']=not mismatch;assert not mismatch,mismatch
   self.log['final_snapshot']=snap(self.c);self.log['finished']=now();self.save()
  except BaseException:self.log['cleanup_error']=traceback.format_exc();self.save();raise
  finally:self.c.close()

def fans():
 b=ControlBench()
 try:
  # Ventilation first: six tests that do not require outdoor load permissions.
  for mode in (2,0,1):
   for fan,reg,ch,do in [('送风',134,7,3),('回风',131,4,6)]:
    for raw in (0,50,100):
     cid=f"T02-{mode*6+(0 if fan=='送风' else 3)+(raw//50)+1:03d}"
     prior=json.loads(RESULTS.read_text('utf-8')) if RESULTS.exists() else {}
     if prior.get(cid,{}).get('status')=='部分通过':
      print('ALREADY RECORDED',cid,'continue remaining cases',flush=True);continue
     entry={'started':now(),'mode':mode,'fan':fan,'manual_raw':raw,'checks':[]}
     b.log['cases'][cid]=entry;b.save();print('CASE START',cid,fan,raw,flush=True)
     try:
      b.baseline(mode);b.wr(reg,raw);b.wr(398,1)
      s=b.wait(cid+' running',lambda s:s['state'][9]==2 and s['ao'][ch]==raw*10 and s['do'][do]==1,60)
      hold_start=time.monotonic();samples=[]
      while time.monotonic()-hold_start<20:
       s=b.snapshot(cid+' hold20s');samples.append(s)
       assert s['ao'][ch]==raw*10 and s['do'][do]==1,(cid,'unstable AO/DO',s)
       assert not any(s['faults']),(cid,'fault',s)
       time.sleep(.5)
      entry['hold_seconds']=time.monotonic()-hold_start;entry['held_sample_count']=len(samples)
      stopped=b.stop();assert stopped['ao'][ch]==0 and stopped['do'][do]==0,(cid,'stop output remains',stopped)
      entry.update({'software_checks_passed':True,'finished':now()});b.save()
      result(cid,'部分通过',f"BENCH参数{reg}={raw}；运行软件DA{ch}={raw*10}、DO索引{do}=1，连续{entry['hold_seconds']:.1f}s稳定；正常停机两路清0",b.path,
       '本例已正常停止；物理AO端子电压、继电器接点独立测量待补；正式版回归待测',f'模式236={mode}；寄存器{reg}={raw}（参数刺激，非物理信号源）')
     except BaseException:
      entry.update({'software_checks_passed':False,'error':traceback.format_exc(),'finished':now()});b.save()
      infrastructure=any(x in entry['error'] for x in ('PermissionError','SerialException','ModbusError'))
      result(cid,'未执行' if infrastructure else '失败',entry['error'].splitlines()[-1],b.path,
       '测试环境中断，不能据此判固件失败；正在正常停止和恢复' if infrastructure else '保留原始异常，正在正常停止和恢复')
      raise
 finally:b.finish()
 # Backfill the per-case cleanup after the final independent restoration read.
 for cid,v in b.log['cases'].items():
  if v.get('software_checks_passed'):
   result(cid,'部分通过',f"BENCH {v['fan']}手动{v['manual_raw']/10:g}V：软件AO/DO连续{v['hold_seconds']:.1f}s及正常关闭通过",b.path,
    '本批已停机并逐项恢复配置、回读无差异；物理端子及正式版回归待测',f"模式236={v['mode']}；手动原始值{v['manual_raw']}")

def axf_symbols():
 sys.path.insert(0,str(R/'.codex-tmp/defrost_test_deps'))
 from elftools.elf.elffile import ELFFile
 out={}
 with (I/(BOARDS[2][-1]+'.axf')).open('rb') as f:
  elf=ELFFile(f)
  for s in elf.get_section_by_name('.symtab').iter_symbols():
   if s.name and (s.name not in out or s['st_info']['bind']=='STB_GLOBAL'):out[s.name]=(s['st_value'],s['st_size'])
 if 'IndoorParameterSaveState' in out:
  out['EEpflag']=out['IndoorParameterSaveState']
  out['t']=out['IndoorParameterSaveIndex']
 return out

def parameters():
 b=ControlBench('scalar_parameters');sy=axf_symbols()
 try:
  b.stop();b.config({164:0})
  with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
   options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
   tables={name:list(struct.unpack('<500h',bytes(ss.target.read_memory_block8(sy[name][0],1000)))) for name in ('Parameter_min','Parameter_max','Parameter_def')}
  b.log['tables']=tables;b.log['table_symbols']={name:sy[name] for name in tables};b.save()
  with CASECSV.open(encoding='utf-8-sig',newline='') as f:requirements=[r for r in csv.DictReader(f) if r['大组']=='T07' and re.match(r'参数\[\d+\]',r['测试名称'])]
  for req in requirements:
   cid=req['用例编号'];a=int(re.search(r'参数\[(\d+)\]',req['测试名称'])[1])
   m=re.search(r'默认(-?\d+)，合法\[(-?\d+),(-?\d+)\]',req['参数及前置状态']);default,low,high=map(int,m.groups())
   entry={'address':a,'name':req['测试名称'],'required':[low,high,default],
    'actual_table':[tables['Parameter_min'][a],tables['Parameter_max'][a],tables['Parameter_def'][a]],'attempts':[]}
   b.log['cases'][cid]=entry
   if a not in b.touched:b.original[str(a)]=b.rd(a)[0];b.touched.add(a)
   for value in (low,high,default,low-1,high+1):
    before=b.rd(a)[0]
    try:b.c.write_single_register(1,a,value&65535);error=None
    except Exception as e:error=repr(e)
    actual=b.rd(a)[0]
    entry['attempts'].append({'requested':value,'before':signed16(before),'actual':signed16(actual),'error':error})
    if low<=value<=high:
     if error or actual!=value&65535:entry.setdefault('failures',[]).append('合法值拒写/未生效:'+str(value))
    elif error is None and not low<=signed16(actual)<=high:
     entry.setdefault('failures',[]).append('规格外值仍生效:'+str(value))
   # Never leave an intentionally out-of-range request as the operating value.
   b.c.write_single_register(1,a,default&65535)
   if entry['actual_table']!=entry['required']:entry.setdefault('failures',[]).append('默认或范围表与规格不同')
   b.save();print('PARAMETER',cid,a,'table',entry['actual_table'],'failures',entry.get('failures',[]),flush=True)
   result(cid,'失败' if entry.get('failures') else '部分通过',
    ('；'.join(entry['failures']) if entry.get('failures') else 'AXF匹配板上默认/范围表与协议合法、越界写入检查通过')+f"；参数{a}实际min/max/default={entry['actual_table']}",b.path,
    '本项协议检查已执行；MCGS/Python界面及统一复位保存回读待本批完成',req['参数及前置状态'])
  # Save shadow must match all final default values before an ST-Link reset.
  a,size=sy['Old_Parameter'];assert size==1000,(a,size)
  with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
   options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
   end=time.monotonic()+20
   while True:
    values=struct.unpack('<500H',bytes(ss.target.read_memory_block8(a,1000)))
    mismatch={str(v['address']):[b.rd(v['address'])[0],values[v['address']]] for v in b.log['cases'].values() if b.rd(v['address'])[0]!=values[v['address']]}
    if not mismatch:break
    assert time.monotonic()<end,mismatch;time.sleep(.2)
   b.log['saved_shadow_matches']=True;b.save();ss.target.reset()
  end=time.monotonic()+15
  while True:
   try:b.rd(709);break
   except Exception:
    assert time.monotonic()<end;time.sleep(.3)
  for cid,v in b.log['cases'].items():
   actual=signed16(b.rd(v['address'])[0]);v['reset_readback']=actual
   if actual!=v['required'][2]:v.setdefault('failures',[]).append('默认值复位后不符:'+str(actual))
  b.save()
 finally:b.finish()
 for cid,v in b.log['cases'].items():
  result(cid,'失败' if v.get('failures') else '部分通过',
   ('；'.join(v['failures']) if v.get('failures') else '默认/范围表、协议合法及越界检查、ST-Link复位后默认值回读通过')+f"；min/max/default={v['actual_table']}，复位读回{v.get('reset_readback')}",b.path,
   '本批原参数全部恢复并逐项回读一致；实际MCGS/Python界面验收及真实掉电未测；ST-Link复位不是断电')

def valves():
 b=ControlBench('valve_batch')
 try:
  for idx,(name,reg,ao,do,manual) in enumerate([('新风',335,3,12,380),('送风',336,7,4,130),('回风',337,4,7,449),('排风',338,6,9,None)]):
   for output in (0,1,2):
    cid=f'T07-{16+idx*3+output:03d}';entry={'name':name,'type':output,'points':[]};b.log['cases'][cid]=entry
    print('CASE START',cid,name,output,flush=True)
    b.baseline(2);b.config({329:1,330:0,331:1,reg:output,135:0,377:2,380:0})
    if name=='排风' and output==2:
     b.config({335:2,377:1})
     for ch,value in [(1,500),(4,500),(2,2000)]:
      base=1229+12*ch;b.config({base:1,base+4:value,base+5:value,base+6:value,base+7:value,base+8:0})
     entry['stimulus']='AI1/AI4=50%RH及AI2=2000ppm为合法工程量映射模拟，非物理信号源'
    b.wr(398,1);b.wait(cid+' running',lambda s:s['state'][9]==2,30)
    for value in ((0,50,100) if manual is not None else (None,)):
     if value is not None:b.wr(manual,value)
     if output==2 and manual is not None:
      expected_ao=value*10;expected_do=0
     elif output==1:expected_ao=0;expected_do=1
     elif output==0:expected_ao=0;expected_do=0
     else:expected_ao=None;expected_do=0
     s=b.wait(cid+' point '+str(value),lambda s:s['do'][do]==expected_do and
      (s['ao'][ao]==expected_ao if expected_ao is not None else s['ao'][ao]==s['ao'][3] and s['ao'][3]>0),8)
     entry['points'].append({'raw_manual':value,'snapshot':s});b.save()
    stopped=b.stop();assert stopped['ao'][ao]==0 and stopped['do'][do]==0,(cid,stopped)
    entry['normal_stop_passed']=True;b.save()
    result(cid,'部分通过',f"{name}阀类型{output}：软件输出选择、{('0/5/10V' if manual is not None else '跟随/开关')}及正常关闭检查通过",b.path,
     '物理阀端子、异常停机与实际保持时间待补；本批结束恢复原配置',entry.get('stimulus','正常参数手动输入'))
 finally:b.finish()
 for cid,v in b.log['cases'].items():
  if v.get('normal_stop_passed'):
   result(cid,'部分通过',f"{v['name']}阀类型{v['type']}：所选软件DO/AO、各点及正常关闭符合",b.path,
    '原配置已逐项恢复回读无差异；物理端子、异常停机与时序仍待测',v.get('stimulus','正常参数手动输入'))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['preflight','flash','health','fans','parameters','valves']);args=parser.parse_args()
 globals()[args.action]()
