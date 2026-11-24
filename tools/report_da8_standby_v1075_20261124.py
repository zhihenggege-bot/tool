"""Generate reviewable result bound to the final flashed image and board trial."""
import json
import shutil
import build_da8_standby_v1075_20261124 as build
import deploy_da8_manual_v1074_20261124 as dep


def main():
    day=build.DAY
    audit=json.loads((day/'final_audit.json').read_text('utf8'))
    arm=json.loads((day/'standby_ARM_regression.json').read_text('utf8'))
    deployment=json.loads((day/'deployment_final.json').read_text('utf8'))
    assert audit['passed'] and arm['passed'] and deployment['passed']
    image=build.OUT/'PRODUCTION/PSC330_V10.75_PRODUCTION.axf'
    tested=[(p,json.loads(p.read_text('utf8'))) for p in day.glob('board_standby*.json')]
    tested=[(p,q) for p,q in tested if q.get('passed') and q.get('restored') and q.get('image_sha256')==dep.d.sha(image)]
    assert len(tested)==1
    test_path,test=tested[0]
    traces={}
    for path in day.glob('*samples.jsonl'):
        rows=[json.loads(line) for line in path.read_text('utf8').splitlines()]
        traces[path.name]=dict(samples=len(rows),sha256=dep.d.sha(path),
            first=rows[0]['at'],last=rows[-1]['at'],
            unexpected_compressor_gpio=sum(any(v for bo in z['outdoor'] for v in bo['gpio'][:2]) for z in rows))
        assert not traces[path.name]['unexpected_compressor_gpio']
    dep.dump(day/'trace_inventory.json',traces)
    final=audit['final_water']
    text=f'''# DA8正常停机防冻 V10.75 — 2026-11-24

用户要求：“要求低于0℃时停机也保持最低开度”。规格§3.11.10原文为“新风温度小于0度时蒸汽阀门/热水阀门开启度不得小于最小开度（可设）”。本项目DA8用于冷热两用水盘管，DA0、DA1、DA9用于电加热。

## 最终行为

- 新风温度330[512]低于0℃且330[346]>0时，正常待机及正常启停过渡也保持DA8最低开度，与所选制冷／制热／通风等模式无关。
- 正常制冷／制热运行时取max(247手动开度,346最低开度)；停机及其他阶段只保持346，不继续输出较大的247手动值。
- 新风达到0℃或346改为0时，正常停机输出归零。控制不改写247。
- 故障、急停、联锁及必须有效的新风探头故障仍优先关闭水阀。防冻停机豁免不扩展成故障豁免。
- 346启用时，新风探头在所有模式下均为必需探头，不能被原通风／可选探头门禁屏蔽。346为0时保留原探头是否必需的判定，原手动控制不受无关探头故障影响。
- 无新增地址；247、346范围仍0～1000，分别对应0～100%。925为水阀输出显示、922为最终DA8指令；它们和PWM均属于软件／驱动寄存器证据。

## 代码范围

仅修改内机UserAction.c、ErrorCheck.c和User.h版本号；source_changes.diff保留完整差异。两台316保持V12.56，全量图像比对通过。所有正式时序参数保持原值。

## 验证结果

Keil正式档构建0错误、0警告。最终AXF执行{len(arm['checks'])}项ARM检查通过，覆盖所有模式、启停阶段、手动值、最低值、0℃边界、动态退出及急停／消防／风阀联锁／漏水／传感器故障等优先级；运行手动控制与V10.74比较一致，未启用防冻时无关新风故障不改变手动开度。

最终板测记录{test_path.name}共{len(test['cases'])}项检查通过：

- 使用现场原始新风−3.2℃读数，正常停机时DA8=200、PWM=196。
- 停机下手动0或1000都只输出最低值200；最低值1000输出满量程；制热／通风选择同样保持防冻。
- 新风−0.1℃输出最低值，到0℃或+0.1℃输出归零；346在冷态改0也归零。
- 正常制冷启动后手动500仍输出500，手动0受200最低值约束；正常停机完成后保留200。
- 原始NTC采集模拟失效后固件自行报警，330[600]=1、Y05软件输出为1、水阀关闭；恢复有效输入并普通复位后，停机防冻恢复200。
- 全程保留时间戳及室外DO采样，未请求压机加载，两台316压机GPIO始终为0；未强写输出、派生温度、故障或计时状态。

初次抓取出现同一扫描内的DA／显示中间清零值，导致连续匹配脚本超时，但对应584组原始采样中PWM均保持196，没有据此判为硬件掉输出。原失败及参数恢复记录保存在board_standby.json和原JSONL。采集脚本随后保留每次原始观察，并在DA、显示、最终值和PWM组成一致数值组时判定；全部原始轨迹仍保留在trace_inventory.json中。

首轮烧录后兼容性审阅发现，对未启用防冻的无关新风故障不应增加手动关阀条件，已收窄判断。最终烧录准备曾因备份文件同名而在编程开始前退出；该失败记录保留为deployment_final_backup_name_attempt1.json，未覆盖原备份，随后使用独立备份文件名完成最终烧录。初步产物保存在initial_board_build；最终版本重新执行ARM、烧录全量校验及完整板测，最终结论绑定最终AXF哈希，不以初步板测替代。

## 恢复及当前状态

临时参数已恢复到本轮烧录前现场值，330[247]={final['manual']}、330[346]={final['minimum']}，新风温度{final['fresh10']/10:.1f}℃，正常停机时水阀输出{final['final']}（{final['final']/10:.0f}%），PWM比较值{final['pwm']}。机组其余执行输出关闭，故障及Y05软件输出为0。正式档标记0，最短停机120秒、最短运行180秒、环温确认1298=300秒均保持不变。保存缓存与本轮触及参数一致且空闲。

没有测量实体0～10V电压、水阀真实行程，也未进行本轮物理断电。这些不包含在本次板上软件验收中。

最终HEX：.codex-tmp/da8_standby_v1075_20261124/PRODUCTION/PSC330_V10.75_PRODUCTION.hex

HEX SHA256：{dep.d.sha(image.with_suffix('.hex'))}

AXF SHA256：{dep.d.sha(image)}

烧录证据：deployment_final.json；原始参数及初步烧录：deployment.json；最终参数及图像核对：final_audit.json。
'''
    (day/'修改与验证说明.md').write_text(text,'utf8')
    files=['build_da8_standby_v1075_20261124.py','test_da8_standby_v1075_arm_20261124.py',
        'deploy_da8_standby_v1075_20261124.py','deploy_da8_standby_final_v1075_20261124.py',
        'board_da8_standby_v1075_20261124.py','audit_da8_standby_v1075_20261124.py','report_da8_standby_v1075_20261124.py',
        'deploy_da8_manual_v1074_20261124.py','board_da8_manual_v1074_20261124.py']
    for name in files:shutil.copy2(build.R/'tools'/name,day/name)
    print('REPORT COMPLETE',len(test['cases']),'board cases;',len(arm['checks']),'ARM checks',flush=True)


if __name__=='__main__':main()
