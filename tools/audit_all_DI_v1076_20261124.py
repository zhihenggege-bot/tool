"""Audit all14-input retest, current user polarities, image and save restoration."""
import json
import struct
import time
from contextlib import ExitStack
import board_all_DI_v1076_20261124 as b


def main():
    dep,d,day=b.dep,b.d,b.DAY
    board=json.loads((day/'board.json').read_text('utf8'))
    assert board['sequence_completed'] and board['restored'] and len(board['covered'])==13
    assert len(board['failures'])==1 and board['failures'][0]['input']=='X02'
    failed=[row for row in board['checks'] if not row['passed']]
    assert len(failed)==1 and failed[0]['name']=='X02 short remote stop request ignored'
    supplement=json.loads((day/'X02专项复核/board.json').read_text('utf8'))
    root_cause=json.loads((day/'X02_ARM原因复核.json').read_text('utf8'))
    assert supplement['passed'] and supplement['restored'] and root_cause['passed']
    assert all(row['passed'] for row in supplement['checks'])
    # Independently inspect every captured sample for cross-channel false
    # faults, not just the polling predicates used during stimulus generation.
    source_faults={ch:f for ch,f in zip(b.NAMES,b.FAULT)}
    reviewed=0;confirmed=set()
    with (day/'samples.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            z=json.loads(line);label=z['label']
            if not label.startswith('X') or label[1:3] not in b.NAMES:continue
            ch=label[1:3];v=z['values']
            actual_faults={a for a in b.FAULT if a is not None and v[str(a)]}
            expected=source_faults[ch]
            assert actual_faults <= ({expected} if expected is not None else set()),(label,actual_faults)
            if expected is not None and expected in actual_faults:confirmed.add(ch)
            reviewed+=1
    assert confirmed==set(b.NAMES)-{'02'},confirmed
    path=day/'final_audit.json';assert not path.exists()
    q=dict(started=d.now(),passed=False,images=[],save_samples=[],
        independent_raw_sample_review=reviewed,no_cross_channel_false_faults=True)
    def save():dep.dump(path,q)
    touched={int(w['address']) for w in board['writes'] if w['address'] not in (398,524)}
    with ExitStack() as stack:
        c=d.client();stack.callback(c.close)
        q['snapshot']=d.snap(c)
        assert dep.POSTBOOT_STOPPED(q['snapshot']) and q['snapshot']['2622']==dep.EXPECTED
        actual=d.config(c)
        q['configuration_mismatches']={a:[v,actual[a]] for a,v in board['original'].items()
            if int(a) not in (1875,1923) and actual[a]!=v}
        assert not q['configuration_mismatches']
        q['restored_polarities']={f'X{ch}':actual[str(a)] for ch,a in zip(b.NAMES,b.POLARITY)}
        assert q['restored_polarities']==board['polarity_baseline']
        for bd in dep.BOARDS:
            image=dep.NEW if bd[0]=='330' else bd[6]
            ss=stack.enter_context(d.ConnectHelper.session_with_chosen_probe(unique_id=bd[1],target_override=bd[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            row=dict(board=bd[0],verified_bytes=d.verify(ss.target,image),runtime=d.runtime(ss.target,image.with_suffix('.axf')))
            assert row['runtime']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180)
            q['images'].append(row)
            if bd[0]=='330':t=ss.target;sy=d.symbols(image.with_suffix('.axf'))
        began=time.monotonic();notice=began
        while True:
            cache=list(struct.unpack('<500H',bytes(t.read_memory_block8(sy['Old_Parameter'],1000))))
            pending={str(a):[cache[a],actual[str(a)]] for a in touched if cache[a]!=actual[str(a)]}
            row=dict(at=d.now(),pending=pending,state=t.read8(sy['IndoorParameterSaveState']),
                error=t.read16(sy['CPURomWriteError']))
            q['save_samples'].append(row);save();assert row['error']==0
            if not pending and row['state']==0:break
            assert time.monotonic()-began<150,row
            if time.monotonic()-notice>20:
                print('WAIT restored current user settings EEPROM cache',pending,flush=True);notice=time.monotonic()
            time.sleep(.5)
        keys=set(a for a in b.FAULT if a is not None)|{605,710,819,861,924}
        q['final_feedback']={str(a):c.read_holding_registers(1,a,1)[0] for a in sorted(keys)}
        assert not any(q['final_feedback'].values())
        timings=[]
        for item in board.get('timings',[]):
            r=dict(item)
            if 'overload' in r['test']:
                fault=956 if r['test'].startswith('X11') else 958
                edge=next(e for e in board['events'] if e['t']>=r['input_write_t'] and e['edges'].get(str(fault))==1)
                r.update(first_confirmed_t=edge['t'],observed_delay_s=edge['t']-r['input_write_t'])
            timings.append(r)
        q.update(passed=True,restored=True,finished=d.now(),checks=len(board['checks']),covered=board['covered'],timings=timings,
            original_failed_checks=failed,supplement_checks=len(supplement['checks']),all14_exercised=True,
            all14_acceptance_passed=False,remaining_discrepancy='X02 remote-off path does not qualify3s; actual code and board confirmed, original failure retained',
            remote_followup={k:supplement.get(k) for k in ('start_total_s','remote_stop_request_s','automatic_restart_total_s')})
        save()
    lines=['# 全部14路DI按用户当前极性复测\n\n',
        '330 V10.76正式版、两台316 V12.56；未修改固件。用户本轮开始时14路极性均为1，作为本轮唯一恢复基准。\n\n',
        '本轮只通过正常Modbus临时翻转逐路极性模拟触发，读取板上真实输入/滤波状态、独立故障、DO/AO及外机GPIO；SWD全程只读。未切换实体接点。\n\n',
        '| DI | 独立故障 | 本轮结果 |\n| --- | --- | --- |\n']
    for ch,fault in zip(b.NAMES,b.FAULT):
        verdict='启停/恢复验证；停机不足3秒单列差异' if ch=='02' else '通过'
        lines.append(f"| X{ch} | {fault if fault is not None else '控制输入，无故障'} | {verdict} |\n")
    lines.extend(['\n## 记录到的持续输入确认时间\n\n| 项目 | 秒 |\n| --- | --- |\n'])
    for r in q['timings']:lines.append(f"| {r['test']} | {r['observed_delay_s']:.3f} |\n")
    lines.extend(['\n时间从极性命令写入开始到首次观察，包含串口/读回采样间隔，不代替物理触点测量。短时滤波按原100ms/1s节拍，未修改计时器或加速正式档。\n\n',
        '- X00/X01/X03/X04/X13：短脉冲、持续触发独立故障、报警、通风风机保护停机、恢复后锁存及复位。\n',
        '- X05：短于15秒中断不报警，持续15秒确认909，只报警，通风风机不停。\n',
        '- X06/X07/X10：分别966/968/910，短脉冲不报、持续输入报警、输入恢复后锁存及复位；通风风机不停。本轮未接加热/加湿实际负载，不能声称负载带载切断验收。\n',
        '- X02：本地信号0/1均不接管，远程有效输入开机、撤销输入正常停机、恢复输入自动重启，无故障报警。原短停请求不生效的检查失败，记录保留，不能算全部验收通过。专项板测补齐正常停机及自动重启；停机请求未等3秒。\n',
        '- X11/X12：按排风DO和回风AO运行条件验证956/958、605/Y05、风机保护停机、未解除时不能清锁存、恢复后复位。\n',
        '- X15/X14：送风DO/回风AO，启动连续10秒许可，中断重计；未满60秒缺压不报，满60秒后短7秒缺压不报、恢复清计时、再次连续10秒缺压独立报警并停机；恢复后复位。\n\n',
        f"主轮共{len(board['checks'])}项检查，{len(board['checks'])-1}通过、1项X02短停判据未通过；X02专项另{len(supplement['checks'])}项观察与恢复检查通过。全部14路均已执行，13路报警输入通过，X02停机延时单列差异，不能宣布14路全部验收通过。所有设置恢复为本轮开始值（包括14路极性均1），三块镜像一致，保存缓存恢复、保存状态空闲、EEPROM错误0。最终全部独立故障、605/710/861/924/Y05均0。\n\n",
        'X02根因：DI_Points_Process只对有效输入累计3秒，失效时X02_En很快清0；SwitchStatusProcess读取FarSwitchX02=X02_En即撤销运行请求，独立BoardErrAction的3秒停机计时未约束该直接路径。V10.75/V10.76两种极性ARM复现一致，不是新DI诊断或用户极性改变引入。原规格外部联锁条款要求断开持续3秒，后续远程保持接点要求未明确取消延时，故保留差异待用户决定；本轮未修改固件。\n\n',
        '限制：通风模式及输入模拟测试，外机压机全程停机，未验收压机带载切断、实体继电器触点、真实压力反馈和真实断电。本轮结果不能代替这些整机实测。\n'])
    (day/'测试结果.md').write_text(''.join(lines),'utf8')
    print('FINAL ALL DI AUDIT:14 inputs exercised;13 alarm inputs pass,X02 off-delay discrepancy retained;current user settings restored',flush=True)


if __name__=='__main__':main()
