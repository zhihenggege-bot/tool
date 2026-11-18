"""Independent stopped-state configuration and persistence shadow audit."""
import argparse, json, struct, time, traceback
from run_indoor_bench_20261105 import D, BOARDS, EXPECTED, client, snap, loads_off, axf_symbols, dump, now, ConnectHelper, result

# These persistent values advance during genuine operation. They are not test
# configuration, must not be reset to the preflight value, and are reported.
RUNTIME_COUNTER_REGISTERS = {167, 373}


def main(reset=False):
    c = client()
    p = D / ('independent_audit_' + time.strftime('%H%M%S') + '.json')
    report = {'at': now(), 'kind': 'SWD RAM reads; optional explicit ST-Link reset; no RAM/Flash data writes', 'reset_requested':reset}
    try:
        report['initial_version_settle']=[]
        end=time.monotonic()+30
        while True:
            report['versions']=c.read_holding_registers(1,2622,18)
            report['initial_version_settle'].append({'at':now(),'versions':report['versions']})
            if report['versions']==EXPECTED:break
            assert time.monotonic()<end,report['versions']
            time.sleep(.5)
        report['snapshot'] = snap(c)
        config = {}
        for a, n in [(0, 125), (125, 125), (250, 125), (375, 125), (1229, 60), (1298, 2)]:
            config.update({str(a+i): v for i, v in enumerate(c.read_holding_registers(1, a, n))})
        report['config'] = config
        original = json.loads((D / 'preflight.json').read_text('utf-8'))['config']
        report['runtime_counter_changes'] = {a:[v,config[a]] for a,v in original.items()
             if int(a) in RUNTIME_COUNTER_REGISTERS and config[a]!=v}
        report['differences_from_preflight'] = {a: [v, config[a]] for a, v in original.items()
             if int(a) not in RUNTIME_COUNTER_REGISTERS and config[a] != v}
        sy = axf_symbols()
        report['persistence_symbol_candidates'] = {n: list(v) for n,v in sy.items()
             if any(k in n.lower() for k in ('eeprom', 'parameter', 'save', 'i2c', 'aiCfg'.lower()))}
        with ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1], target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t = ss.target
            a, size = sy['Old_Parameter']
            assert size == 1000
            shadow = list(struct.unpack('<500H', bytes(t.read_memory_block8(a, size))))
            report['old_parameter_shadow'] = shadow
            report['parameter_shadow_mismatches'] = {str(a): [config[str(a)], v] for a,v in enumerate(shadow) if config[str(a)] != v}
            a, size = sy['IndoorAiCfgShadow']
            ai = list(struct.unpack('<60H', bytes(t.read_memory_block8(a,size))))
            report['ai_shadow_mismatches'] = {str(1229+i): [config[str(1229+i)],v] for i,v in enumerate(ai) if config[str(1229+i)] != v}
            report['ai_dirty'] = t.read8(sy['IndoorAiCfgDirty'][0])
            report['writer_state'] = t.read8(sy['EEpflag'][0])
            report['boot_state'] = t.read8(sy['eepromtt'][0])
            if reset:
                assert not report['differences_from_preflight'], report['differences_from_preflight']
                assert not report['parameter_shadow_mismatches'] and not report['ai_shadow_mismatches']
                assert report['snapshot']['state'][9]==0 and loads_off(report['snapshot'])
                report['pre_reset_settle'] = []
                end=time.monotonic()+30
                stable=None
                while True:
                    ps=list(struct.unpack('<500H',bytes(t.read_memory_block8(sy['Old_Parameter'][0],1000))))
                    ai=list(struct.unpack('<60H',bytes(t.read_memory_block8(sy['IndoorAiCfgShadow'][0],120))))
                    good=(ps==[config[str(i)] for i in range(500)] and
                          ai==[config[str(1229+i)] for i in range(60)] and
                          t.read8(sy['EEpflag'][0])==0 and t.read8(sy['IndoorAiCfgDirty'][0])==0)
                    report['pre_reset_settle'].append({'at':now(),'all_ready':good})
                    if good:
                        stable=stable or time.monotonic()
                        if time.monotonic()-stable>=2:break
                    else:stable=None
                    assert time.monotonic()<end, 'save state did not settle'
                    time.sleep(.2)
                dump(p,report)
                t.reset()
                report['post_reset_boot_settle']=[]
                end=time.monotonic()+30
                while True:
                    state={'at':now(),'ai_loaded':t.read8(sy['IndoorAiCfgLoaded'][0]),
                           'eeprom_state':t.read8(sy['eepromtt'][0])}
                    report['post_reset_boot_settle'].append(state)
                    if state['ai_loaded']==1 and state['eeprom_state']==3:break
                    assert time.monotonic()<end,state
                    time.sleep(.25)
        if reset:
            report['post_reset_version_settle']=[]
            end=time.monotonic()+30
            while True:
                versions=c.read_holding_registers(1,2622,18)
                report['post_reset_version_settle'].append({'at':now(),'versions':versions})
                if versions==EXPECTED:break
                assert time.monotonic()<end,versions
                time.sleep(.5)
            loaded={}
            for a,n in [(0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)]:
                loaded.update({str(a+i):v for i,v in enumerate(c.read_holding_registers(1,a,n))})
            report['after_reset_config']=loaded
            report['after_reset_runtime_counter_changes']={a:[v,loaded[a]] for a,v in original.items()
                 if int(a) in RUNTIME_COUNTER_REGISTERS and loaded[a]!=v}
            report['after_reset_differences_from_preflight']={a:[v,loaded[a]] for a,v in original.items()
                 if int(a) not in RUNTIME_COUNTER_REGISTERS and loaded[a]!=v}
            report['post_reset_observations']=[]
            start=time.monotonic()
            while time.monotonic()-start<30:
                s=snap(c)
                report['post_reset_observations'].append(s)
                assert s['state'][9]==0 and loads_off(s) and not any(s['faults']), s
                assert c.read_holding_registers(1,2622,18)==EXPECTED
                time.sleep(.4)
            report['post_reset_health_duration_s']=time.monotonic()-start
            assert not report['after_reset_differences_from_preflight'], report['after_reset_differences_from_preflight']
        dump(p, report)
        print('AUDIT', p.name, flush=True)
        for key in ('differences_from_preflight','parameter_shadow_mismatches','ai_shadow_mismatches','ai_dirty'):
            print(key, report[key], flush=True)
        print('PERSISTENCE SYMBOLS', report['persistence_symbol_candidates'], flush=True)
        if reset:
            result('T17-001','通过','本批330配置参数0~499（运行累计167/373除外）、新AI配置1229~1288及档位1298/1299与烧前快照一致；保存稳定后ST-Link复位再次一致，累计增量单独保留',p,
                   '板上保留用户指定BENCH；此项是参数及校准恢复，不表示固件所有功能通过；167/373真实运行累计未回写或清零')
            result('T17-003','部分通过',f"独立终检：复位后{report['post_reset_health_duration_s']:.1f}s三板版本/通信正常，无内机软件故障、负载DO/AO全0；Y05报警接点单独记录",p,
                   '端子带电/接点独立测量未做；正式版未切换；实际EEPROM掉电完整性另测；台架外机压力探头故障可保持Y05，不计为负载输出')
    except BaseException:
        report['audit_error']=traceback.format_exc()
        dump(p,report)
        raise
    finally:
        c.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reset',action='store_true')
    main(parser.parse_args().reset)
