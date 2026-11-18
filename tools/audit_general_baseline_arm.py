"""Reproduce baseline-audit findings in existing Keil AXFs, offline only.

Run: py -3 -X utf8 tools/audit_general_baseline_arm.py
Requires the Unicorn/ELF dependencies used by test_defrost_lifecycle_arm.py.
These are defect reproductions, not a release acceptance suite. Exit 0 means
the documented observations reproduced; it does not mean the firmware passed.
No serial port, ST-Link, board memory or EEPROM is accessed.
"""
import hashlib
import json
from pathlib import Path

from test_defrost_lifecycle_arm import Firmware, IN, OUT, ROOT
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR


def suppress_tx(f):
    def return_to_caller(uc, address, size, user):
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    addr = f.symbols['StartUart6SendData'][0] & ~1
    f.uc.hook_add(UC_HOOK_CODE, return_to_caller, begin=addr, end=addr)


def parameters(f, values):
    for index, value in values.items():
        f.p(index, value)


def main():
    observations = {}
    f = Firmware(IN)
    base, size = f.symbols['Parameter']
    writes = []

    def track_write(uc, access, address, width, value, user):
        if base + size <= address < base + size + 16:
            writes.append((address - base) // 2)

    f.uc.hook_add(UC_HOOK_MEM_WRITE, track_write)
    f.uc.mem_write(base + size, bytes([0xA5]) * 16)
    f.call('PSC316Gateway_PublishToHMI')
    assert writes == [2888, 2889, 2890, 2891]
    observations['330_fan_runtime_mirror_oob'] = {
        'indices': writes, 'parameter_words': size // 2,
        'overwritten_symbol': 'Parameter1',
        'address': hex(base + size),
    }

    allowed = [f.call('ParamCanWriteFromHMI', i, 1) for i in (1229, 1230)]
    assert allowed == [0, 0]
    observations['330_valid_ai_writes_rejected'] = allowed

    f = Firmware(IN)
    suppress_tx(f)
    buf = f.symbols['ucUart6Buff'][0]
    f.uc.mem_write(buf, bytes([1, 6, 3, 32, 0x12, 0x34, 0, 0]))
    denied_on_hmi = f.call('ParamCanWriteFromHMI', 800, 0x1234) == 0
    f.call('ModbusUart6Fun6')
    assert denied_on_hmi and f.p(800) == 0x1234
    observations['330_uart6_status_write_bypasses_hmi_policy'] = f.p(800)

    reads = []
    base, size = f.symbols['Parameter']

    def track_read(uc, access, address, width, value, user):
        if address == base + size:
            reads.append(address)

    f.uc.hook_add(UC_HOOK_MEM_READ, track_read)
    f.uc.mem_write(buf, bytes([1, 3, 0x0B, 0x48, 0, 1, 0, 0]))
    f.call('ModbusUart6Fun3')
    assert reads
    observations['330_uart6_reads_index_equal_to_size'] = 2888

    f = Firmware(OUT)
    parameters(f, {10: 500, 12: 500, 80: 0, 800: 1, 805: 300, 809: 300})
    f.var('output', 1, index=1, width=1)
    for tick in (0, 1, 0, 1):
        f.var('uc1s', tick)
        f.call('EEV_Action', 0)
    assert f.p(805) == 280 and f.var('output', index=1, width=1) == 1
    observations['316_shared_eev_closes_with_healthy_compressor_running'] = {
        'initial_steps': 300, 'target_steps': f.p(805), 'healthy_comp2_output': 1,
    }

    f = Firmware(IN)
    parameters(f, {709: 2, 236: 1, 128: 1, 332: 1, 127: 1, 129: 1,
                   214: 2, 250: 1, 251: 1, 512: -10, 346: 300,
                   738: 250, 739: 250, 120: 20})
    assert f.call('IndoorHeatPumpFullLoad') == 0
    f.call('HeatControl_UP')
    assert f.p(890) == 300 and f.var('DA', index=0, width=2) == 300
    observations['330_winter_minimum_overrides_aux_full_load_gate'] = 300

    f = Firmware(IN)
    parameters(f, {709: 2, 236: 1, 128: 2, 512: 100, 738: 230,
                   739: 250, 120: 20})
    f.call('HeatControl_UP')
    assert f.p(890) == 1000
    observations['330_23C_forces_full_heat_with_WD25_WDF2'] = 1000

    f = Firmware(IN)
    parameters(f, {700: 4, 709: 2, 236: 0, 320: 1, 315: 0, 321: 50, 322: 60,
                   127: 1, 332: 1, 890: 600, 738: 250, 739: 250, 120: 20})
    f.call('IndoorModeTransitionAction')
    f.var('uc1s', 1)
    for _ in range(60):
        f.call('IndoorAutoCoolHeatSwitchAction')
        # Match UserAction's actual call order: the transition handler consumes
        # the auto-switch request in the same scan, before load control runs.
        f.call('IndoorModeTransitionAction')
    assert f.p(236) == 0 and f.p(709) == 3
    assert f.var('IndoorPendingWorkMode') == 1
    observations['330_auto_switch_queues_normal_shutdown'] = {
        'mode': f.p(236), 'sys_step': f.p(709),
        'pending_mode': f.var('IndoorPendingWorkMode'),
        'scope': 'paired handlers in actual scan order; physical outputs not measured',
    }

    fan_cut = []
    for unit_type, fan_type in ((1, 3), (1, 2), (2, 2), (2, 4)):
        f = Firmware(OUT)
        parameters(f, {165: unit_type, 166: fan_type, 107: 1})
        f.var('output', 1, index=0, width=1)
        f.var('Comp', 1, index=0, width=1)
        f.call('OutdoorProtectOutputLimit')
        assert f.var('Comp', index=0, width=1) == 1
        assert f.var('output', index=0, width=1) == 0
        fan_cut.append({'unit_type': unit_type, 'fan_type': fan_type,
                        'comp_request': 1, 'final_comp_output': 0})
    observations['316_running_compressor_cut_when_fan_regulation_stops_fans'] = fan_cut

    f = Firmware(OUT)
    f.var('BoardAddressSet', 1)
    parameters(f, {1400: 1, 45: 15})
    f.var('FanRunTime', 16, index=0, width=4)
    f.var('CompStopTime', 120, index=0, width=4)
    f.var('output', 1, index=2, width=1)
    f.call('ModuleCompAction')
    assert f.var('Comp', index=0, width=1) == 1
    observations['316_start_gate_has_no_actual_fan_elapsed_check'] = {
        'request_timer_seconds': 16, 'fan_on_elapsed_in_emulation_ms': 0,
        'compressor_request': 1,
        'scope': 'isolated gate; occurrence in a whole machine requires integration validation',
    }

    result = {
        'method': 'offline execution of existing ARM machine code with injected RAM/IO',
        'firmware_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                            for p in (IN, OUT)},
        'observation_count': len(observations), 'observations': observations,
    }
    target = ROOT / '.codex-tmp/v1017_comparison/arm_audit_result.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
