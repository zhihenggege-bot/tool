"""Publish deployment/test evidence into the existing monitor delivery."""
import hashlib
import json
import shutil
import zipfile
import build_di_faults_v1076_20261124 as b


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    day=b.DAY
    audit=json.loads((day/'final_board_audit.json').read_text('utf8'))
    board=json.loads((day/'board_DI.json').read_text('utf8'))
    assert audit['passed'] and audit['restored'] and not audit['configuration_mismatches']
    assert len(board['cases'])==6 and all(row['passed'] for row in board['cases'])
    assert all(row['passed'] for row in board['checks'])
    path=day/'交付核验.json'
    q=json.loads(path.read_text('utf8'))
    previous=b.OUT/'pre_flash_delivery.json'
    assert not previous.exists()
    shutil.copy2(path,previous)
    q.update(flashed=True,hardware_tested=True,board_checks=len(board['checks']),
        device_parameters_changed=True,device_parameters_restored=True,final_configuration_changed=False,
        final_faults_and_Y05_zero=True,physical_contacts_switched=False,physical_terminal_measured=False,
        board_scope='Actual production board: unchanged physical inputs, polarity inversion via normal Modbus, independent fault/reset and Y05 software; three channels twice plus simultaneous causes',
        original_trace='board_DI.json',final_audit='final_board_audit.json',
        retained_test_issue='Original cleanup assertion included read-only refresh counters1875/1923. All129 functional checks passed; independent final audit confirms all writable settings restored.')
    report=day/'修改与验证说明.md'
    text=report.read_text('utf8')
    old='- 本次未烧录、未操作板上参数、未进行实体接点验证；以上为编译及离线代码验证。配套新反馈需将330升级到V10.76。'
    assert old in text
    text=text.replace(old,
        '- 已按用户后续要求烧录330 V10.76正式版，程序镜像完整回读通过；两台316 V12.56未改动。\n'
        '- 板上三路各测两遍，加上短脉冲、未解除复位、解除但未复位、多路并发和恢复检查，共129项功能检查通过。监控表格直接使用板上Modbus结果，三项均显示实际故障，不再显示版本要求。\n'
        '- 只通过正常Modbus临时翻转156/159/395及操作524；SWD只读，不改原始输入、滤波计时、故障、PID或输出状态。实体接点未开合，实体继电器触点未测；两种输入方向由ARM代码检查覆盖。\n'
        '- 已恢复所有实际设置，并核对保存缓存、保存状态及EEPROM错误标志。最终605/710/819/861和逐路故障均为0；设备保持停机。\n'
        '- 保留原始board_DI.json收尾断言失败：1875/1923是只读外机状态刷新计数，测试中正常递增，不能当设置值比较。修正了测试脚本的比较范围；独立final_board_audit.json确认实际参数无差异。该问题没有修改固件。')
    report.write_text(text,'utf8')
    package=b.R/'监控工具_FFP-2026.11.24b'
    notes=package/'使用说明.txt'
    contents=notes.read_text('utf8')
    contents=contents.replace('本次仅修改、编译及离线验证，尚未烧录或进行实体触点板测。',
        '已烧录330 V10.76正式版，板上极性翻转/故障锁存/复位检查通过并恢复参数；实体接点开合尚未验证。')
    notes.write_text(contents,'utf8')
    shutil.copy2(day/'final_board_audit.json',package/'烧录板测收尾核验.json')
    shutil.copy2(report,package/'修改与验证说明.md')
    (package/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(package).as_posix()+'\n'
        for p in sorted(package.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'),'utf8')
    archive=b.R/(package.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for p in package.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(package).as_posix())).hexdigest()==sha(p)
    q['zip_sha256']=sha(archive)
    path.write_text(json.dumps(q,ensure_ascii=False,indent=2),'utf8')
    print('DELIVERY UPDATED:330 V10.76 flashed;129 board checks;settings restored;ZIP verified',flush=True)


if __name__=='__main__':main()
