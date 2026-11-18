"""Summarize bounded fix evidence; keep unsuccessful attempts and limitations."""
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/手动联锁修复_20261113'
F=D/'复位可靠传递修复后'
P=R/'.codex-tmp/manual_gate_v1063_v1244_20261113'

def read(p):return json.loads(p.read_text('utf8'))
def link(p):return p.relative_to(R).as_posix()

def main():
    rows=[];details=[];cases=[];automatic=[]
    for folder in (D,D/'330复位修复后',F):
        for p in sorted(folder.glob('rerun_manual_protection_stopped_configuration_*.json')):
            q=read(p);label={D:'330 V10.61',D/'330复位修复后':'330 V10.62',F:'330 V10.63'}[folder]
            for c in q['targeted_rerun']['cases']:
                name={0:'X00高压',1:'X01低压',6:'X06过载',4:'X04风机1',5:'X05风机2'}[c['channel']]
                status='通过' if c.get('passed') else '未通过／观察或恢复未完成'
                rows.append(f'|{label}|{name}|{status}|{q.get("restored",False)}|[原始记录]({link(p)})|')
                if folder==F:cases.append(c)
                samples=c.get('samples',[])
                details.append(dict(firmware=label,case=name,passed=c.get('passed',False),error=c.get('error'),
                    samples=len(samples),first_sample=samples[0]['at'] if samples else None,last_sample=samples[-1]['at'] if samples else None,
                    restored=q.get('restored',False),evidence=link(p)))
        for p in sorted(folder.glob('rerun_fan_interlock_and_automatic_regression_*.json')):
            q=read(p);a=q['manual_automatic_regression'];automatic.append((p,q,a))
    audits=sorted(F.glob('after_*.json'),key=lambda p:p.stat().st_mtime)
    last=read(audits[-1]) if audits else {}
    complete=len(cases)==5 and all(c.get('passed') for c in cases) and bool(automatic) and automatic[-1][2].get('passed') and last.get('verified')
    lines=['# 手动输出联锁修复与板上复测（2026-11-13）','',
        '目标固件：330 V10.63 / 两块316 V12.44，BENCH_ONLY_3S。正式档已编译，未上板验收。',
        '当前阻断：330升级过程中ST-Link USB Pipe error，烧录未完成、固件完整性待核验；随后检测不到调试探针和任何串口。两块316已完整回读匹配V12.44。本次330 V10.63尚未完成上板验收。',
        '330烧录前完整Flash与SRAM备份已保存。deployment.json中的programmed=false仅表示未完成烧录，不表示Flash未被改写；不可将板上330继续认定为完整V10.62。',
        f'本任务修复范围复测完成={bool(complete)}。软件回读不等于继电器端子、电压或压机动力验收。','',
        '本次修复：','',
        '- 316手动压机被清零：最终联锁在手动模式读取该风机类型支持的实际DO；变频同时检查运行DO及AO>0。自动风机状态、调节停机例外保留原路径。',
        '- 316手动命令覆盖保护：在手动DO赋值后重新应用已计算的压机／整机故障和急停结果；无风机仍禁止压机。故障识别、锁存及复位判据未改。',
        '- 330重复复位：新复位到来时将原11秒传递窗口重新计时。旧版在第9秒收到新请求后可能1秒即结束；新构建的ARM回归确认重新获得完整窗口。',
        '- 330复位可靠传递：逐台保留复位请求，收到对应控制帧的有效应答后才完成；超出11秒窗口仍可传递，错误CRC、错误机号、旧请求应答不能撤销新请求。',
        '- 330 Y05：原手动调试按手动报警开关覆盖真实报警；现改为真实故障或手动报警任一有效即输出。两个构建档各8组报警组合通过ARM执行回归，实体继电器尚未复核。',
        '- 本次共6个固件源文件变化（含两份版本宏）；寄存器地址、映射、0～10V比例和正式时序常量均未改。','',
        '原始失败及修复后复测：','',
        '|固件|测试项|结果|批次最终恢复|证据|','|---|---|---|---|---|',*rows,'']
    for p,q,a in automatic:
        lines+=['自动／手动联锁回归：','',f'- 整批通过={a.get("passed",False)}；恢复={q.get("restored",False)}。[记录]({link(p)})']
        for c in a['checks']:lines.append(f'- {c["check"]}：通过={c.get("passed",False)}。')
        for c in a.get('automatic_fan_lead',[]):lines.append(f'- 外机{c["unit"]}自动启动：软件风机输出领先首次压机输出约{c["observed_fan_lead_s"]:.3f}秒（BENCH档采样值）。')
        lines.append('')
    arm=read(R/'.codex-tmp/manual_gate_v1244_20261113/ARM_regression.json')
    lines+=['离线回归与烧录核验：','',
        f'- 正式档及BENCH档共{sum(r["automatic_old_new_equal"] for r in arm["results"])}组自动输出与旧版逐项一致；{sum(r["manual_fan_cases"] for r in arm["results"])}组手动风机组合通过，另有故障、禁用和急停检查。',
        f'- [手动联锁ARM证据]({link(R/".codex-tmp/manual_gate_v1244_20261113/ARM_regression.json")})；[复位重新计时ARM证据]({link(R/".codex-tmp/manual_gate_v1062_v1244_20261113/reset_ARM_regression.json")})；[可靠复位及Y05 ARM证据]({link(P/"reset_delivery_ARM_regression.json")})。',
        f'- [316烧录／回读]({link(D/"deployment.json")})；[330 V10.63中断记录及备份]({link(F/"deployment.json")})。330新固件尚未完成全HEX回读，不能标记烧录成功。',
        f'- 最近独立核验：通过={last.get("verified",False)}，源码匹配={last.get("source_inventory_matches")}，参数差异={last.get("restoration_mismatches")}。'+(f'[核验]({link(audits[-1])})' if audits else ''),'',
        '连续抓取：每条正常协议配置／应答／错误、316直接状态、330镜像、故障输入与保护输出均保留墙钟和单调时钟。[修复后日志]('+link(F/'events.jsonl')+')。',
        '本轮手动保护使用330正常输入极性配置，刺激会传给两台外机；“健康继续运行”指每块板上未故障的另一系统，不能宣称另一台外机未受到同一刺激。',
        '手动保护测试会同时下发压机和风机手动命令，风机故障会切断整台外机；这与自动启停分开验收。','',
        '仍保留的验收缺口：11个AI点持续输入条件不足、物理端子电压、正式时序及2小时稳定性；本次修复不将它们标记为通过。',
        '原始超时、启动阶段无应答及诊断计数比较异常均保留；后续恢复／补核单列，没有覆盖原记录。','',
        '恢复队列：','',
        '1. 恢复台架USB连接，用tools/recover_reset_delivery_v1063_20261113.py重新烧录330并逐字节回读；核对三板版本、配置与停止状态。',
        '2. 运行tools/manual_delivery_fix_context_20261113.py manual，完成高压、低压、过载、X04、X05五项；同时抓取330总报警、Y05软件输出、316保护及330镜像；现场核对Y05实体继电器。',
        '3. 运行同一工具的automatic动作，核对无风机压机禁止、风机先起、正常启停及参数恢复，再独立audit。',
        '4. 正式时序、2小时稳定性仍按用户要求暂缓。','',
        '生成：'+datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')]
    (R/'手动联锁修复与复测_20261113.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (D/'result_summary.json').write_text(json.dumps(dict(scope_complete=bool(complete),cases=details,latest_audit=link(audits[-1]) if audits else None),ensure_ascii=False,indent=2),encoding='utf8')
    inventory={}
    for p in sorted(D.rglob('*')):
        if p.is_file() and p.name!='evidence_inventory.json':inventory[p.relative_to(D).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    (D/'evidence_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    print('REPORT WRITTEN scope_complete=',bool(complete),flush=True)

if __name__=='__main__':main()
