"""Read-only queue reporter; never opens COM or a probe or controls the writer."""
import ctypes
import json
import os
from pathlib import Path
import time

import full_queue_progress_20261112 as progress

D=progress.D
R=progress.R
STATE=D/'report_watcher.json'


def alive(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        return ctypes.get_last_error()==5
    try:
        code=ctypes.c_uint32()
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
        return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle(handle)


def write_json(path,data):
    temp=path.with_suffix(f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    temp.replace(path)


def finish_report(queue,writer_alive):
    progress.summarize()
    data=json.loads((D/'progress.json').read_text('utf8'))
    finished=len(queue['executed'])==len(queue['tasks']) and not queue.get('active')
    rows=['# 内外机剩余队列首轮执行汇总（2026-11-12）','',
        f"记录生成：{data['at']}；队列状态：{queue['status']}；控制器进程仍运行：{writer_alive}。",'',
        f"53批中，已执行并完成独立恢复核验{len(queue['executed'])}批，尚未完成{len(queue['tasks'])-len(queue['executed'])}批。首轮全部批次执行结束：{'是' if finished else '否'}。",'',
        '批次执行、具体用例通过和完整验收是三种不同状态。所有结论以原始输入、输出和恢复证据为准；控制代码未因首轮发现问题而整改。', '',
        '[逐项观察及证据](../../剩余全队列执行进度_20261112.md)。83项条件受限独立保留；软件DO/AO不代替物理端子测量，BENCH不证明正式秒数。', '',
        '## 执行异常与待复核观察', '',
        '以下是待复核记录，不自动判为固件缺陷；输入前提不足、既有未决口径与实际行为异常须结合证据区分。','',
        '|项目|观察与限定|证据|','|---|---|---|']
    for entry in data['execution_errors']:
        rows.append(f"|{entry['key']}|执行返回码{entry['exitcode']}，恢复审计随后完成；须检查原始日志。|controller.json|")
    for entry in data['cases']:
        fields=('passed','software_scope_passed','matches','behavior_matches','observed_matches_command','all_sample_frequency_hold')
        negatives=[key for key in fields if entry.get(key) is False]
        note=entry.get('review_notes','')
        qualified=any(word in note for word in ('不足','未建立','未证明','未决','暂缓','待补测'))
        if not negatives and not qualified:
            continue
        label=entry.get('id',entry.get('label',str(entry.get('parameter','观察'))))
        if entry.get('label') and entry.get('id'):
            label+=' '+entry['label']
        detail='；'.join(negatives+[str(entry.get('error','')),note]).replace('|','/').replace('\n',' ')
        evidence=Path(entry['evidence']).name
        rows.append(f"|{label}|{detail}|[{evidence}]({evidence})|")
    formal=data.get('production')
    rows+=['','## 正式时序及连续两小时观察','']
    rows.append('正式时序原28行保留，逐例执行范围及未关闭条款见进度报告。')
    rows.append('正式控制器状态：'+str(formal) if formal else '正式队列尚无执行记录。')
    soak=[]
    for path in (D/'PRODUCTION').glob('*.json'):
        try:
            raw=json.loads(path.read_text('utf8'))
        except (OSError,ValueError):
            continue
        if not isinstance(raw,dict):
            continue
        entry=raw.get('cases',{}).get('T13-064')
        if isinstance(entry,dict):
            soak.append(dict(evidence=path.name,elapsed_s=entry.get('elapsed_s'),
                passed=entry.get('passed',False),restored=raw.get('restored',False),
                error=raw.get('error')))
    rows.append('连续两小时证据：'+json.dumps(soak,ensure_ascii=False) if soak else '连续两小时观察尚无完成证据，不能计为通过。')
    report=D/'首轮执行汇总.md'
    temp=report.with_suffix(f'.{os.getpid()}.tmp')
    temp.write_text('\n'.join(rows)+'\n',encoding='utf8')
    temp.replace(report)
    return report


def main():
    if STATE.exists():
        old=json.loads(STATE.read_text('utf8'))
        assert not alive(old['pid']),'A read-only report watcher already exists'
    state=dict(pid=os.getpid(),started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),read_only=True,
        hardware_access=False,status='watching')
    write_json(STATE,state)
    try:
        while True:
            queue=json.loads((D/'controller.json').read_text('utf8'))
            writer_alive=alive(queue['pid'])
            state.update(updated=time.strftime('%Y-%m-%dT%H:%M:%S%z'),writer_alive=writer_alive,
                writer_status=queue['status'],executed=len(queue['executed']),active=queue.get('active',{}).get('key'))
            progress.summarize()
            if queue['status']!='running' or not writer_alive:
                report=finish_report(queue,writer_alive)
                state.update(status='reported',report=str(report.relative_to(R)))
                write_json(STATE,state)
                print('FINAL READ-ONLY REPORT',report,flush=True)
                return
            write_json(STATE,state)
            time.sleep(30)
    except BaseException as exc:
        state.update(status='reporter_error',error=repr(exc))
        write_json(STATE,state)
        raise


if __name__=='__main__':
    main()
