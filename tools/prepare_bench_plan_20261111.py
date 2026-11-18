"""Generate the next-day queue from existing evidence; no hardware access."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / '内外机台架测试队列_20261111.csv.txt'
SUMMARY = ROOT / '测试证据/明日台架计划_20261111/plan_inventory.json'


def read(name):
    with (ROOT / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    if QUEUE.exists():
        with QUEUE.open(encoding='utf-8-sig', newline='') as f:
            existing = list(csv.DictReader(f))
        assert all(r.get('执行状态') == '待执行' and not any(r.get(k) for k in ('结果', '新证据', '恢复核验'))
                   for r in existing), 'Queue contains execution results; preserve them instead of regenerating'
    indoor = read('内机剩余150项明日安排_20261110.csv.txt')
    outdoor = read('室外机逐项测试表_20261110.csv.txt')
    latest = {r['用例']: r for r in read('内外机未完成测试核对_20261110.csv.txt')}
    rows = []
    for r in indoor:
        cid, name = r['原用例'], r['名称']
        group = cid.split('-')[0]
        category = '当前台架可做功能子范围'
        batch, priority = 'B06 内机余项', 'P1'
        scope = '正常330入口建立条件，原始采集输入模拟，检查动作、保持、解除、复位及设备回读'
        gap = '模拟输入及软件输出不代替物理信号/端子；旧版本证据不自动升为当前版通过'
        if cid.startswith('T18-'):
            category, batch = '需真实断电条件', 'C03 真实断电/保存'
            scope = '具备可控分路断电及所需毫秒触发条件后按原步骤执行；当前不以ST-Link复位替代'
            gap = '当前台架尚未证明可控真实断电，保存中断0/10/100ms还需触发装置'
        elif cid in ('T01-003', 'T08-007', 'T08-008'):
            category, batch = '需仪表/信号源', 'C02 信号与端子'
            scope = '核验实际电压/电流低中高三点；设备和仪表未就绪则标受限'
            gap = '工程量映射或ADC模拟不能作为物理三点对账'
        elif (cid in ('T10-020',) or cid in {f'T15-{i:03}' for i in range(5, 9)}
              or (group == 'T03' and any(f'NTC{i}' in name for i in range(8, 12)))):
            category, batch = '需3/4台及扩展回路', 'C01 扩展硬件'
            scope = '当前可检查未配置回路不误报；3/4台、5～8安装回路的完整联测待硬件齐备'
            gap = '只有两台316；模拟结构不能算四台实物或八回路验收'
        elif group == 'T14' or cid in ('T16-008', 'T17-002'):
            category, batch, priority = '需PRODUCTION档完成时序', 'B08 正式档时序', 'P1'
            scope = '使用相同源码的现有正式产物，三板档位一致后执行真实墙钟时序；未切档则只记录功能缺口'
            gap = 'BENCH不证明10/15/30/60/120/150/180/300秒正式时序；切档需预留烧录及核验时间'
        elif group == 'T03':
            batch = 'B07 通风故障矩阵'
            scope = '已安装AI0～4、NTC0～7分别开短路模拟；出现/保持/撤源/复位；风机可启停，冷热负载不误开'
        elif cid == 'T13-064':
            batch = 'B09 通风连续2小时'
            scope = '正常通风连续120分钟，按预定只读负载窗口对照；只读记录不并行故障、改模式或改参数'
            gap = '模式中断、复位、输入模拟中断导致的无效窗口重新计时；旧35分钟不拼接'
        elif cid in ('T10-017', 'T10-025', 'T10-026', 'T10-027'):
            batch, priority = 'B01 故障镜像与通讯', 'P0'
            scope = '单台/双台通讯丢失和逐台恢复，核330候选分配、另一健康外机及同拍停机；先验证断链方法'
            gap = '真实分路断线需接线条件；通信仿真只记软件子范围；不停止CPU或伪写通讯故障位代替断链'
        elif cid in ('T10-018', 'T10-019', 'T16-005'):
            batch, priority = 'B05 化霜联测', 'P0'
            scope = '与外机化霜同轮取证：阶段8/7普通分配不覆盖；急停清负载/旧请求/状态/占用，解除不续跑旧轮'
        elif group == 'T15':
            batch = 'B06 内机余项'
            scope = '1～4回路已有300/120秒轨迹只补缺口；连续性和模式切换重点补其它已安装回路'
        elif cid in ('T06-024', 'T06-025'):
            scope = '核245/247手动模式与DA8实际路由、许可、0/中点/0；不支持的配置记不适用，不造枚举'
            gap = '独立介质许可口径未确认，只记录现状，不判缺陷、不改代码'
        elif group == 'T06':
            scope = '蒸汽/热水、主热/再热/预热逐配置：新风-0.1/0/+0.1℃，零需求/非零需求，阀门最小开度和电热区分'
        elif cid == 'T10-024':
            scope = '当前只补正常软件复位前后累计；真实断电累计另记受限，不能关闭整项'
            gap = '真实断电部分未做；正常复位与掉电分开取证'
        elif cid == 'T12-005':
            scope = '全局冷媒桥接今日已测；仅补PT/过热计算独立对账及未覆盖动态，不重复四种冷媒写入专项'
        elif cid == 'T17-004':
            batch = 'B10 恢复与盘点'
            scope = '汇总未测/受限/未决及问题证据，所有原ID保留，禁止将子范围通过写为整项通过'
        prior = latest[cid]
        rows.append(dict(机组='330', 用例=cid, 名称=name, 批次=batch, 优先级=priority,
                         条件分类=category, 计划覆盖=scope, 未关闭范围=gap,
                         当前状态=prior['补充后最新范围状态'] or prior['原状态'],
                         已有证据=prior['证据路径'], 原步骤=r['步骤与判定'],
                         执行状态='待执行', 结果='', 新证据='', 恢复核验=''))

    batches = {'PARAM': 'B02 参数缺口', 'AMBIENT': 'B04 环温许可',
               'DISPATCH': 'B03 六配置风机与分配', 'FANTIME': 'B03 六配置风机与分配',
               'HEATFAN': 'B03 六配置风机与分配', 'FANCURVE': 'B03 六配置风机与分配',
               'DEFROST': 'B05 化霜联测', 'PROTECT': 'B01 故障镜像与通讯',
               'FOURWAY': 'B08 正式档时序', 'LINK': 'B01 故障镜像与通讯'}
    for r in outdoor:
        cid, group = r['用例'], r['组']
        category = '当前台架可做功能子范围'
        scope = r['输入步骤'] + '；' + r['观察']
        gap = r['限制']
        if cid in ('O-PARAM-025', 'O-PARAM-026'):
            category = '需首次初始化条件'
            scope = '先审阅已有EEPROM/默认种入；无可恢复的首次初始化环境则受限，不清当前生产EEPROM'
            gap = '普通切全新风不等于首次种入，不据已有值不变判失败'
        elif group == 'PARAM':
            scope = '今日已有默认表/边界写入证据；只补跨广播持续回读、实际有效源与算法关联，不重跑全部24项边界'
            gap += '；首次默认、真实掉电保存及物理输出分别待验'
        elif group == 'AMBIENT':
            scope += '；同一运行状态下复用自然计时，阈值前/等于/后和中断重计分别留证'
            gap += '；当前BENCH许可恢复窗口不等于正式300秒；13℃/LWS−2、−15支路及43℃图文差异只观察'
        elif group == 'FANTIME':
            scope += '；每种配对同一曲线并录开/停/互斥，不另跑重复起停'
            gap += '；正式15秒/最小开停须PRODUCTION补测'
        elif group == 'PROTECT':
            scope += '；每例保持故障至316实值、330逐条镜像和2598/2618连续稳定；记录时间差后撤源/复位'
            gap += '；采集模拟与真实断线、物理开关保护分别标注；压机功率回路隔离'
        elif group == 'DEFROST':
            scope += '；入口自然运行累计，禁止写计时器/阶段/Owner；同轮仅合并不互相破坏的观察'
            gap += '；正常60秒恢复/30秒补开在BENCH仅功能，需正式档；默认间隔与合法最小间隔分开标注'
        elif group == 'FOURWAY':
            scope += '；有效共享源41与316[193]同时记录，不能只写193后立即判断'
            gap += '；BENCH动作仅功能，20/30/120秒要正式档验证'
        if cid == 'O-FANCURVE-016':
            scope = '先保持现有代码；记录35.9/36/36.1℃，按用户当前文字>36升频观察；≥36图支路单列，不预判缺陷'
        if cid == 'O-FANCURVE-019':
            scope += '；定频关/开两分支各测设置0.1/1/2Hz/s，额外>45℃启动分支；满载速度适用未决单列'
        if cid == 'O-FANCURVE-021':
            scope += '；至少20分钟连续观察与3次单/双风机切换，轮换周期未规定不自造失败条件'
        if cid in ('O-LINK-001', 'O-LINK-006'):
            scope = '今日共享/全局37步已通过，明日仅基线抽查与收尾复核，不把重复检查计为新增完整验收项'
        if cid == 'O-LINK-005' or cid == 'O-DEFROST-021':
            gap += '；真实通讯断开需可控分路；无条件则模拟软件范围单列，不冒充真实断线'
        prior = latest[cid]
        rows.append(dict(机组='316', 用例=cid, 名称=r['名称'], 批次=batches[group], 优先级=r['优先级'],
                         条件分类=category, 计划覆盖=scope, 未关闭范围=gap,
                         当前状态=prior['补充后最新范围状态'] or prior['原状态'],
                         已有证据=prior['证据路径'], 原步骤=r['输入步骤'] + '；预期：' + r['预期'],
                         执行状态='待执行', 结果='', 新证据='', 恢复核验=''))

    rows.sort(key=lambda r: (r['批次'], r['优先级'], r['机组'], r['用例']))
    assert len(rows) == 306 and len({r['用例'] for r in rows}) == 306
    assert {r['用例'] for r in rows} == set(latest)
    for i, r in enumerate(rows, 1):
        r['队列序号'] = i
    fields = ['队列序号'] + [k for k in rows[0] if k != '队列序号']
    with QUEUE.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    sources = ['内机剩余150项明日安排_20261110.csv.txt', '室外机逐项测试表_20261110.csv.txt',
               '内外机未完成测试核对_20261110.csv.txt']
    summary = dict(plan_date='2026-11-11', timezone='Asia/Shanghai', hardware_access=False,
                   firmware_modified=False, scheduled_automation=False, total_rows=len(rows),
                   execution_policy=dict(continue_after_case_failure=True,
                                         request_confirmation_between_cases=False,
                                         recover_and_verify_before_next_case=True,
                                         record_condition_limits_and_continue=True,
                                         report_issues_after_queue=True,
                                         change_firmware_during_tests=False,
                                         source='User instruction2026-11-10:逐项连续测试，测完统一说明问题'),
                   unique_ids=len({r['用例'] for r in rows}),
                   source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                   categories={u: dict(Counter(r['条件分类'] for r in rows if r['机组'] == u)) for u in ('330', '316')},
                   batches={b: dict(Counter(r['机组'] for r in rows if r['批次'] == b)) for b in sorted({r['批次'] for r in rows})},
                   completion_warning='Candidate partial software scopes, not predicted full acceptances; no completion evidence created.',
                   duration_minutes=dict(current_bench_lower=750, current_bench_upper=995,
                                         production_additional_lower=180, production_additional_upper=300))
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', 'utf8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
