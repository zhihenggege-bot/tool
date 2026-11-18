"""Summarise completed, restored board batches without rewriting old CSV."""
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    records=json.loads((BASE/'case_results.json').read_text('utf8'))
    batches=[]
    for p in sorted(BASE.glob('remaining571_heat_dynamic_*_20261106_*.json')):
        d=json.loads(p.read_text('utf8'))
        if not any(x in p.name for x in ('remaining_pid_', 'remaining_exact_', 'initial_boundaries_',
            'preheat_temperature_boundaries_', 'environment_heat_targets_', 'humidity_exact_deadband_',
            'default_ambient_preheat_', 'auto_humidity_continuity_', 'di_protection_matrix_', 'eev_live_matrix_',
            'eev_live_midpoints_', 'mode_temperature_humidity_permissions_', 'auto_long_qhs_',
            'fan_enumerations_', 'compatibility_extra_di_', 'loaded_modes_to_disinfect_',
            'all_thirty_mode_transitions_', 'serial_environment_cool_targets_',
            'serial_fan_enumerations_', 'serial_compatibility_extra_di_', 'serial_auto_long_qhs_',
            'serial_di_protection_matrix_', 'serial_ys_permissions_', 'serial_heat_upper_boundaries_',
            'serial_multifault_priorities_', 'serial_normal_mode_handoffs_')):
            continue
        batches.append(dict(evidence=p.relative_to(ROOT).as_posix(),restored=d.get('restored'),
            cases=list(d.get('cases',{})),error=d.get('error',''),
            test_aborted=d.get('aborted_due_to_test_precondition',False) or bool(d.get('interrupted_by_test_supervisor')),
            explanation=d.get('test_error_explanation','') or d.get('interrupted_by_test_supervisor',{}).get('reason',''),
            case_errors=[dict(id=cid,error=e['error'].splitlines()[-1],
                classification=e.get('result_classification') or ('采集异常，非功能结论' if any(x in e['error'] for x in ('STLink error','Get IDCODE','DP error')) else '未通过，见原始时序'))
                for cid,e in d.get('cases',{}).items() if isinstance(e,dict) and e.get('error')]))
    paths={b['evidence']:b for b in batches if b['restored'] is True}
    rows=[dict(id=cid,**{k:r.get(k) for k in ('status','actual','evidence','at')})
          for cid,r in sorted(records.items()) if r.get('evidence') in paths and r.get('status')!='未测']
    for row in rows:
        errors={e['id']:e for e in paths[row['evidence']]['case_errors']}
        error=errors.get(row['id'],{})
        row['interpretation']=(error['classification'] if error.get('classification','').startswith('环境受限')
                               else '采集异常，非功能结论' if error.get('classification')=='采集异常，非功能结论'
                               else '功能未通过，保留原始记录' if row['status']=='失败'
                               else row['status'])
    skips=json.loads((BASE/'environment_skips_20261106.json').read_text('utf8'))['cases']
    report=dict(scope='本轮续测软件证据，逐例范围以原始日志为准',cases=rows,batches=batches,
        counts=dict(Counter(r['status'] for r in rows)),
        interpreted_counts=dict(Counter(r['interpretation'] for r in rows)),environment_skips=len(skips),
        board_firmware_changed=False,
        source_fix='消排毒远程恢复修正已构建V10.54两档并完成30组ARM回归；板上仍V10.53，未烧录。',
        limits='测试版；软件输入模拟和软件输出回读，不代表物理端子、真实断电或正式时序验收。')
    (BASE/'live_continuation_summary_20261106.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    lines=['# 内机继续测试结果（2026-11-06）','',report['limits'],'',
        f'已结束且已恢复批次中，本轮逐例记录{len(rows)}项：{report["interpreted_counts"]}。当前条件不足跳过{len(skips)}项，均不计通过。',
        '', report['source_fix']+'失败、测试方法异常、恢复及复测历史保留；运行中批次不计入已恢复结果。',
        '', '|执行|用例|结果及实际覆盖|证据|','|---|---|---|---|']
    for r in rows:
        lines.append(f'|[x]|{r["id"]}|{r["interpretation"]}；{str(r["actual"]).replace(chr(10)," ").replace("|","／")}|[原始日志]({r["evidence"]})|')
    lines+=['','|批次异常|参数恢复|说明|','|---|---|---|']
    for b in batches:
        if b['error'] or b['test_aborted']:
            detail=b['explanation'] or b['error'].splitlines()[-1]
            if b['evidence'].endswith('auto_humidity_continuity_20261106_114106.json'):
                detail='测试方法不足：59秒才发工程映射撤销，实际输入送达时已触发切换；原始异常保留，后续改58秒撤销完整复测。不是已证实的固件提前切换。'
            elif b['evidence'].endswith('auto_humidity_continuity_20261106_120607.json'):
                detail='测试计时起点不足：首次读到计数1已处于该秒中段，58.391秒不能直接判提前；后续逐计数并以计数2首次边沿计完整58秒复测。原始异常保留。'
            elif b['evidence'].endswith('serial_auto_long_qhs_600_20261106_151236.json'):
                detail='测试脚本结束判据不足：600秒公开计数清零并进入正常停机步骤3，但模式寄存器待正常退出后才更新；旧脚本5秒内等模式更新而超时。原始全计数保留，后续分别验证切换启动边沿和新模式运行建立。'
            lines.append(f'|[{Path(b["evidence"]).name}]({b["evidence"]})|{b["restored"]}|{detail.replace("|","／")}|')
        for e in b['case_errors']:
            detail=f'{e["id"]}：{e["classification"]}；{e["error"]}'
            lines.append(f'|[{Path(b["evidence"]).name}]({b["evidence"]})|{b["restored"]}|{detail.replace("|","／")}|')
    lines+=['','[条件不足跳过清单](本轮跳过项目_内机BENCH_20261106.md)；[571例证据盘点](尚待补测证据盘点_20261106.md)。',
        '', '[DA8遗留冷水阀的未决观察](DA8遗留冷水阀_续测观察_20261106.md)：制冷中确有软件输出，介质启用口径未定；不因其它模式测试通过而关闭该问题。']
    (ROOT/'内机继续测试结果_20261106.md').write_text('\n'.join(lines)+'\n','utf8')
    print(json.dumps(dict(recorded=len(rows),counts=report['counts'],skipped=len(skips)),ensure_ascii=False))


if __name__=='__main__':main()
