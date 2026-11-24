"""Verify final restored settings/images/save cache and summarize raw DI traces."""
import json
import struct
import time
from contextlib import ExitStack
import board_fan_DI_v1076_20261124 as b


def main():
    dep=b.dep;d=b.d;day=b.DAY
    board=json.loads((day/'board.json').read_text('utf8'))
    assert board['passed'] and board['restored'] and all(r['passed'] for r in board['checks'])
    path=day/'final_audit.json';assert not path.exists()
    q=dict(started=d.now(),passed=False,images=[],save_samples=[])
    def save():dep.dump(path,q)
    touched={int(row['address']) for row in board['writes'] if row['address'] not in (398,524)}
    with ExitStack() as stack:
        c=d.client();stack.callback(c.close)
        q['snapshot']=d.snap(c)
        assert dep.POSTBOOT_STOPPED(q['snapshot']) and q['snapshot']['2622']==dep.EXPECTED
        actual=d.config(c)
        q['configuration_mismatches']={a:[v,actual[a]] for a,v in board['original'].items()
            if int(a) not in (1875,1923) and actual[a]!=v}
        assert not q['configuration_mismatches']
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
            row=dict(at=d.now(),pending=pending,save_state=t.read8(sy['IndoorParameterSaveState']),
                error=t.read16(sy['CPURomWriteError']))
            q['save_samples'].append(row);save();assert row['error']==0
            if not pending and row['save_state']==0:break
            assert time.monotonic()-began<150,row
            if time.monotonic()-notice>20:
                print('WAIT restore save cache',pending,flush=True);notice=time.monotonic()
            time.sleep(.5)
        q['final_feedback']={str(a):c.read_holding_registers(1,a,1)[0] for a in (605,710,819,861,912,913,956,958)}
        assert not any(q['final_feedback'].values())
        # The polling helper holds a match0.3s before returning. Derive edge
        # times from the preserved FIRST rising-edge sample, not that hold end.
        timings=[]
        for timing in board.get('timings',[]):
            r=dict(timing)
            if 'overload' in r['test']:
                fault=956 if r['test'].startswith('X11') else 958
                edge=next(e for e in board['events'] if e['t']>=r['input_write_t'] and e['edges'].get(str(fault))==1)
                r.update(first_confirmed_t=edge['t'],observed_delay_s=edge['t']-r['input_write_t'],
                    timing_basis='first fault rising-edge sample, excluding polling hold')
            timings.append(r)
        q.update(passed=True,restored=True,finished=d.now(),checks=len(board['checks']),timings=timings)
        save()
    lines=['# X11/X12/X14/X15正式档板测\n',
        '330 V10.76，316 V12.56；仅正常Modbus配置、极性、启停和故障复位；SWD只读。未修改、烧录固件。\n',
        '规格3.11.3风机过载持续3秒报警停机；3.11.7风机启动60秒后检测，压差异常持续10秒报警停机。X11/X12沿用当前配置与风机输出门限，X14/X15沿用386选项。\n',
        '| 测试 | 实测确认时间（秒） |\n| --- | --- |\n']
    for r in q['timings']:
        lines.append(f"| {r['test']} | {r['observed_delay_s']:.3f} |\n")
    lines.extend(['\n时间从极性写入开始到首次观测对应状态，包含通讯/采样间隔，非物理接点精确时刻。原始样本read_ended保留整组读回时间边界。\n',
        '\nX11排风过载DO、X12回风过载DO/AO：短脉冲、持续滤波、对应故障、605/Y05、全部风机停机、故障输入未解除不能清锁存、恢复后锁存保留及复位清除。\n',
        '\nX15送风压差DO、X14回风压差AO：未满60秒缺压不报、启动许可不足10秒不放行、中断重计、连续10秒许可后运行、真实等待60秒门限、7秒短时缺压不报及恢复清计时、再次连续10秒缺压独立报警/Y05和停机、恢复后锁存及复位。\n',
        f"\n功能检查{len(board['checks'])}项通过。最终全参数对比无差异，三板镜像核对一致，正式档标记/启停下限保持，保存缓存恢复，EEPROM错误标志0。最终956/958/913/912/605/710/861/Y05均0。\n",
        '\n限制：通过极性翻转模拟输入，未开合实体接点，未测端子/继电器触点。通风模式验证，外机压机全程停机；不能将本次结果描述为压机带载停机或真实压差传感器验收。两种物理接点方向仍属现场验证项。\n'])
    (day/'测试结果.md').write_text(''.join(lines),'utf8')
    print('FINAL FAN DI AUDIT PASS',len(board['checks']),'checks,all parameters and save cache restored',flush=True)


if __name__=='__main__':main()
