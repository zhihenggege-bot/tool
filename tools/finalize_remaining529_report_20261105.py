"""Consolidated report, only after hardware queue and independent audit finish."""
import collections,csv,json
from run_indoor_bench_20261105 import D,R,RESULTS,now

def main():
    queue=json.loads((D/'remaining529_HP_resumed_batches.json').read_text('utf8'))
    assert len(queue['batches'])==4 and all(v['exit_code']==0 for v in queue['batches']),queue
    auditpath=max(D.glob('independent_audit_*.json'),key=lambda p:p.stat().st_mtime)
    audit=json.loads(auditpath.read_text('utf8'))
    assert audit.get('reset_requested') and not audit.get('audit_error'),auditpath
    for key in ('differences_from_preflight','parameter_shadow_mismatches','ai_shadow_mismatches','after_reset_differences_from_preflight'):
        assert not audit[key],(auditpath,key,audit[key])
    summary=json.loads((D/'remaining529_coverage_summary.json').read_text('utf8'))
    data=json.loads(RESULTS.read_text('utf8'))
    for cid in ('T13-007','T13-008','T13-009','T13-010'):
        assert data[cid]['status']=='部分通过' and '四压机运行反馈已建立' in data[cid]['actual'],(cid,data[cid])
    rows=list(csv.DictReader((R/'剩余529例执行覆盖与未测清单_20261105.csv').open(encoding='utf-8-sig',newline='')))
    assert len(rows)==529
    cycles=max(D.glob('remaining571_529_cycles_soak_*.json'),key=lambda p:p.stat().st_mtime)
    run=json.loads(cycles.read_text('utf8'))
    assert run.get('passed') and run.get('restored') and not run.get('cleanup_error'),cycles
    cycle=run['cases']['T13-063'];soak=run['cases']['T13-064']
    assert cycle['passed'] and len(cycle['runs'])==30 and all(r['passed'] for r in cycle['runs'])
    assert soak['passed'] and soak['elapsed_s']>=7200
    pending=[r for r in rows if r['本批证据层级']=='未执行']
    counts=summary['pending_scope_evidence_counts']
    totalchecks=summary['checks_in_matrices']
    statuses=collections.Counter(v['status'] for v in data.values())
    lines=['# 剩余529例复核结果（2026-11-05）','',f'更新时间：{now()}。已结束本轮执行并完成参数恢复及ST-Link复位终检。',
       '', '当前板上保持330 V10.52 BENCH、两块316 V12.39 BENCH。正式/BENCH同源修复已构建；本轮没有切换正式版实板验时。',
       '', '## 529例的实际覆盖','',
       '|证据层级|例数|含义|','|---|---:|---|',
       f'|板上软件检查|{counts.get("板上软件检查/范围见证据",0)}|见逐项范围，部分通过仍有物理/正式时序缺口|',
       f'|仅ARM离线|{counts.get("仅ARM离线",0)}|当前链接镜像、模拟输入/时钟，不等于实机通过|',
       f'|未执行|{counts.get("未执行",0)}|逐项保留操作、条件和缺口|','',
       f'完整总表累计记录{len(data)}例，状态为{dict(statuses)}；其中包含529范围以外的此前记录。矩阵中{totalchecks}条检查不是同等数量的独立验收用例，不能说529例全部通过。',
       '', '[529例覆盖和未测清单](剩余529例执行覆盖与未测清单_20261105.csv)；[全部逐项记录](内机测试版逐项测试记录_20261105.md)。',
       '', '## 用户指定项目','',
       '|项目|本次结果与边界|','|---|---|',
       '|风量/风压目标0|V10.52板上不再回退旧294/310目标，反馈目标保持0；自动风机仍受有效最小电压约束，并非目标0就强制停风机|',
       '|最小电压大于最大|V10.52板上最小9V/最大3V时按有效最大=最小输出9V；两处夹限一致；未改存储参数值；手动0/5/10V回归符合|',
       '|无效混风阀组合|5组板上软件检查：仅新风AO+CO2焓差时互补和1000；无新风/DO/房压/手动组合均抑制混风AO|',
       '|预热已输出后的X07|V10.51已建立预热AO后测加湿AO/DO两类；短脉冲、持续切断、锁存及健康复位恢复符合。后续V10.52只改送风目标/夹限及版本，未改热保护；不冒称本例重新在V10.52执行|',
       '|消毒/排毒/组合完整流程|6个完整结束策略用例均有板上阶段记录，专用150/20/30s按墙钟等待；三类时长0均不误启|',
       '|满载转消毒|制冷/制热各结束0和1，先取得四压机运行反馈，原模式先关完，再消毒1min；恢复原模式时再次取得四压机反馈|',
       '|化霜中关机|板上8→7→0完整等待后再关机；未写生命周期或计时变量|',
       '|化霜高压两路|分别极性模拟316 X00/X02，约0.031s读到对应压机停止，另一台保持；无新高压锁存，恢复输入后本次化霜不重启|',
       '|排序/禁用/补位及计时|板上4→3→2→1→0、禁压机剩3台、禁外机剩2台；运行计时及停机后不继续累计已检查；7200s双向/8压机等剩余条件为ARM离线|',
       '|PID/EEV矩阵|冷热/再热/预热/加湿PID边界、YS/BX/死区、EEV原式微分和蒸发限幅、8路盘管低温、普通/急停超关等有当前双档ARM证据；未替代压力/电阻/电压实物输入、EEV脉冲和热工闭环|',
       f'|30轮普通启停|完成{len(cycle["runs"])}轮：通风、零压机需求制冷、非热泵有热需求制热各10轮；每轮正常启停及风机链/软件输出/119/三板版本检查。不是30轮满载压机启停|',
       f'|两小时观察|实际{soak["elapsed_s"]:.1f}s，20min基线+40min较高读取频率+60min基线；逐样本文件保留；仅软件通信、故障和输出观察|',
       '', '## 仍需处理或补测','',
       '- 普通Modbus手动化霜旧入口570/572/573被写保护拦截，监控工具口径不一致。本批用旧HMI命令输入RAM模拟检查下游；入口未修，不列普通HMI操作通过。',
       '- 无再热自动冷热切换QHS是先累计全停再判低温，还是共同连续计时，原文解释仍未确定。当前共同连续计时已观察，未擅自改规格。',
       '- 停机中再发开机当前被丢弃、不排队；ARM观察安全停完后重新发命令可开。规格没有明确排队要求，本批不判功能故障；加载场景只验证未确认请求撤销。',
       '- 真实断电43例、仪表/物理输入/端子、正式实时时序、完整实物热工与四外机环境等仍缺条件；保持未测或部分通过。水/汽与电热介质、部分曲线阈值仍依规格与已确认口径，不能以代码补写标准。',
       '', '## 恢复与可追溯性','',
       f'[终检]({auditpath.relative_to(R).as_posix()})：普通配置、新AI配置、保存影子恢复一致；保存稳定后ST-Link复位再回读一致，30s健康观察完成。167/373是真实运行累计，增量单列保留，不回写。复位不是真实断电。',
       '', '[测试刺激、旧化霜入口和原始失败说明](测试证据/内机实测_20261105/BENCH_V1052_V1239/remaining529_execution_notes.md)。固件源文件/产物哈希见[构建一致性](测试证据/内机实测_20261105/BENCH_V1052_V1239/continuation_source_artifact_audit.json)。',
       '', f'[30轮及两小时原始记录]({cycles.relative_to(R).as_posix()})。',
       '', '## 未执行项目逐项列出','', '|用例|测试名称|','|---|---|']
    lines += [f'|{r["用例编号"]}|{r["测试名称"]}|' for r in pending]
    destination=R/'剩余529例复核结果_20261105.md'
    destination.write_text('\n'.join(lines)+'\n','utf8')
    phase=R/'内机测试版阶段结论_20261105.md'
    old=phase.read_text('utf8')
    intro=['# 内机测试版阶段结论（2026-11-05）','',f'更新时间：{now()}。当前330 V10.52、两316 V12.39，均保持BENCH。',
        '',f'本轮原529例：板上软件检查{counts.get("板上软件检查/范围见证据",0)}例，仅ARM离线{counts.get("仅ARM离线",0)}例，未执行{counts.get("未执行",0)}例；部分通过与ARM离线均不等于完整实机通过。',
        '',f'30轮普通启停及实际两小时观察已结束，参数恢复和独立复位终检完成。零风量/风压回退旧目标、反向电压夹限已修并回归；旧手动化霜协议入口限制仍保留。',
        '', '[本轮完整结果、限制及未测项](剩余529例复核结果_20261105.md)；[逐项覆盖](剩余529例执行覆盖与未测清单_20261105.csv)。',
        '', '<!-- HISTORY_BEFORE_REMAINING529_START -->','## 此前阶段记录（保留）','',old]
    assert '<!-- HISTORY_BEFORE_REMAINING529_START -->' not in old,'Avoid duplicating history'
    phase.write_text('\n'.join(intro),'utf8')
    print(destination)

if __name__=='__main__':main()
