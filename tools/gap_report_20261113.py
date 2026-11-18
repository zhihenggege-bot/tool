"""Read-only report of the isolated rerun; execution is not acceptance."""
import json
import hashlib
from pathlib import Path
from datetime import datetime

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/缺口复测_20261113'


def link(p,label='证据'):
    return f'[{label}]({p.relative_to(R).as_posix()})'


def main():
    records=[]
    for p in D.glob('rerun_*.json'):
        q=json.loads(p.read_text('utf8'))
        if 'targeted_rerun' in q:records.append((p,q,q['targeted_rerun']))
    lines=['# 缺口复测与连续抓取记录（2026-11-13）','',
           '本轮按“再测一遍、认真抓取记录”执行。固件未修改、未重新烧录；绑定330 V10.61 / 316 V12.43，BENCH_ONLY_3S。',
           '', '最终结果：化霜整机禁用、两路模拟高压报警屏蔽、伙伴压机30秒补开、化霜中切换通风的完整过程均获得软件范围证据。手动保护4项因手动压机未开启仍不能验收；AI共12点，1点满足诊断判据、11点持续输入条件不足。全部批次最终恢复并通过独立核验。',
           '', '证据区分正常协议配置、ADC/NTC输入模拟、316直接软件状态、330镜像及独立恢复核验；软件DO/AO不代表物理端子测量。', '',
           '| 复测项目 | 实际记录及判定 | 恢复 | 原始证据 |','|---|---|---|---|']
    for p,q,e in sorted(records,key=lambda x:x[1].get('today','')):
        kind=e['kind'];text='执行中，未下验收结论'
        labels={'whole_unit_disable':'化霜中整机禁用','mode_during_defrost':'化霜中切换通风',
                'manual_protection':'手动保护','defrost_analog_pressure':'化霜模拟高压',
                'defrost_partner_30s':'伙伴压机30秒补开','AI_diagnostics':'AI输入诊断'}
        if kind=='whole_unit_disable' and 'passed' in e:
            text='内部化霜状态清零、授权释放、两压机关闭；禁用时允许阶段6残留。'+('软件子范围通过' if e['passed'] else '未满足判据')
        elif kind=='mode_during_defrost' and e.get('finished'):
            states=sorted({(s['selected_mode'],s['state'][9],s.get('IndoorPendingWorkMode')) for s in e['samples']},key=str)
            text=f'模式/步骤/待切换状态：{states}；最终选中通风={e.get("selected_mode_accepted")}。'
            if e.get('passed'):text+='完整切换通过。'
            elif 'IndoorPendingWorkMode' not in e.get('final',{}):text+='25秒观察未覆盖完整停机；后续长窗复测另列。'
            else:text+='本次窗口未覆盖最终切换，后续更长窗口复测另列；不算固件失败。'
        elif kind=='manual_protection':
            done=[c for c in e['cases'] if c.get('finished')]
            failed=[c['channel'] for c in done if not c.get('passed')]
            text=f'已尝试{len(done)}项，未通过/前置未建立通道{failed}。命令已达两316，但健康手动压机输出未建立；不能验证后续保护有效性。'
        elif kind=='defrost_analog_pressure' and e.get('finished'):
            text=f'AI{e["channel"]}：实际化霜下3801kPa连续{e.get("continuous_high_defrost_s",0):.3f}秒；报警屏蔽={e.get("alarm_masked")}；软件子范围通过={e.get("passed")}。'
        elif kind=='defrost_partner_30s' and e.get('finished'):
            text=f'伙伴启动计数{e.get("partner_start_counter_s")}秒，首个化霜样本至启动{e.get("observed_from_first_active_s")}秒；通过={e.get("passed")}。'
            if q.get('today_cleanup_error'):text+=' 首次正常停机等待超过脚本180秒上限；后续正常停机与独立恢复核验通过，原超时保留。'
        elif kind=='AI_diagnostics':
            done=[c for c in e['cases'] if c.get('finished')]
            passed=sum(bool(c.get('passed')) for c in done)
            text=f'已尝试{len(done)}个AI输入点，{passed}点满足持续输入、诊断与通风软件输出判据；逐点见下表。'
        if e.get('error'):text+=' 原始异常：'+e['error'].splitlines()[-1].replace('|','/')
        restored='已回读恢复' if q.get('restored') else '待核验/见异常'
        lines.append(f'| {labels.get(kind,kind)} | {text} | {restored} | {link(p)} |')
    ai=[(p,e) for p,q,e in records if e['kind']=='AI_diagnostics']
    if ai:
        lines+=['','| AI通道 | 输入ADC | 风量方式 | 实际消费ADC范围 | 持续无效秒数 | 诊断/输出判据 | 恢复 |','|---|---|---|---|---|---|---|']
        for p,e in ai:
            for c in e['cases']:
                lines.append(f'| {c["channel"]} | {c["raw"]} | {c["flow_basis"]} | {c.get("consumed_range")} | {c.get("continuous_invalid_s")} | {c.get("passed")} | {c.get("recovery_verified")} |')
    lines+=['','抓取方式：events.jsonl逐条保存协议写入开始、响应/错误、回读、直接状态及镜像；AI/NTC另有连续采样文件，均包含墙钟和单调时钟。先判定实际消费输入成立，再判定保护结果。', '',
        '已保留的两项代码交互证据（仅离线执行当前AXF，未改板上状态）：', '',
        '- 手动输出限制：合法配置下手动函数将压机置1，随后输出限制按正常FanOpenSet判断风机未运行，将两压机清0；与本轮板上现象一致。',
        '- 模式切换的单函数离线调用：请求通风后Pending=2、SysStatus转停机，直接再调同函数会清Pending。该调用没有模拟主循环上游重新生成SysStatus，不能据此判定固件缺陷；长窗板上已经采到Pending=2持续保留，最终行为以板上完整轨迹为准。', '',
        '物理端子电压：本会话没有可读取的万用表/采集仪测量，仍未验收。正式秒数及2小时队列保持此前“暂不测”范围，本轮BENCH复测不能关闭这些缺口。', '',
        '本轮主目录：'+link(D/'events.jsonl','连续协议与状态日志')+'。旧批次失败记录保留；“已执行”不等于全部通过。']
    if (D/'state_edges.csv').exists():
        lines+=['','便于核对的派生表：'+link(D/'state_edges.csv','状态变化表')+'；'+link(D/'protocol_and_action_errors.csv','协议与执行异常表')+'。原始日志保留完整数据。']
    audits=[]
    for p in D.glob('*.json'):
        q=json.loads(p.read_text('utf8'))
        if q.get('read_only') and q.get('verified'):audits.append((p,q))
    if audits:
        p,q=max(audits,key=lambda x:x[0].stat().st_mtime)
        lines+=['','最近独立核验：'+link(p)+'；verified=True，参数差异='+str(q.get('restoration_mismatches'))+'。']
    lines+=['','报告生成：'+datetime.now().astimezone().isoformat(timespec='seconds')]
    path=R/'缺口复测记录_20261113.md';path.write_text('\n'.join(lines)+'\n',encoding='utf8')
    inventory={p.relative_to(R).as_posix():dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
               for p in D.rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl','.txt','.csv','.py') and p.name!='capture_inventory.json'}
    (D/'capture_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    print(path)


if __name__=='__main__':main()
