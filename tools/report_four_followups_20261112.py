"""Publish scoped case results from evidence; process exit is not case acceptance."""
import json
from pathlib import Path
from datetime import datetime

R = Path(__file__).resolve().parents[1]
D = R/'测试证据/四项复核_20261112'


def records(prefix, key):
    result=[]
    for p in sorted(D.glob(prefix+'*.json')):
        q=json.loads(p.read_text('utf8'))
        if isinstance(q,dict) and key in q:result.append((p,q,q[key]))
    return result


def main():
    lines=['# 四项复核结果（2026-11-12）','',
        '范围：一定一双速制冷、X04/X05及低压/过载复核、一定一变60/120秒、外机AO换算。',
        '完整剩余队列、连续2小时稳定性测试保持暂停；83项条件受限、28项正式时序独立保留。',
        '构建/版本按各证据分别标注：原复核330 V10.59 /316 V12.42；修复复测330 V10.60 /316 V12.43。后者是否已上板以flash.json为准。输入模拟与软件输出回读不代表真实端子测量，BENCH不证明正式时序。','',
        f'更新时间：{datetime.now().isoformat(timespec="seconds")}。','',
        '|批次/用例|结果|证据|','|---|---|---|']
    for p,q,e in records('fixed50Hz_span_','scaling'):
        for c in e['cases']:
            result='软件回读通过' if c.get('passed') else '执行中/待核对'
            lines.append(f'|AO最高频{c["maximum_hz"]}Hz → DA{c["expected_DA"]}|{result}|{p.name}|')
    for p,q,e in records('B01_contacts_','B01_contacts'):
        for c in e['cases']:
            result=c.get('status','执行中')
            if c.get('status') and not c.get('recovery_verified'):result+='；恢复未核验'
            lines.append(f'|X{c["ch"]:02d}，316[{c["alarm"]}]|{result}|{p.name}|')
    for p,q,e in records('regression_typeII_','remaining_functional'):
        for c in e.get('cases',[]):
            result={True:'软件子范围通过',False:'待核对'}.get(c.get('passed'),'执行中')
            lines.append(f'|一定一双速：{c["label"]}|{result}|{p.name}|')
    for p,q,e in records('remaining_normal_prestart_','remaining_functional'):
        for c in e.get('cases',[]):
            result='软件子范围通过' if c.get('passed') else '待核对'
            lines.append(f'|{c["label"]}|{result}|{p.name}|')
        for pair in e.get('pairs',[]):
            if pair.get('error'):
                lines.append(f'|一定一变{e["minimum_seconds"]}秒重新加载|超时/异常，需看诊断；不能判为最小运行时间不合格|{p.name}|')
    lines+=['','## 已确认的AO改动','',
        '316 V12.42仅将两条风机频率→DA函数改为固定50Hz满量程，最高/最低频率目标限幅和调速算法保持原逻辑。',
        '30Hz→DA600、40Hz→DA800、50Hz→DA1000。这项初版修正未改330，后续启动确认修正另见下文。',
        '两个316板已烧录，HEX有效字节回读核验均通过；正式/BENCH构建均0错误0警告。',
        'V12.42 ARM回归1920项通过；监控FFP-2026.11.12a离线354项通过、EXE离线界面启动通过并打包。','',
        '## 重新加载诊断','',
        '原V10.59启动确认超时为FanONLaySet+60秒（本台75秒），未纳入外机风机最小停机等待。',
        '60秒档板上诊断已捕获75秒后启动重试时间增加300秒、316请求随后撤销，与原ARM复现一致；这不是风机提前停机。',
        '证据：`restart_watchdog_ARM_reproduction.json`；不把启动超时等同于风机提前停机。','',
        '## 低温恢复问题与测试输入修正','',
        '原V12.42一定一双速：低温停风标志解除后，段位仍需等待0→1切换。该间隙失去有意停风授权，最终联锁误切运行压机；环境10.1℃、系统1或2冷凝42.1℃均有板上记录，原ARM亦复现。',
        'V12.43小修正只将有意停风授权延续至段位0结束，不改变30秒温度保持、段切换间隔、最小开停、故障和禁用保护；板上结果见后表。',
        '原OR交接测试把ADC原始值400/2000误当作转换后的信号400/2000，出现9999压力，不能作为控制缺陷。修复复测用实际ADProcess离线核验过的4～20mA采集值745/3724，经正常AI配置映射，逐帧核对实际输入。',
        '第二次ADC交接测试虽采样时温度正确，恢复计数仍在采样间隔归零，输入连续性无法证明。随后用正常网关AI工程量窄量程建立稳定温度，最终OR用例通过：环境条件上界25.031秒、冷凝条件上界21.562秒，合并43.156秒仍不恢复；单独冷凝条件持续达到30秒并经过段切换后恢复，压机连续运行。两次ADC失败记录保留，不将其改写为通过。',
        '原X01测试直接改316输入极性，与330广播发生竞争，出现短暂消警；不能据此断定镜像缺陷复现。稳定复测改正常330外机极性源，分别核对两板输入、防抖、报警、保护、镜像及无复位恢复。','',
        '新板烧录后首次审计见共享风机类型330[1344]为0、原值为1，审计当时未通过；后续未重刷、未额外写参数，重新审计值已恢复一致。初次失败记录保留，该现象尚未定位原因，不并入本次两项已修复代码缺陷。','',
        '## 修复复测证据','',
        '以下只统计实际生成的证据，执行进程返回0不自动等于用例通过。','',
        '|新版本用例|结果|证据|','|---|---|---|']
    fix=D/'restart_fix'
    for path in sorted(fix.glob('*.json')):
        try:q=json.loads(path.read_text('utf8'))
        except (ValueError,OSError):continue
        if not isinstance(q,dict):continue
        for key in ('typeII_recovery','stable_low_pressure','remaining_functional'):
            e=q.get(key)
            if not e:continue
            for c in e.get('cases',[]):
                label=c.get('label',f'LP X{c.get("ch", "?")}')
                status='软件子范围通过' if c.get('passed') else ('失败/待核对' if 'passed' in c or c.get('error') else '执行中')
                if not c.get('passed') and e.get('error') and 'exact input' in e['error']:
                    status='输入前提超时；保留原记录并安排重跑'
                lines.append(f'|{label}|{status}|restart_fix/{path.name}|')
            for pair in e.get('pairs',[]):
                if pair.get('error'):lines.append(f'|重新加载{e.get("minimum_seconds")}秒|异常，原轨迹保留|restart_fix/{path.name}|')
                for r in pair.get('run_lengths',[]):
                    lines.append(f'|最小运行{e["minimum_seconds"]}秒，风机{r["fan"]+1}|观测运行{r["on_seconds"]:.3f}秒，少{r["shortfall_seconds"]:.3f}秒|restart_fix/{path.name}|')
                for r in pair.get('restart_gaps',[]):
                    lines.append(f'|最小停机{e["minimum_seconds"]}秒，风机{r["fan"]+1}|观测间隔{r["off_seconds"]:.3f}秒|restart_fix/{path.name}|')
    lines+=['','### 新构建离线回归','', '|结果文件|通过/总断言|','|---|---|']
    arm_files=[D/'restart_guard_ARM_results.json',D/'typeII_recovery_ARM_results.json',fix/'adc_fixture_ARM_results.json',fix/'adc_robust_fixture_ARM_results.json',fix/'typeII_independent_OR_ARM_results.json',*sorted((fix/'arm').glob('*results*.json'))]
    for path in arm_files:
        if not path.exists():continue
        q=json.loads(path.read_text('utf8'))
        if isinstance(q,dict):lines.append(f'|{path.relative_to(D).as_posix()}|{q.get("passed","见原文件")}/{q.get("total","见原文件")}|')
    totals=[]
    for path in arm_files:
        if path.exists():
            q=json.loads(path.read_text('utf8'))
            if isinstance(q,dict) and isinstance(q.get('total'),int):totals.append(q)
    if totals:lines+=['',f'已生成的新构建ARM结果共{sum(q["passed"] for q in totals)} / {sum(q["total"] for q in totals)}项通过；各文件为互不重叠用例集。监控离线354项另计。']
    audits=[]
    for path in fix.glob('*audit*.json'):
        try:q=json.loads(path.read_text('utf8'))
        except (ValueError,OSError):continue
        if isinstance(q,dict) and q.get('verified'):audits.append((path,q))
    if audits:
        path,q=max(audits,key=lambda x:x[0].stat().st_mtime)
        lines+=['',f'最近独立恢复审计：`restart_fix/{path.name}`；版本{q["versions"]}；源码绑定{q["source_inventory_matches"]}文件；参数恢复差异{len(q["restoration_mismatches"])}项；停机状态已核验。']
    lines+=['',
        '## 代码范围与仍未关闭事项','',
        '本次新增修正仅四个源码文件：330 CompAction.c及版本头、316 UserAction.c及版本头。330启动确认保留原60～300秒确认余量，另加各台有效316[180]风机最小停机设定；实际已启动的确认优先、失败启动仍撤销请求并等待300秒重试。未新增或搬移寄存器。',
        '316保留V12.42固定50Hz满量程AO修正，仅延续一定一双速低温调压停风许可至段位0结束；故障、禁用及环境许可联锁仍执行。control_timing.h未修改，36℃原边界未修改。正式/BENCH构建均0错误0警告，台架运行BENCH；本轮软件证据不能替代正式时序或物理端子验收。',
        '本轮故障镜像检查覆盖X04/X05、X06/X07过载和X01/X03低压；不能外推为所有温度/压力探头的物理断线场景全部通过。首次烧录后1344暂态不一致尚未归因，后续独立审计均一致，继续保留观察。',
        '完整剩余53批和连续2小时稳定性测试仍按先前要求保留未执行；83项条件受限、28项正式时序独立保留。已记录的30秒档29.4秒不作为新增代码缺陷；本次60秒档一路59.766秒、120秒档一路120.109秒，记录采样边界，未把观测误差用于更改定时逻辑。','',
        '## 原始记录与恢复','',
        '证据目录：`测试证据/四项复核_20261112`。逐批正常停机、恢复原参数，再执行独立审计。',
        '已完成/执行中和各用例通过是不同口径，详见`four_controller_105025.json`和各用例JSON。']
    (R/'四项复核结果_20261112.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('Updated 四项复核结果_20261112.md')


if __name__=='__main__':main()
