"""Final baseline-audit observations against existing ARM builds; no hardware.

Exit 0 means observations reproduced, including a stale calibration-page write.
It is not whole-machine acceptance. See the baseline comparison report.
"""
import hashlib
import json

from test_defrost_lifecycle_arm import Firmware, IN, OUT, ROOT, indoor
from audit_gateway_readback_arm import rtu_frame
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_PC, UC_ARM_REG_LR,
                              UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)


def observe_runtime_restore(version, corrupt_crc=False):
    f = Firmware(OUT)
    values = [7, 111, 222]
    if version >= 2:
        values.append(333)
    if version >= 3:
        values.extend((444, 555))
    body = (0xC300 + version).to_bytes(2, 'big') + b''.join(
        value.to_bytes(4, 'big') for value in values)
    f.uc.mem_write(0x20060000, body)
    crc = f.call('CompressorRuntimeCRC16', 0x20060000, len(body))
    record = body + (crc ^ int(corrupt_crc)).to_bytes(2, 'big')
    eeprom = bytearray([255] * 4096)
    eeprom[1024:1024 + len(record)] = record

    def read_eeprom(uc, address, size, user_data):
        destination = uc.reg_read(UC_ARM_REG_R0)
        count = uc.reg_read(UC_ARM_REG_R1)
        source = uc.reg_read(UC_ARM_REG_R2)
        assert 0 <= source < len(eeprom) and count <= 28
        uc.mem_write(destination, bytes(eeprom[source:source + count]))
        uc.reg_write(UC_ARM_REG_R0, 1)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    address = f.symbols['CI2C_ReadByte'][0] & ~1
    f.uc.hook_add(UC_HOOK_CODE, read_eeprom, begin=address, end=address)
    f.call('CompressorRuntimeInit')
    result = {
        'record_format': version, 'corrupt_crc': corrupt_crc,
        'compressor_seconds': [f.var('CompTotalRunSeconds', index=i, width=4) for i in range(2)],
        'outdoor_seconds': f.var('OutdoorTotalRunSeconds'),
        'fan_seconds': [f.var('OutdoorFanTotalRun', index=i, width=4) for i in range(2)],
        'save_requested': f.var('RuntimeSaveRequested'),
        'scope': 'ARM record selection/decoding with simulated EEPROM reads; no writes or power cuts',
    }
    if corrupt_crc:
        assert result['compressor_seconds'] == [0, 0]
        assert result['outdoor_seconds'] == 0 and result['save_requested'] == 1
    else:
        assert result['compressor_seconds'] == [111, 222]
        assert result['outdoor_seconds'] == (333 if version == 3 else 0)
        assert result['fan_seconds'] == ([444, 555] if version == 3 else [0, 0])
        assert result['save_requested'] == int(version != 3)
    return result


