"""Summarize actual evidence without promoting register feedback to terminal tests."""
import json,csv,hashlib
from pathlib import Path
from datetime import datetime
R=Path(__file__).resolve().parents[1];D=R/'.codex-tmp/spec3133_hardware_20261104'
PHASES=[('phase1_fan_valve','风机风阀及手动电压'),('phase2_thermal_r2','制冷制热／再热／预热／加湿'),('phase4_sequences_safety','自动送风／压差／顺序／急停'),('phase6_loaded_shutdown','有负载正常关机'),('phase3_special','消毒／排毒／自动消排毒首轮'),('phase3_connection_recovery','串口中断后停机恢复原参数'),('phase3_special_r2','自动消排毒恢复原模式及中断／零时长补测'),('phase5_reset_matrix','24组ST-Link复位恢复'),('phase7_reheat_routing','独立再热通道及焓差复测'),('phase8_eev_emergency','EEV紧停关闭步数反馈'),('phase9_humidity_heatfault','恒湿冷量偏置及独立热故障／加湿抑制')]
PHASES.insert(8,('phase5_reset_off_r2','先实际正常停机再复位的六模式补测'))
PHASES.insert(9,('phase5_reset_matrix_r3','临时取消油预热等待后补齐复位矩阵'))
PHASES.insert(7,('phase3_boundaries','零时长命令自清及手动中止补测'))
def main():
 records={};detail=[];table=[]
 for name,label in PHASES:
  p=D/(name+'.json')
  if not p.exists():table.append(f'| {label} | 尚未执行 | — | — |');continue
  r=json.loads(p.read_text('utf-8'));records[name]=r
  checks=r.get('checks',[]);count=sum(x['passed'] for x in checks)
  state='已完成' if r.get('finished') else ('中断，见恢复与补测' if r.get('error') else '进行中')
  table.append(f"| {label} | {state} | {count}/{len(checks)} | {'是' if r.get('configuration_restored') else '未完成'} |")
  for i,c in enumerate(checks,1):detail.append({'批次':name,'序号':i,'检查':c['label'],'原始判定':'通过' if c['passed'] else '失败','构建':'330 V10.47 / 316 V12.38 BENCH','证据':str(p.relative_to(R)).replace('\\','/'),'细节':json.dumps(c.get('details'),ensure_ascii=False)})
 with (R/'室内3.1_3.2_3.3_台架复核明细_20261104.csv').open('w',newline='',encoding='utf-8-sig') as fh:
  w=csv.DictWriter(fh,fieldnames=['批次','序号','检查','原始判定','构建','证据','细节']);w.writeheader();w.writerows(detail)
 complete=all(name in records and records[name].get('finished') for name,_ in PHASES if name!='phase3_special')
 finalpath=D/'final_readback.json'
 final=json.loads(finalpath.read_text('utf-8')) if finalpath.exists() else None
 restored=('已完成最终只读核对：'+str(final['original_touched_fields_checked'])+'个触及字段与各字段测试前最早快照一致；'+
  '停机='+str(final['stopped'])+'，软件DO／AO全退='+str(final['outputs_off'])+'，两外机通信健康='+str(final['communication_healthy'])+'。末态证据`final_readback.json`。') if final else '最终全台架快照尚未记录，不能提前宣称现场已恢复。'
 reset_count=len(records.get('phase5_reset_matrix',{}).get('matrix',[]))
 reset_verified=set()
 reset_evidence={}
 for key in ('phase5_reset_matrix','phase5_reset_off_r2','phase5_reset_matrix_r3'):
  rr=records.get(key,{})
  cc={x['label']:x['passed'] for x in rr.get('checks',[])}
  for m in rr.get('matrix',[]):
   label=f"reset mode{m['mode']} allow{m['allow']} intent{m['prior_intent']}"
   if all(cc.get(label+' '+suffix,False) for suffix in ('pre-reset intended state saved','EEPROM retains selected mode and both setpoints','restores run permission correctly')):
    reset_verified.add((m['mode'],m['allow'],m['prior_intent']))
    reset_evidence[(m['mode'],m['allow'],m['prior_intent'])]=key
 with (R/'室内3.2_STLink复位矩阵_20261104.csv').open('w',newline='',encoding='utf-8-sig') as fh:
  cols=['模式','自启164','复位前保存意图166','预期','STLink复位结论','证据','真实断电结论']
  w=csv.DictWriter(fh,fieldnames=cols);w.writeheader()
  for mode in range(6):
   for allow in (0,1):
    for intent in (0,1):
     key=(mode,allow,intent)
     w.writerow(dict(zip(cols,[['制冷','制热','通风','消毒','排毒','自动消排毒'][mode],allow,intent,
      '恢复运行许可，经正常启动流程' if allow and intent else '保持停机',
      '通过' if key in reset_verified else '待补齐／核实',
      reset_evidence.get(key,''),'待测：用户指定真实断电另测'])))
 exceptions=[]
 for name,r in records.items():
  if r.get('error'):exceptions.append(f"- `{name}`：{r['error']}")
  for c in r.get('checks',[]):
   if not c['passed']:exceptions.append(f"- `{name}`／{c['label']}：原始失败保留，须按下文原因及补测判断。")
 text=f'''# 室内3.1、3.2、3.3控制板台架复核

更新时间：{datetime.now().isoformat(timespec='seconds')}。执行状态：{'各批次已执行完，仍须按未测项区分验收范围' if complete else '测试进行中，表格只统计已落盘证据'}。

本轮实际操作COM6及ST-Link；330 V10.47、两块316 V12.38，三板BENCH标识1299=15107。压机动力按用户确认已断开，仅控制板／继电器或模拟负载。没有改固件、没有烧录、没有写RAM强制保护计数。

手动设定通过正常Modbus写入并回读。回风机按**手动AO**测试131=0／50／100，观测DA4=0／500／1000；没有安排回风机自动闭环。温湿度、房压、CO₂等通过临时NTC校准或新AI工程量映射刺激，是真实控制板跑逻辑，**不是物理信号源输入**。DO／AO结果为软件最终输出反馈，未用万用表量端子。

用户已明确3.2暂用ST-Link复位，真实断电另测。复位矩阵仅复位330 MCU，两块316保持供电；只证明330 MCU复位、EEPROM加载及启动许可，不能将其计为24组真实失电来电通过。

本轮已落盘{len(detail)}项控制板观察；ST-Link复位首轮已执行{reset_count}/24组，合并补测后前提和恢复均通过的独立组合为{len(reset_verified)}/24。原始脚本失败与后续核实分别保留，下表不是整机验收通过率。

## 分批结果

分子是原始脚本通过数，分母是检查数；包含脚本预期通道错误，不能直接当整机通过率。详细输入、时刻和反馈见同名明细CSV及原始JSON。

| 批次 | 状态 | 原始通过/检查 | 现场参数恢复 |
|---|---|---|---|
{chr(10).join(table)}

## 必须保留的口径与问题

1. 独立再热（129=0）走**DA9**，共用（129=1）走DA0；预热DA1。第一批热量脚本有两处误按DA0验独立再热，已保留失败原始数据并安排AO、SCR及共用／独立四种组合复测。此处不是通过修改固件消除失败。
2. 首次温度刺激曾尝试超出NTC校准±10℃范围，写入未被接受，已恢复并改用合法范围重跑；失败文件`phase2_thermal.json`保留，不算固件控制失败。当前可达室温22／28／32℃。预热后温度低于10℃这一路无法靠当前热板校准达到，未伪造结果。
3. 热量批次的“post-preheat PID stays off above target”实际带有940=0x80（当时仍是分段预热），该观察只证明**非法配置被抑制**，不算合法PID验收。后续批次另测333=1／374=1、940无0x80时的高温不加热；低温加热仍待物理NTC模拟器。
4. 既有代码核对的工具缺口仍在：Python配置页127=0会清332，阻碍“制冷无再热、热泵有辅热”；回风机手动AO＋送风阀手动AO缺界面拦截（固件940=0x02抑制回风机）。本轮用正常原始参数路径验证控制板，不能称MCGS／Python界面已全部通过。
5. EEPROM旧保存实现非原子快照的问题尚未整改；稳定保存后复位通过，不能否定保存中断时可能出现新温度＋新启停位＋旧模式的离线复现。原证据见`mode_restart_audit_20261104/observations.json`。
6. SCR按已确认一路AO＋两路DO、40／30／30结构；强制热边界仍为WD字面实现，环温恢复仍按暂缓方案。没有改成WDF、没有修改正式时序。
7. 六模式过载紧停时执行负载撤销，**Y05报警继电器仍吸合**；解除并复位后Y05退出。若“除EEV外所有用电设备”连报警输出都要求失电，当前没有按这个字面实现；不能把本次结果写成所有DO均0。
8. 有负载制冷首轮脚本误把30s送风延时起点放在“再热关闭”，原始失败保留。规格起点是**室外机全部关机完成**；只读SWD补测已观察到末台外机风机关闭t≈266.751s、室内送风关闭t≈296.718s，间隔29.967s。加湿退出30s期间原启动请求保留，压机可能在这一阶段完成启动，然后再正常卸载；必须结合外机反馈判定。
9. 同一SWD记录中，热泵带负载停机末台外机风机关闭t≈378.778s，室内送风关闭t≈438.813s，间隔60.035s；压机全停更早，不能把压机最后运行反馈当成室外机完整停机时刻。
10. 首轮消排毒测试已完成消毒／排毒的两种收尾和自动消排毒的结束停机；最后一组自动消排毒恢复原模式在等待期间串口访问中断，原始日志报WriteFile拒绝访问，清理未完成。恢复连接后已正常停机并按原快照恢复参数，证据phase3_connection_recovery；最后一组及零时长／手动中断另见phase3_special_r2。首轮超时不直接判成固件150s逻辑失败，也不能将未采到的收尾补写为通过。
11. 自启屏蔽且保存166=1时，复位后界面398=0、实际停机，但166保留1；此时重复写398=0没有新的关机边沿，不能作为保存关机已建立的证据。首轮随后“allow1／intent0”会记录前提失败；六模式补测通过实际开机→正常关机建立166=0再复位。启用自启前应核对保存意图，不能仅以当前界面显示停机推断下一次复位一定不启。未修改此控制行为。
12. 复位矩阵首轮制热自启被油预热门禁阻挡，软件进入HEATON／HEATOFF（7／8），不是记忆丢失；原脚本等待12s不足。另批phase5_reset_matrix_r3通过正常参数临时设30=0，先确认实际保存的启停意图，再补齐尚未验证的组合；测试后恢复原30值。普通开机主流程自身还有上电30s入口，不把20s记忆消费等同于全部风机立即启动。
13. 自动消排毒恢复原模式补测的完整周期已通过；随后零时长用例中398开机命令在同一扫描被正确清为0，通用参数写入器误按“写1必须读1”报断言。该错误不能判作固件拒写或零时长失效；专批phase3_boundaries允许命令自清，再检查禁用负载及三种特殊模式手动中止，不修改固件。

## 本轮时序范围

普通阀5s／无阀3s、正常压机和风机序列3s、压差确认3s、风机全停后关阀3s使用BENCH口径。特殊模式开阀150s、送风至消毒20s、组合模式中间30s、消毒／排毒1min、加湿器退出等待30s、制冷送风延时30s、制热热源退出30s＋送风延时60s仍按固件真实计时。

正式构建须重新验150／10／30／10／15／60等规定时间；不能拿BENCH的3s作为正式时序通过。已有正式和BENCH最终ARM映像扩展236项检查通过，覆盖两种构建各30种有序模式迁移、999分钟阈值及参数上下限；这些是离线推进时间，不是控制板连续运行999分钟。

## 按规格条款查证据

| 条款 | 本轮证据 | 必须单独保留的边界 |
|---|---|---|
| 3.1通风及冷／热温湿度许可 | phase2、phase9 | 温湿度是合法工程量映射／校准刺激，尚非真实传感器全链；详见每个检查项 |
| 3.1主热／再热／辅热／预热／加湿输出形式 | phase2、phase7、phase9及既有ARM观察 | 所有主热形式及预热形式的满需求／退出已覆盖，不能等同于每条PID曲线、辅热全套化霜周期均实测 |
| 3.1手动AO、风机风阀选择及冲突 | phase1、phase4、phase7 | 手动0／5／10V为设定与软件输出对应；端子电压、MCGS输入框及工具已知缺陷分别记录 |
| 3.2记忆状态／模式／冷热设定和自启许可 | phase5、保存中断ARM观察 | 24组是ST-Link复位；真实断电另测；保存中断已有非原子反例 |
| 3.3通风启停、风机先开后关、压差确认 | phase1、phase4 | 压差通过正常极性参数使输入有效／无效，保留过滤，未实际操作压差开关；BENCH时序不等同正式 |
| 3.3制冷／制热正常停机 | phase6及SWD补采 | 先退加湿、热源、外机，末台外机风机停后吹扫30／60s；原脚本时间起点错误保留 |
| 3.3消毒／排毒／自动消排毒 | phase3、扩展ARM矩阵 | 完整真实一分钟周期两种收尾；全部30种模式迁移为ARM验证，未在控制板穷举30次 |
| 3.3紧急停机及EEV关闭 | phase4、phase8 | 操作负载撤销，报警继电器Y05保持报警；EEV为软件步数反馈，线圈脉冲和机械归零未实测 |

## 原始失败及异常

{chr(10).join(exceptions) if exceptions else '已落盘批次暂无原始失败；尚未完成的批次不据此判定。'}

## 尚不能签为整节完全验收

- 真实断电／来电、保存中断的现场试验，按用户要求另测。
- DO接点和AO端子0／5／10V的仪表实测、执行器实际动作及MCGS界面联动。
- 预热后低温PID、真实传感器断线／短路、现场消防及所有外部联锁组合；本轮逻辑注入与离线证据不得替代这些输入测试。
- 全部设备组合与所有中断阶段尚须逐行核对原242条清单；本轮明细是已执行观察，不把242行一律改成通过。
- 正式固件实际时间及有动力的整机运行。

## 收尾与证据

每批正常停机后恢复本批触及的配置／校准并回读；随后通过当前AXF解析的Old_Parameter保存影子和AI配置journal影子／dirty标志核对保存状态，不使用旧版本绝对地址。原始JSON标明恢复是否完成。最终全台架快照须另记录，测试未完前不提前宣称现场已恢复。

{restored}

证据目录：`.codex-tmp/spec3133_hardware_20261104/`；明细：`室内3.1_3.2_3.3_台架复核明细_20261104.csv`；扩展ARM代码：`tools/test_modes_restart_matrix_20261104.py`。
'''
 (R/'室内3.1_3.2_3.3_台架复核结果_20261104.md').write_text(text,'utf-8')
 print('Evidence report updated:',len(detail),'observations; all phases complete=',complete)
if __name__=='__main__':main()
