"""Write scoped conclusions from completed journals; no hardware access."""
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    base=root/'测试证据/内机实测_20261105/BENCH_V1054_V1239'
    p=max(base.glob('*ambient_actual*json'),key=lambda p:p.stat().st_mtime)
    d=json.loads(p.read_text('utf8'))
    assert d.get('restored') and not d.get('error') and not d.get('cleanup_error')
    rows=d['completed_runs']
    complete=[k for k,v in rows.items() if len(v)==2]
    incomplete=[k for k,v in rows.items() if len(v)!=2]
    lines=['# 环温制冷目标到压机反馈续测（2026-11-09）','',
           '330 V10.54 / 316 V12.39 BENCH；压机动力隔离。仅软件运行反馈，非端子或真实压机运行证据。',
           'CN=4，HLC=22℃、HLM=35℃。正常参数及合法NTC校准，一次升程、一次降程；采到精确目标温度，稳定观察允许±0.1℃且公式台数不变，目标与316制冷反馈台数稳定3秒。','',
           '|输入℃|公式台数|已完成方向|本批结论|','|---|---:|---|---|']
    for k,v in rows.items():
        temp=int(k)
        expected=0 if temp<=220 else 4 if temp>=350 else (4*(temp-220)+129)//130
        lines.append(f'|{temp/10:.1f}|{expected}|{", ".join(e["direction"] for e in v) or "无"}|'+
                     ('双向软件检查完成' if len(v)==2 else '缺方向证据，仍待测')+'|')
    lines+=['',f'双向完成{len(complete)}点；{len(incomplete)}点未完成双向。输入抖动跨台数边界跳过{len(d.get("environment_skips",[]))}个方向，不判通过。',
            '跳过方向：'+', '.join(f'{e["direction"]} {e["temperature"]/10:.1f}℃' for e in d.get('environment_skips',[]))+'。',
            '配置恢复成功；未发生脚本异常。排序三轮复现、实际端子及正式时序仍待测。',
            f'\n[原始证据]({p.relative_to(root).as_posix()})']
    (root/'环温制冷_实际台数升降复测_20261109.md').write_text('\n'.join(lines)+'\n','utf8')
    finalpath=max(base.glob('independent_final_readback_20261109_*.json'))
    final=json.loads(finalpath.read_text('utf8'))
    assert final['passed']
    heading='## 2026-11-09 V10.54本轮复测收尾'
    text='\n\n'+heading+'\n\n'+'''- [x] V10.54 BENCH烧录校验成功；六种模式远程停机/恢复均建立执行器并恢复重启，批次参数已恢复。正常冷热模式未覆盖压机负载运行中的远程断开；物理接点另验。
- [x] 特殊模式阀等待阶段12组中止控制检查完成；其中三模式相序/消防六组仍有[885]=1的显示残留，实际负载已停。该显示缺陷未改固件，不判整项验收通过。
- [x] Target=3动态禁用运行压机并补位的软件检查完成；CN保持4、目标保持3，禁用参数已恢复。
'''+f'- [x] 环温制冷11点升降续测：{len(complete)}点双向软件收敛完成；{len(incomplete)}点仍缺方向证据，输入抖动跳过方向不算通过。\n'+\
f'- [x] 独立只读终检全部通过：版本、BENCH档、全量配置恢复、网关禁用恢复、内外机停止、无报警；配置差异为空。 [终检证据]({finalpath.relative_to(root).as_posix()})\n\n'+\
'本轮未改固件源码；正式档未烧录实测。以上子检查不等于全部剩余项目已通过。\n\n[V10.54本轮汇总](V10.54烧录及板上复测_20261109.md)；[环温明细](环温制冷_实际台数升降复测_20261109.md)；[显示缺陷](特殊模式故障停机_阶段显示残留_20261109.md)。\n'
    report=root/'内机测试版逐项测试记录_20261105.md'
    current=report.read_text('utf8')
    if heading not in current:report.write_text(current+text,'utf8')
    remote=root/'消排毒远程恢复_缺陷记录_20261106.md'
    current=remote.read_text('utf8')
    h='## 2026-11-09 远程恢复板上回归完成'
    if h not in current:
        remote.write_text(current+'\n\n'+h+'\n\nV10.54 BENCH三种特殊模式及制冷/制热/通风远程停机恢复均已完成软件执行器检查；输入恢复后自动重启，无人工复位。六例约3.000～3.078秒观察到断开动作。特殊模式真实等待150秒，消毒另等20秒。配置已恢复并独立终检通过。旧V10.53失败保留；本次软件回归不代表物理接点或正式档验收。\n\n另发现特殊模式相序/消防停机后的[885]阶段显示残留，控制负载已停，详见[显示缺陷](特殊模式故障停机_阶段显示残留_20261109.md)。\n\n[本轮汇总](V10.54烧录及板上复测_20261109.md)。\n','utf8')
    print('Finalized',len(complete),'bidirectional points;',len(incomplete),'incomplete points; final readback passed')


if __name__=='__main__':main()
