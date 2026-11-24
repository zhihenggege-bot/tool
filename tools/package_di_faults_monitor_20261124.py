"""Package the verified DI monitor and record firmware scope; no board access."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
import build_di_faults_v1076_20261124 as b

R=b.R
S=R/'psc330_monitor_tool/psc330_monitor'
D=R/'监控工具_FFP-2026.11.24b'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    fw=json.loads((b.DAY/'DI_ARM_regression.json').read_text('utf8'))
    di=json.loads((b.OUT/'monitor_di_tests.json').read_text('utf8'))
    prior=json.loads((b.OUT/'monitor_fault_regression.json').read_text('utf8'))
    smoke=json.loads((b.OUT/'monitor_exe_smoke.json').read_text('utf8'))
    assert fw['passed'] and len(fw['checks'])==190
    assert di['passed'] and di['total']==115
    assert prior['total']==prior['passed']==362
    assert di['version']==prior['version']==smoke['version']=='FFP-2026.11.24b'
    assert smoke['gui_created'] and not smoke['serial_opened']
    assert sha(S/'app.py')==di['source_sha256']==prior['source_sha256']
    manifest_path=b.OUT/'PRODUCTION/manifest.json'
    manifest=json.loads(manifest_path.read_text('utf8'))
    before=json.loads((b.OUT/'source_before.json').read_text('utf8'))
    assert b.inventory()==manifest['source_inventory']
    changed=[n for n,h in manifest['source_inventory'].items() if before[n]!=h]
    assert set(changed)=={'PSC330RK-V10-内机/User/UserHead/User.h',
                          'PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c'}
    assert all(sha(b.OUT/'PRODUCTION'/n)==h for n,h in manifest['artifacts'].items())
    assert fw['image_sha256']==sha(b.OUT/'PRODUCTION/PSC330_V10.76_PRODUCTION.axf')
    D.mkdir(exist_ok=True)
    shutil.copy2(b.OUT/'monitor_dist/PSC330_PSC316_Monitor.exe',D/'PSC330_PSC316_Monitor.exe')
    src=D/'Python源码';src.mkdir(exist_ok=True)
    for name in ('app.py','pt_tables.py','PSC330_PSC316_Monitor.spec','README.md',
                 'test_fault_summary.py','test_di_protections.py'):
        shutil.copy2(S/name,src/name)
    notes=(
        'PSC330 / PSC316 监控工具 FFP-2026.11.24b\n'
        '双击PSC330_PSC316_Monitor.exe，无需安装Python。\n'
        '故障 → DI保护明细：逐路查看当前输入与独立确认故障。\n'
        '新固件330 V10.76补齐消防960、风阀联锁962、漏水964。\n'
        '故障地址和1=故障固定，不随极性改变；检测延时、停机范围、复位规则沿用原逻辑。\n'
        '常开设置：闭合触发；常闭设置：断开触发。故障解除后按原规则复位。\n'
        'X02为远程启停，不是故障。X14/X15当前输入1=压差许可，故障另看913/912。\n'
        '600为新风温度探头故障；加湿器故障为910。\n'
        '补齐909～913轮询；删除无数据来源的旧显示。详细地址表见Python源码/README.md。\n'
        '低于330 V10.76或版本未知时，新反馈显示版本要求，不作无故障判定。\n'
        '本次仅修改、编译及离线验证，尚未烧录或进行实体触点板测。\n'
        '监控软件不会自动升级固件或改写设备参数。\n')
    (D/'使用说明.txt').write_text(notes,'utf8')
    for path,name in ((b.OUT/'monitor_di_tests.json','DI显示验证.json'),
                      (b.OUT/'monitor_fault_regression.json','外机故障显示回归.json'),
                      (b.OUT/'monitor_exe_smoke.json','EXE启动检查.json')):
        shutil.copy2(path,D/name)
    (D/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(D).as_posix()+'\n'
        for p in sorted(D.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'),'utf8')
    dest=R/(D.name+'.zip')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(D.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(D).as_posix())
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for p in D.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(D).as_posix())).hexdigest()==sha(p)
    report=dict(passed=True,firmware_version='10.76',monitor_version=di['version'],
        changed_firmware_sources=changed,firmware_artifacts=manifest['artifacts'],
        firmware_ARM_checks=len(fw['checks']),monitor_DI_checks=di['total'],
        outdoor_monitor_regression_checks=prior['total'],source_sha256=sha(S/'app.py'),
        exe_sha256=sha(D/'PSC330_PSC316_Monitor.exe'),zip_sha256=sha(dest),
        archive_verified=True,flashed=False,hardware_tested=False,device_parameters_changed=False)
    (b.DAY/'交付核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    for name in ('monitor_di_tests.json','monitor_fault_regression.json','monitor_exe_smoke.json'):
        shutil.copy2(b.OUT/name,b.DAY/name)
    manifest.update(offline_verified=True,offline_evidence=str((b.DAY/'DI_ARM_regression.json').relative_to(R)))
    manifest_path.write_text(json.dumps(manifest,indent=2),'utf8')
    text='''# DI独立故障与监控软件修改说明

330 V10.76（正式档）；监控软件FFP-2026.11.24b。未修改316。

## 用户确认要求

每路保护DI的故障地址固定，1始终表示确认故障。常开设置闭合触发，常闭设置断开触发，极性只参与输入判定。检测使能、延时、停机范围和复位规则保持原有逻辑。

## 固件

补齐330[960]消防、[962]风阀联锁、[964]漏水独立锁存。取原有极性处理和3秒滤波后的同一输入；原fireValveFlag和605综合保护控制路径不变。新增三个寄存器不参与控制决策。已有524复位时同步清除诊断锁存；输入未解除则同一扫描重新置位。输入单独恢复时保留故障原因。上电由原有RAM初始化清零，不增加参数保存。

只改User.h（三个宏及版本）和ErrorCheck.c（诊断置位及复位），没有修改压机、风机、EEV、四通阀、化霜、PID和输出时序源码。

## 地址表

| DI | 独立确认故障 | 当前输入 | 极性参数 |
| --- | --- | --- | --- |
| X00 电源/相序 | 911 | 1350 | 155 |
| X01 消防 | 960（本次补齐） | 1351 | 156 |
| X02 远程启停 | 无，控制输入 | 1352 | 157 |
| X03 送风机/泵过载 | 601 | 1353 | 158 |
| X04 风阀联锁 | 962（本次补齐） | 1354 | 159 |
| X05 滤网堵塞 | 909 | 1355 | 389 |
| X06 主加热/再热 | 966 | 1356 | 390 |
| X07 预热 | 968 | 1357 | 391 |
| X10 加湿器 | 910 | 1358 | 392 |
| X11 排风机过载 | 956 | 1359 | 393 |
| X12 回风机过载 | 958 | 1360 | 394 |
| X13 漏水 | 964（本次补齐） | 1361 | 395 |
| X14 回风压差 | 913 | 1362 | 396 |
| X15 送风压差 | 912 | 1363 | 397 |

X14/X15当前输入1为压差许可，0为不满足；故障仍按配置启用并经原检测时间确认，不能把许可位直接当故障位。常规故障DI的0反相/常闭断开报警、1正相/常开闭合报警保留。X02极性控制启停请求，无报警位。

## 监控软件

故障页增加“DI保护明细”；补入601及909～913，修正600只表示新风温度探头故障。补齐909～913轮询，删除955/957/959/961/963/965/967无数据来源的旧显示，当前输入改用1350～1363。明确X14/X15是许可、X02是控制。旧固件或版本未知时三项新增故障显示版本要求，不把未实现地址的0解释为无故障。设备通讯和写入流程未改变。

## 验证与限制

- Keil正式档编译：0错误、0警告。
- 实际ARM机器码190项检查通过：常开/常闭极性、原3秒滤波、独立/同时/先后故障、故障恢复与复位、未解除复位重新置位。
- 其中按六种模式和八种故障组合，对V10.75/V10.76所有已有Parameter值、DO/AO数组、内外机指令及相关状态，逐一比较触发、恢复、复位三个阶段；除新增诊断值外一致。
- 监控软件115项映射/轮询/真实Tk表格显示检查、362项原外机故障摘要回归通过。源码GUI与打包EXE启动检查通过，无串口连接。
- ZIP内容、源码和EXE哈希已核验，记录见交付核验.json。
- 本次未烧录、未操作板上参数、未进行实体接点验证；以上为编译及离线代码验证。配套新反馈需将330升级到V10.76。
'''
    (b.DAY/'修改与验证说明.md').write_text(text,'utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print('PACKAGE:',dest,flush=True)


if __name__=='__main__':main()
