"""Observe gateway readback attribution in the existing 330 ARM build.

No hardware access. Exit 0 means observations (including defects) reproduced;
it does not mean the firmware passed acceptance. UART sends are intercepted,
while scheduling, request construction, receive gap and CRC parsing execute.
"""
import hashlib
import json

from test_defrost_lifecycle_arm import IN, ROOT, indoor
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR


def rtu_frame(payload):
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return payload + crc.to_bytes(2, 'little')


class PendingEnable:
    def __init__(self):
        self.f = f = indoor()
        f.p(214, 2)  # One outdoor unit plus the indoor board.
        for index in range(4):
            f.var('PSC316VersionRequestPending', 0, index, 1)
        f.var('ReadBackFlag', 1, 1, 2)
        f.var('PSC316SetMirror', 1, 2, 2)  # Previous unit-1 [167] = disabled.
        self.sent = []
        self.ticks = 0

        def intercept(uc, address, size, user_data):
            if address == (f.symbols['StartUart5SendData'][0] & ~1):
                self.sent.append(bytes(uc.mem_read(
                    f.symbols['ucUart5Buff'][0], f.var('ucUart5SendLen'))))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        for name in ('StartUart5SendData', 'UART5Init'):
            address = f.symbols[name][0] & ~1
            f.uc.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address)
        assert f.call('PSC316Gateway_HMIWrite', 1832, 0) == 1

    def advance_to_read(self, address):
        # Do not deliver the enable write or any target readback to a board.
        # No response is injected until the specific requested observation.
        for _ in range(60):
            self.ticks += 100
            self.f.var('Systick_1ms', self.ticks)
            previous_count = len(self.sent)
            self.f.call('ModuleSendData')
            if len(self.sent) == previous_count:
                continue
            frame = self.sent[-1]
            if (len(frame) == 8 and frame[:2] == bytes((1, 3))
                    and int.from_bytes(frame[2:4], 'big') == address
                    and int.from_bytes(frame[4:6], 'big') == 1):
                assert self.f.var('PSC316WriteJob', width=1) == 1
                assert self.f.read(self.f.symbols['PSC316WriteJob'][0] + 1, 1) == 3
                # Stay inside the production wrapper's 6000ms job timeout.
                assert self.ticks < 6000
                return frame
        raise AssertionError('requested read was not reached')

    def receive_word(self, value, unit=1, valid_crc=True):
        frame = rtu_frame(bytes((unit, 3, 2, value >> 8, value & 255)))
        if not valid_crc:
            frame = frame[:-1] + bytes((frame[-1] ^ 1,))
        f = self.f
        f.uc.mem_write(f.symbols['ucUart5Buff'][0], frame)
        f.var('ucUart5ReceLen', len(frame))
        f.call('ModuleReciData')  # Observe the newly changed receive length.
        self.ticks += 10
        f.var('Systick_1ms', self.ticks)
        f.call('ModuleReciData')  # Receive gap met; execute CRC and dispatch.
        return frame

    def result(self):
        f = self.f
        job = bytes(f.uc.mem_read(*f.symbols['PSC316WriteJob']))
        return {
            'job_active': job[0], 'job_phase': job[1], 'job_retry': job[3],
            'job_unit': job[2], 'job_word_count': int.from_bytes(job[4:6], 'little'),
            'job_target_address': int.from_bytes(job[6:8], 'little'),
            'write_state': f.var('PSC316WriteState', index=0, width=1),
            'write_error': f.var('PSC316WriteError', index=0, width=1),
            'disable_mirror': f.var('PSC316SetMirror', index=2, width=2),
            'last_read_address': f.var('PSC316LastReadAddr', index=0, width=2),
            'elapsed_ms': self.ticks,
        }


def main():
    observations = {}
    pending = PendingEnable()
    pending.advance_to_read(38)
    response = pending.receive_word(0)
    result = pending.result()
    assert (result['write_state'], result['write_error'], result['job_active'],
            result['disable_mirror'], result['last_read_address']) == (2, 0, 0, 0, 38)
    assert (result['job_unit'], result['job_word_count'], result['job_target_address']) == (1, 1, 167)
    observations['unrelated_register_38_zero_falsely_confirms_enable_167_zero'] = {
        **result, 'response_hex': response.hex(),
        'target_readback_delivered': False,
        'sent_frames_hex': [frame.hex() for frame in pending.sent],
    }

    pending = PendingEnable()
    pending.advance_to_read(167)
    pending.receive_word(0)
    result = pending.result()
    assert (result['write_state'], result['job_active'], result['disable_mirror']) == (2, 0, 0)
    observations['matching_target_readback_normally_completes'] = result

    pending = PendingEnable()
    pending.advance_to_read(167)
    pending.receive_word(1)
    result = pending.result()
    assert (result['job_active'], result['job_phase'], result['job_retry'],
            result['write_state'], result['disable_mirror']) == (1, 1, 1, 1, 1)
    observations['mismatching_target_readback_normally_retries'] = result

    pending = PendingEnable()
    pending.advance_to_read(38)
    pending.receive_word(1)
    result = pending.result()
    assert (result['job_phase'], result['job_retry'], result['write_state']) == (1, 1, 1)
    observations['unrelated_register_mismatch_also_consumes_a_target_retry'] = result

    pending = PendingEnable()
    pending.advance_to_read(38)
    pending.receive_word(0, unit=2)
    result = pending.result()
    assert (result['job_active'], result['job_phase'], result['job_retry'],
            result['disable_mirror']) == (1, 3, 0, 1)
    observations['different_unit_response_does_not_complete_unit1_job'] = result

    pending = PendingEnable()
    pending.advance_to_read(38)
    pending.receive_word(0, valid_crc=False)
    result = pending.result()
    assert (result['job_active'], result['job_phase'], result['job_retry'],
            result['disable_mirror']) == (1, 3, 0, 1)
    observations['bad_crc_response_does_not_complete_job'] = result

    result = {
        'method': 'existing ARM scheduler and receive parser with intercepted UART boundaries',
        'scope': 'no physical UART timing, outdoor board execution or load outputs',
        'firmware_sha256': {IN: hashlib.sha256((ROOT / IN).read_bytes()).hexdigest()},
        'observation_count': len(observations), 'observations': observations,
    }
    target = ROOT / '.codex-tmp/v1017_comparison/gateway_readback_arm_result.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
