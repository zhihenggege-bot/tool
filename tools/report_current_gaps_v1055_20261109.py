"""File-only gap snapshot; evidence counts are not full acceptance counts."""
import json
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone,timedelta

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/内机实测_20261105/BENCH_V1055_V1239'


def main():
    inventory=json.loads((D/'pending_evidence_inventory_20261109.json').read_text('utf8'))
    rows=inventory['rows'];missing=[r for r in rows if not r['evidence']['board']]
    board=[r for r in rows if r['evidence']['board']]
    current=[r for r in board if any('/BENCH_V1055_V1239/' in p for p in r['evidence']['board'])]
    offline=[r for r in missing if r['evidence']['offline']]
    unseen=[r for r in missing if not r['evidence']['offline']]
    count=Counter(r['group'] for r in missing)
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    lines=['# 当前未测与待复测清单（2026-11-09）','',
        f'盘点生成时间：{stamp}。330 V10.55、两316 V12.39，测试档BENCH。以最近一次完成且参数恢复的原始证据盘点；正在运行的批次不提前计入。','',
        f'原571项中：{len(board)}项有板上软件子范围证据（其中{len(current)}项包含V10.55），{len(offline)}项仅离线，{len(unseen)}项未找到完成证据。后两类合计**{len(missing)}项缺板上完成证据**。这些数字不是完整验收通过数；板上软件证据中仍有端子、原始诊断、正式时序等缺口。历史101项不混入571项。','',
        '## 用户调整的测试顺序','',
        '通风相关项目暂缓，先执行其余可测项目，再返回通风。两小时通风监视只采到约35分钟，按用户要求结束并恢复，未判两小时通过。真实接线/断线、真实断电和正式秒数本轮不冒充完成；可用输入模拟先取得下游软件证据。','',
        '## 当前异常与复测状态','',
        '|事项|当前结论与剩余范围|','|---|---|',
        '|消排毒故障停机后[885]残留1|V10.55局部修复并有阶段内软件复测；实际端子、正式档及尚未覆盖组合另验。|',
        '|电热故障加湿不关、AI3漏联锁、Z=0显示和原因码覆盖|有后续修复及软件范围证据，原失败保留；不等同电气输入到端子的整链验收。|',
        '|消排毒时长非法写入无应答|范围重测已完成：323/324合法0/1/998/999回读，非法1000/-1被拒且保留原值、随后合法写入正常；未实际运行999分钟。|',
        '|环温满载顺序首轮被DA8打断|原轨迹保留；测试配置增加[245]=1、[247]=0隔离遗留DA8后重测，未因此修改固件。以最新恢复完成的批次为准。|',
        '|遗留DA8隔离T06-024|固定压机下，旧手动配置[245]=1、[247]0→500→0使软件DA8同样0→500→0，重复复现；[314]实际固定0。既定隔离用例预期不满足，但[245]本身已选择手动输出，规格未明确这条遗留旁路的独立介质许可，不能单凭脚本预期认定必须屏蔽。未改固件，IO用途/手动许可口径和真实端子另核。|',
        '|四路盘管300/120秒板测|原始ADC/滤波输入模拟时，首路在303秒观察窗内未见低温闭锁，批次已正常停止恢复，独立回读165819通过。第二轮合并ADC输入传输仍未完成：只读计数显示四路中途重置，最长连续227/221/215/183秒，未达到300秒。原始失败及180924独立恢复回读保留；未证明输入连续，暂不判固件缺陷或勾选300/120秒通过。|',
        '|EEV起始/上限首轮拒写|测试脚本误把最大开度写到[14]温差参数，协议拒写；已纠正为电机总步数[10]、最大开度[12]后重测，原中断不判固件缺陷。|',
        '|最早一次0V异常|后续正常写入及保存竞态专项未重现；首次轨迹不足，继续保留待复现，不能声称已彻底定因。|',
        '|化霜中消防急停后的退出|T16-005负载软件输出已关闭，但保持制热选择时退出命令后化霜阶段8持续超过150s；恢复原先制冷配置后已清0，独立回读无差异。保留原清理失败，不判完整闭环通过，后续需带316直接状态和命令链复核。|','',
        '## 加热曲线已取得的证据','',
        '主热、共用再热、独立再热、预热的AO/1:2/1:2:4/SCR升降曲线、回差及并行不争用均有板上软件范围证据（T06-007～023）。不笼统归为“没测”；冬季指定边界、未覆盖的运行重配置、真实端子及正式档仍分别保留。','',
        '## 缺板上完成证据的分组','',
        '|组|项数|','|---|---:|']
    lines += [f'|{g}|{n}|' for g,n in sorted(count.items())]
    lines += ['','## 全部缺证据用例','','|用例|名称|证据级别|','|---|---|---|']
    lines += [f'|{r["id"]}|{r["name"]}|{r["level"]}|' for r in missing]
    lines += ['','传感器开路/短路配对编号可共用一次锁存输入模拟；只增加其共同的下游证据，不虚报为两个电气场景已测。第三/第四外机未安装的回路不以被配置清除的锁存冒充启用回路测试。','',
        '[逐项原始证据索引](测试证据/内机实测_20261105/BENCH_V1055_V1239/pending_evidence_inventory_20261109.json) · [主测试记录](内机测试版逐项测试记录_20261105.md)']
    (R/'当前未测与待复测清单_20261109.md').write_text('\n'.join(lines)+'\n','utf8')
    print(json.dumps(dict(at=stamp,original_scope=571,board_subscope=len(board),current_version_subscope=len(current),
        missing_board_subscope=len(missing),offline_only=len(offline),no_completed_evidence=len(unseen)),ensure_ascii=False))


if __name__=='__main__':main()
