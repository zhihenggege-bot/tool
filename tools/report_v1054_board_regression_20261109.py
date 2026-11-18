"""Summarize actual V10.54 flash/test evidence without reclassifying old results."""
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    base=root/'测试证据/内机实测_20261105/BENCH_V1054_V1239'
    flash=json.loads((base/'flash_special_remote_20261106.json').read_text('utf8'))
    rows=[]
    for p in sorted(base.glob('remaining571_heat_dynamic_*.json')):
        data=json.loads(p.read_text('utf8'))
        if not data.get('started','').startswith('2026-11-09'):continue
        for cid,e in data.get('cases',{}).items():
            rows.append((cid,e,p,data))
    out=['# V10.54烧录及板上复测（2026-11-09）','',
         '330 V10.54 BENCH；两块316 V12.39 BENCH。压机动力隔离，软件反馈/参数/DI极性模拟，不代表端子测量、真实负载、真实断电或正式档秒数。','',
         f'烧录：{flash.get("passed")}；330逐字节校验137012字节；两块316原样保留并各校验79960字节；烧录后配置差异：{flash.get("config_changes")}。',
         '正式档与BENCH共用修复源码，正式档已编译/ARM检查；本次烧录和板上测试仅BENCH。','',
         '|用例|模式/范围|本次软件检查|批次参数恢复|证据|','|---|---|---|---|---|']
    for cid,e,p,d in rows:
        mode=e.get('mode','')
        if e.get('kind')=='remote':
            scope=f'模式{mode}远程断开/恢复'
            if e.get('passed'):
                outcome=f'断开约{e["reaction_observed_s"]:.3f}s停机；恢复后自动重启执行器'
            else:outcome='未完成' if not e.get('error') else '异常：'+e['error'].splitlines()[-1]
        else:
            scope=e.get('scope','')
            if cid=='T10-014' and e.get('gateway_register'):
                scope=f'目标3，禁用运行压机并补位；网关[{e["gateway_register"]}]'
            elif cid.startswith('T09-') and e.get('runs'):
                scope=f'环温制冷{e["runs"][0]["temperature"]/10:.1f}℃，目标/316台数升降收敛'
            outcome='已完成软件检查' if e.get('passed') else ('异常：'+e['error'].splitlines()[-1] if e.get('error') else '未完成')
            if e.get('phase_display_defects'):
                outcome+='；[885]阶段显示未清零：'+str(e['phase_display_defects'])
        out.append(f'|{cid}|{scope}|{outcome}|{d.get("restored","未完成")}|[原始记录]({p.relative_to(root).as_posix()})|')
    out+=['','“完成软件检查”只代表证据写明的子范围。未执行、环境受限、端子测量及正式档时序不得据此改成通过。',
          '新发现：特殊模式故障急停后内部流程和负载已停止，但[885]特殊阶段显示可能残留1。原始带“阶段必须清零”断言的首轮中断保留；后续分开核对实际停机和显示，未修改固件或掩盖显示缺陷。',
          '已完成的旧版本测试按原版本保留，不自动改成V10.54通过。',
          '\n[烧录原始记录](测试证据/内机实测_20261105/BENCH_V1054_V1239/flash_special_remote_20261106.json)']
    checks=sorted(base.glob('independent_final_readback_20261109_*.json'))
    if checks:
        final=json.loads(checks[-1].read_text('utf8'))
        out+=['',f'独立终检：{final.get("checks")}；配置差异：{final.get("configuration_mismatches")}。',
              f'[终检原始回读]({checks[-1].relative_to(root).as_posix()})']
    out+=['','[环温升降明细](环温制冷_实际台数升降复测_20261109.md)',
          '[特殊模式显示缺陷](特殊模式故障停机_阶段显示残留_20261109.md)']
    (root/'V10.54烧录及板上复测_20261109.md').write_text('\n'.join(out)+'\n','utf8')
    print('REPORT WRITTEN',len(rows),'case entries')


if __name__=='__main__':main()
