"""Observe outdoor disable behavior in existing ARM builds, without hardware.

Exit 0 confirms the observations below, including defects; it is not acceptance.
Requires the same offline dependencies as test_defrost_lifecycle_arm.py.
"""
import hashlib
import json

from test_defrost_lifecycle_arm import Firmware, IN, OUT, ROOT, indoor, outdoor
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR


def observe_busy_writes(second_address, second_value, duplicate=False):
    """Execute the HMI FC06 handler, intercepting its serial-send boundary.

    Valid RTU request bytes are supplied, but reception, CRC dispatch and UART
    timing are outside this observation. The active write is deliberately left
    pending to model a second request arriving before downstream confirmation.
    """
    f = indoor()
    replies = []

    def intercept_send(uc, address, size, user_data):
        replies.append(bytes(uc.mem_read(f.symbols['ucUart1Buff'][0], 8)))
        assert f.var('ucUart1SendLen') == 8
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    send_address = f.symbols['StartUart1SendData'][0] & ~1
    f.uc.hook_add(UC_HOOK_CODE, intercept_send, begin=send_address, end=send_address)
    first_job = None
    for address, value in ((1832, 1), (second_address, second_value)):
        payload = bytes((1, 6, address >> 8, address & 255, value >> 8, value & 255))
        crc = 0xFFFF
        for byte in payload:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
        frame = payload + crc.to_bytes(2, 'little')
        f.uc.mem_write(f.symbols['ucUart1Buff'][0], frame)
        f.call('ModbusUart1Fun6')
        assert replies[-1] == frame
        job = bytes(f.uc.mem_read(*f.symbols['PSC316WriteJob']))
        if first_job is None:
            first_job = job
        else:
            assert job == first_job
    assert len(replies) == 2
    # PSC316_WRITE_JOB_STRU: active/phase/unit/retry, uint16 count/addr, int16 value[].
    assert first_job[0] == first_job[2] == 1
    assert int.from_bytes(first_job[6:8], 'little') == 167
    assert int.from_bytes(first_job[8:10], 'little') == 1
    unit_index = (second_address - 1830) // 48
    state = f.var('PSC316WriteState', index=unit_index, width=1)
    error = f.var('PSC316WriteError', index=unit_index, width=1)
    assert (state, error) == ((1, 0) if duplicate else (3, 3))
    return {
        'requests': [[1832, 1], [second_address, second_value]],
        'normal_FC06_replies_at_send_boundary': [reply.hex() for reply in replies],
        'active_job_unchanged': True,
        'active_job': {'unit': 1, 'parameter': 167, 'value': 1},
        'second_unit_diagnostics': {'state': state, 'error': error},
        'scope': 'FC06 handler and queue only; no UART timing or downstream execution',
    }