def main():
    observations = {}
    for label, path in (('330', IN), ('316', OUT)):
        f = Firmware(path)
        f.uc.mem_map(0x22000000, 0x100000)
        f.call('ParameterInit')
        invalid = []
        for index in range(500):
            values = [f.var(name, index=index, width=2) for name in
                      ('Parameter_min', 'Parameter_def', 'Parameter_max')]
            minimum, default, maximum = [value - 65536 if value >= 32768 else value
                                         for value in values]
            if not minimum <= default <= maximum:
                invalid.append([index, minimum, default, maximum])
        assert not invalid
        observations[label + '_initialized_defaults_fit_saved_parameter_ranges'] = {
            'parameter_count': 500, 'out_of_range_defaults': invalid,
            'scope': 'internal min/default/max consistency; not specification correctness',
        }

    f = indoor()
    f.uc.mem_map(0x22000000, 0x100000)
    f.p(214, 2)
    f.p(540, 1)  # Selected legacy outdoor page.
    f.var('Systick_1ms', 36000)
    f.var('UnitCommErr', 1, 1, 2)  # Previously offline; page keeps loading its old cache.
    for unit in range(4):
        f.var('PSC316VersionRequestPending', 0, unit, 1)
    f.call('W5070Disp')  # Loads the initial zero cache into the selected page.
    assert f.p(746) == 0 and f.var('ReadBackFlag', index=1, width=2) == 0
    sent = []

    def intercept(uc, address, size, user_data):
        if address == (f.symbols['StartUart5SendData'][0] & ~1):
            sent.append(bytes(uc.mem_read(f.symbols['ucUart5Buff'][0], f.var('ucUart5SendLen'))))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for name in ('StartUart5SendData', 'UART5Init'):
        address = f.symbols[name][0] & ~1
        f.uc.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address)

    f.call('PSC316Gateway_BuildReadFrame', 1, 1460, 42)
    words = [0] * 42
    words[25] = 50  # [1485] legacy readback -> TempCheck[6], +5.0C calibration.
    response = rtu_frame(bytes((1, 3, 84)) +
                         b''.join(word.to_bytes(2, 'big') for word in words))
    f.uc.mem_write(f.symbols['ucUart5Buff'][0], response)
    f.var('ucUart5ReceLen', len(response))
    f.call('ModuleReciData')
    f.var('Systick_1ms', 36010)
    f.call('ModuleReciData')
    received = f.field(True, 1, 'TempCheck', 6)
    assert received == 50 and f.var('ReadBackFlag', index=1, width=2) == 1
    # Match SystemAction's communication-before-User/DispAction order: the
    # send scheduler sees the fresh response timestamp and clears comm fault.
    f.call('ModuleSendData')
    assert f.var('UnitCommErr', index=1, width=2) == 0
    f.call('W5070Disp')
    overwritten = f.field(True, 1, 'TempCheck', 6)
    assert overwritten == 0 and f.p(746) == 0
    calibration_write = None
    # Let the normal maintenance schedule reach its calibration-write step.
    for step in range(1, 61):
        f.var('Systick_1ms', 36010 + step * 10)
        count_before = len(sent)
        f.call('ModuleSendData')
        if len(sent) == count_before:
            continue
        frame = sent[-1]
        if (len(frame) == 37 and frame[:2] == bytes((1, 16))
                and int.from_bytes(frame[2:4], 'big') == 1580
                and int.from_bytes(frame[4:6], 'big') == 14):
            calibration_write = frame
            break
    assert calibration_write is not None
    assert int.from_bytes(calibration_write[19:21], 'big') == 0
    observations['late_calibration_readback_overwritten_by_page_then_queued_for_write'] = {
        'readback_received': received, 'cache_after_page_refresh': overwritten,
        'page_value': f.p(746), 'readback_flag': f.var('ReadBackFlag', index=1, width=2),
        'communication_fault_before_page_refresh': 0,
        'read_response_hex': response.hex(),
        'outbound_calibration_write_hex': calibration_write.hex(),
        'outbound_register_1586': 0,
        'scope': 'CRC-checked receive/page/scheduler chain; outbound frame intercepted',
    }

    f = indoor()
    f.uc.mem_map(0x22000000, 0x100000)
    f.p(214, 2)
    f.p(540, 1)
    f.var('Systick_1ms', 36000)
    f.field(True, 1, 'TempCheck', 6, 50)
    f.var('ReadBackFlag', 1, 1, 2)
    f.call('W5070Disp')
    f.call('W5070Disp')
    assert f.p(746) == f.field(True, 1, 'TempCheck', 6) == 50
    observations['calibration_known_before_page_load_is_preserved'] = {
        'page_value': 50, 'cache_value': 50,
        'scope': 'page load and refresh only; normal comparison condition',
    }

    for version in (1, 2, 3):
        observations[f'outdoor_runtime_V{version}_restore'] = observe_runtime_restore(version)
    observations['outdoor_runtime_bad_V3_crc_is_rejected'] = observe_runtime_restore(3, True)

    f = Firmware(OUT)
    length = f.symbols['R410ATemp'][1] // 2
    values = [f.var('R410ATemp', index=i, width=2) for i in range(length)]
    values = [value - 65536 if value >= 32768 else value for value in values]
    # Entries 0..19 are deliberate placeholders; active pressure data start at20.
    descending = [[i, values[i], values[i + 1]] for i in range(20, length - 1)
                  if values[i + 1] < values[i]]
    assert descending == [[382, 307, 306]]
    observations['R410A_active_table_contains_one_descending_pair'] = {
        'active_start_index': 20, 'total_entries': length,
        'descending_pairs': descending,
        'scope': 'compiled lookup data only; pressure sensor accuracy not modeled',
    }

    result = {
        'method': 'offline existing ARM execution with RAM inputs and intercepted UART boundaries',
        'firmware_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                            for path in (IN, OUT)},
        'observation_count': len(observations), 'observations': observations,
    }
    target = ROOT / '.codex-tmp/v1017_comparison/baseline_closure_arm_result.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