def main():
    observations = {}
    f = indoor()
    before = f.call('IndoorMaxCompNum')
    f.p(1832, 1)
    after = f.call('IndoorMaxCompNum')
    assert before == after == 8
    assert f.call('CompIsConfigured', 1, 0) == 0
    assert f.call('CompIsConfigured', 1, 1) == 0
    observations['disabled_unit_excluded_from_candidates_but_not_CN'] = {
        'CN_before': before, 'CN_after': after, 'unit1_candidates': 0,
        'scope': 'installed CN and dispatch availability are different quantities',
    }

    for c in range(2):
        f.field(True, 1, 'CompControl', c, 1)
        f.field(False, 1, 'CompStatus', c, 3)
    f.call('DeviceStatusCount')
    commands = [f.field(True, 1, 'CompControl', c) for c in range(2)]
    assert commands == [0, 0]
    observations['disabled_unit_both_requests_cleared_in_one_handler'] = commands

    modes = []
    for manual in (0, 1):
        f = Firmware(OUT)
        f.p(167, 1)
        f.p(197, 1)
        f.p(107, 1)
        f.p(1300, manual)
        f.p(1302, manual)
        f.p(1303, manual)
        for c in range(2):
            f.var('output', 1, c, 1)
            f.var('Comp', 1, c, 1)
        f.call('OutdoorUnitAction')
        f.call('HandDebugY02Ctrl')
        f.call('OutdoorProtectOutputLimit')
        outputs = [f.var('output', index=c, width=1) for c in range(2)]
        assert outputs == [manual, manual]
        modes.append({'manual': manual, 'compressor_outputs': outputs})
    observations['final_disable_limit_bypassed_in_manual_mode'] = modes

    f = outdoor()
    f.p(197, 1)
    f.p(167, 1)
    f.p(107, 1)
    f.call('OutdoorUnitAction')
    f.call('OutdoorProtectOutputLimit')
    assert f.var('output', index=0, width=1) == 0
    assert f.var('output', index=1, width=1) == 0
    f.var('uc1s', 1)
    for second in range(1, 361):
        f.var('Systick_1ms', second * 1000)
        # Same relative order as UserAction and User's final output boundary.
        # No sensor acquisition or fault injection is performed here.
        f.call('DefrostProcess')
        f.call('OutdoorUnitAction')
        f.call('OutdoorProtectOutputLimit')
    runtime = [f.var('PSC316DefrostRunTime', index=c, width=4) for c in range(2)]
    assert f.p(1420) == f.p(1421) == 8 and runtime == [0, 0]
    assert f.var('PSC316DefrostState') == 1
    observations['disable_during_defrost_keeps_active_lifecycle_with_outputs_off'] = {
        'elapsed_seconds': 360, 'configured_defrost_seconds': 240,
        'compressor_outputs': [f.var('output', index=c, width=1) for c in range(2)],
        'runtime_seconds': runtime, 'published_states': [f.p(1420), f.p(1421)],
        'scope': 'paired defrost/disable/output handlers, no full sensor or fault model',
    }

    f = indoor()
    for c in range(2):
        f.field(False, 1, 'CanDefrost', c, 8)
    f.p(1832, 1)
    assert f.call('IndoorDefrostActive') == 1
    assert f.call('IndoorOutdoorStopped') == 0
    f.field(False, 2, 'CanDefrost', value=1)
    f.var('PSC316DefrostOwner', 1)
    f.call('PSC316UpdateDefrostOwner')
    assert f.var('PSC316DefrostOwner') == 1
    observations['indoor_waits_for_disabled_unit_active_lifecycle'] = {
        'defrost_active': 1, 'outdoor_stopped': 0,
        'defrost_owner_with_unit2_request': f.var('PSC316DefrostOwner'),
    }

    f = Firmware(OUT)
    for address, value in {10: 500, 12: 500, 167: 1, 155: 250, 156: 1}.items():
        f.p(address, value)
    for _ in range(25):
        f.var('uc1s', 0)
        f.call('EEV_Action', 0)
        f.var('uc1s', 1)
        f.call('EEV_Action', 0)
    assert f.p(805) == 250 and f.p(156) == 1
    observations['outdoor_disable_does_not_override_manual_eev_target'] = {
        'manual_enable': f.p(156), 'target_steps': f.p(805),
        'scope': 'EEV handler target only; physical valve movement not modeled',
    }

    f = outdoor()
    f.p(107, 1)
    f.var('AmbientLockout', 0)
    # [169] is the saved setting. [153] is its effective disable value after
    # System_Real combines that setting with the indoor disable command.
    # Inject both here to avoid emulating unrelated ADC acquisition.
    f.p(169, 1)
    f.p(153, 1)
    f.var('uc1s', 1)
    for second in range(1, 361):
        f.var('Systick_1ms', second * 1000)
        for c in range(2):
            f.var('output', f.var('Comp', index=c, width=1), c, 1)
        f.call('DefrostProcess')
        f.call('OutdoorProtectOutputLimit')
    runtimes = [f.var('PSC316DefrostRunTime', index=c, width=4) for c in range(2)]
    ended = [f.var('PSC316DefrostEnded', index=c, width=1) for c in range(2)]
    assert runtimes == [240, 1] and ended == [1, 0]
    assert f.p(1420) == f.p(1421) == 8
    observations['disable_one_compressor_during_defrost_blocks_group_completion'] = {
        'elapsed_seconds': 360, 'configured_defrost_seconds': 240,
        'runtime_seconds': runtimes, 'ended': ended,
        'published_states': [f.p(1420), f.p(1421)],
        'scope': 'effective single-compressor disable injected; sensors not modeled',
    }

    f = indoor()
    for unit in range(1, 5):
        for c in range(2):
            f.field(False, unit, 'CompStatus', c, 3)
    f.field(False, 1, 'CompStatus', 0, 1)
    fault_result = f.call('IndoorHeatPumpFullLoad')
    f.p(1833, 1)
    disabled_result = f.call('IndoorHeatPumpFullLoad')
    for address in (1832, 1880, 1928, 1976):
        f.p(address, 1)
    all_disabled_result = f.call('IndoorHeatPumpFullLoad')
    assert (fault_result, disabled_result, all_disabled_result) == (0, 1, 0)
    observations['auxiliary_full_load_filters_disable_but_not_faulted_compressor'] = {
        'one_fault_all_other_compressors_heating': fault_result,
        'same_fault_then_explicitly_disabled': disabled_result,
        'all_outdoor_units_disabled': all_disabled_result,
        'scope': 'full-load predicate only; does not claim a measured auxiliary output',
    }

    f = indoor()
    f.var('PSC316StatusValid', 1, index=0, width=1)
    f.var('CompMinStopCount', 1000, index=2, width=4)
    f.call('PSC316Gateway_PublishToHMI')
    assert f.var('PSC316SetValid', index=0, width=1) == 0
    assert f.p(1832) == 0 and f.p(1872) == 1
    assert f.call('CompCanLoad', 1, 0) == 1
    observations['load_gate_accepts_unknown_settings_mirror_as_not_disabled'] = {
        'settings_valid': 0, 'disable_mirror': 0, 'online_indicator': 1,
        'load_gate': 1,
        'scope': 'status-valid/settings-unread gate condition, not a measured start',
    }

    f = Firmware(OUT)
    for address, value in {167: 1, 197: 1, 107: 1, 30: 5}.items():
        f.p(address, value)
    f.call('OutdoorUnitAction')
    f.call('UnderHeartCtrl')
    f.call('OutdoorProtectOutputLimit')
    assert f.var('output', index=6, width=1) == 1
    assert f.var('output', index=0, width=1) == 0
    observations['disable_preserves_crankcase_heater_control'] = {
        'crankcase_Y06': 1, 'compressor1': 0,
        'scope': 'initial preheat condition; disable is not emergency power removal',
    }

    f = Firmware(OUT)
    for address, value in {167: 1, 107: 1, 621: 1}.items():
        f.p(address, value)
    f.call('ErrorProcess')
    assert f.var('UnitLevelFault') == 1 and f.p(1501) & 0x10
    f = indoor()
    f.p(1832, 1)
    f.var('UnitCommErr', 1, index=1, width=2)
    f.var('X_02', 1)
    f.call('BoardErrAction')
    assert f.p(710) == 0
    observations['disabled_unit_fault_diagnostics_remain_but_indoor_comm_fault_is_isolated'] = {
        'outdoor_disabled_fan_fault_unit_bit': 1,
        'indoor_system_fault_for_injected_unit1_comm_loss': 0,
        'scope': 'separate fault handlers, unrelated fault inputs cleared',
    }

    observations['busy_write_other_unit_is_not_queued_but_normally_acknowledged'] = (
        observe_busy_writes(1880, 1))
    observations['busy_reverse_write_same_unit_is_not_queued_but_normally_acknowledged'] = (
        observe_busy_writes(1832, 0))
    observations['duplicate_pending_write_is_correctly_coalesced'] = (
        observe_busy_writes(1832, 1, duplicate=True))

    f = outdoor()
    f.p(107, 1)
    f.var('X_00', 1)
    f.var('X_02', 1)
    f.call('DefrostProcess')
    assert f.var('PSC316DefrostState') == 2 and f.p(1420) == 7
    f.p(167, 1)
    f.var('uc1s', 1)
    recovery_states = {}
    for second in range(1, 61):
        f.var('Systick_1ms', second * 1000)
        f.call('DefrostProcess')
        f.call('OutdoorUnitAction')
        f.call('OutdoorProtectOutputLimit')
        if second in (59, 60):
            recovery_states[second] = [f.p(1420), f.p(1421)]
        assert [f.var('output', index=c, width=1) for c in range(2)] == [0, 0]
    assert recovery_states == {59: [7, 7], 60: [0, 0]}
    observations['disable_after_entering_recovery_preserves_60_second_completion'] = {
        'published_states_by_elapsed_second': recovery_states,
        'compressor_outputs_during_recovery': [0, 0],
        'scope': 'already-entered recovery with repeated disable/output handlers; normal control',
    }

    result = {
        'method': 'offline ARM execution with RAM inputs; no board access',
        'firmware_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                            for p in (IN, OUT)},
        'observation_count': len(observations), 'observations': observations,
    }
    target = ROOT / '.codex-tmp/v1017_comparison/outdoor_enable_arm_result.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
