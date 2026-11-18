"""Read-only ARM/UI observations for indoor modes and restart policy.

No firmware changes, serial, probes or real EEPROM access. Observations include
known limitations, so success is not a whole-machine acceptance result.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware, IN, ROOT
from test_indoor_3133_arm import board, ao, out
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC, UC_ARM_REG_LR

D = ROOT / '.codex-tmp/mode_restart_audit_20261104'
observations = {}

def observation(name, data):
    observations[name] = data
    print(name, json.dumps(data, ensure_ascii=False))

def setp(f, values):
    for a, v in values.items():
        f.p(a, v)

def main():
    # All declared heat/preheat output families, with a forced full demand.
    heat = []
    for kind in range(6):
        f = board(1)
        setp(f, {709: 2, 128: kind, 127: 0, 129: 0, 332: 1,
                 738: 100, 739: 250, 512: 50})
        if kind == 1:
            f.field(False, 1, 'CanDefrost', value=8)
        for _ in range(10):
            f.call('HeatControl_UP')
            f.call('IndoorEnforceConfiguredOutputDisable')
        row = {'heat_mode': kind, 'demand': f.p(890), 'DA0': ao(f, 0),
               'DA9': ao(f, 9), 'DO': [out(f, ch) for ch in (0, 1, 2)]}
        expected = {0: (0, 0, [0, 0, 0]), 1: (0, 1000, [0, 0, 0]),
                    2: (1000, 0, [0, 0, 0]), 3: (0, 0, [1, 1, 0]),
                    4: (0, 0, [1, 1, 1]), 5: (1000, 0, [1, 1, 0])}[kind]
        assert (row['DA0'], row['DA9'], row['DO']) == expected, row
        heat.append(row)
    observation('six_heat_modes_and_aux_without_cooling_reheat_ARM', heat)

    # Conflict flags and actual AO ownership; mix invalid output is suppressed
    # but has no dedicated conflict flag.
    cases = [
        ('supply_AO_and_supply_valve_AO', {329: 2, 336: 2}, 0x04),
        ('return_AO_and_return_valve_AO', {330: 2, 337: 2}, 0x02),
        ('return_AO_and_supply_valve_AO', {330: 2, 336: 2}, 0x02),
        ('heatpump_reheat_not_shared', {128: 1, 127: 1, 129: 0, 332: 1}, 0x08),
        ('heatpump_reheat_missing', {128: 1, 127: 1, 129: 1, 332: 0}, 0x08),
        ('two_independent_staged_heaters', {128: 3, 127: 1, 129: 0, 332: 2}, 0x10),
        ('exhaust_AO_without_enthalpy', {338: 2, 335: 2, 377: 2}, 0x20),
        ('mixed_air_without_enthalpy', {381: 1, 335: 2, 377: 2}, 0),
    ]
    rows = []
    for label, values, bit in cases:
        f = board(2)
        setp(f, {128: 0, 127: 0, 129: 0, 335: 0, 336: 0, 337: 0,
                 338: 0, 381: 0, 329: 1, 330: 0, 134: 60, 130: 40, 131: 50})
        setp(f, values)
        f.call('IndoorApplyFanValveState', 1, 1, 1, 1)
        f.call('IndoorEnforceConfiguredOutputDisable')
        row = {'case': label, 'conflict_940': f.p(940),
               'DA4': ao(f, 4), 'DA5': ao(f, 5), 'DA6': ao(f, 6), 'DA7': ao(f, 7)}
        assert (f.p(940) & bit) if bit else f.p(940) == 0, row
        if label == 'mixed_air_without_enthalpy': assert ao(f, 5) == 0
        if label.startswith('supply_'): assert ao(f, 7) == 0
        if label.startswith('return_'): assert ao(f, 4) == 0
        rows.append(row)
    observation('configuration_interlocks_ARM', rows)

    path = ROOT / 'psc330_monitor_tool/psc330_monitor/app.py'
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('mode_audit_monitor', path)
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)
    class Text:
        def __init__(self, text): self.text = text
        def get(self): return self.text
    class Fake:
        _mapped_combo_value_to_int = staticmethod(app.Psc330MonitorApp._mapped_combo_value_to_int)
        def __init__(self):
            self.values = {1299: 0}
            self.mode_config_vars = {}
            for a, field in app.MODE_CONFIG_FIELDS.items():
                if field.mapping:
                    text = next(iter(field.mapping.values()))
                else:
                    text = str(field.minimum if field.minimum is not None else 0)
                self.mode_config_vars[a] = Text(text)
    fake = Fake()
    for a, value in {127: 0, 128: 1, 129: 0, 332: 1}.items():
        fake.mode_config_vars[a] = Text(app.MODE_CONFIG_FIELDS[a].mapping[value])
    values = app.Psc330MonitorApp._mode_config_raw_values(fake)
    assert values[332] == 0
    observation('monitor_clears_aux_when_cooling_reheat_disabled', {
        'input': {'127': 0, '128': 1, '129': 0, '332': 1},
        'normalized': {str(k): values[k] for k in (127, 128, 129, 332)},
        'limitation_reproduced': True, 'firmware_accepts_aux_in_this_configuration': True})

    f = board(2)
    raw = {a: app.signed16(f.p(a)) for a in app.MODE_CONFIG_FIELDS if a < 500}
    raw.update({128: 0, 127: 0, 129: 0, 329: 1, 330: 2, 336: 2,
                337: 0, 338: 0, 381: 0, 341: 30, 342: 100, 340: 100})
    app.Psc330MonitorApp._validate_mode_config(raw)
    observation('monitor_accepts_return_AO_and_supply_valve_AO', {
        'validation_rejected': False, '330': 2, '336': 2,
        'firmware_conflict_940': 2, 'firmware_disables_return_fan': True,
        'limitation_reproduced': True})

    # Exercise actual linked sysrun.o code using an emulated byte EEPROM.
    # No source for this object is present in the build project.
    def memory_firmware(memory=None):
        f = Firmware(IN)
        f.uc.mem_map(0x22000000, 0x100000)
        f.call('ParameterInit')
        for i in range(500):
            v = f.var('Parameter_def', index=i, width=2)
            f.p(i, v)
            f.var('Old_Parameter', v, i, 2)
        mem = bytearray(4096) if memory is None else bytearray(memory)
        if memory is None:
            for i in range(500): mem[16+2*i:18+2*i] = f.p(i).to_bytes(2, 'big')
        writes = []
        def read(uc, a, size, data):
            dst, count, src = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
            assert src+count <= len(mem)
            uc.mem_write(dst, bytes(mem[src:src+count]))
            uc.reg_write(UC_ARM_REG_R0, 1)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        def write(uc, a, size, data):
            val, dst = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
            assert dst < len(mem)
            mem[dst] = val & 255
            writes.append([dst, val & 255])
            uc.reg_write(UC_ARM_REG_R0, 1)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        for name, hook in [('CI2C_ReadByte', read), ('CI2C_WriteByte', write)]:
            addr = f.symbols[name][0] & ~1
            f.uc.hook_add(UC_HOOK_CODE, hook, begin=addr, end=addr)
        return f, mem, writes
    f, mem, writes = memory_firmware()
    setp(f, {161: 271, 166: 1, 236: 1})
    cutoff = None
    for step in range(50):
        f.var('Systick_1ms', 30000+step*10)
        f.call('WriteParamaterEEprom')
        if len(writes) == 4 and cutoff is None:
            cutoff = bytes(mem)
        if len(writes) == 6 and f.var('Old_Parameter', index=236, width=2) == 1: break
    assert cutoff is not None and len(writes) == 6
    rows = []
    for label, image, expected_mode in [('interrupted_after_run_bit', cutoff, 0),
                                        ('completed_save', bytes(mem), 1)]:
        b, _, _ = memory_firmware(image)
        b.call('Readeeprom')
        row = {'case': label, '161': b.p(161), '166': b.p(166), '236': b.p(236)}
        assert (row['161'], row['166'], row['236']) == (271, 1, expected_mode), row
        rows.append(row)
    observation('EEPROM_snapshot_non_atomic_ARM', {
        'write_bytes': writes, 'reloads': rows,
        'scope': 'Actual linked ARM save/load code with emulated EEPROM; not physical power cut'})

    result = {'firmware_sha256': hashlib.sha256((ROOT/IN).read_bytes()).hexdigest(),
              'hardware_access': False, 'firmware_modified': False,
              'observations': observations}
    D.mkdir(exist_ok=True, parents=True)
    (D/'observations.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', 'utf-8')
    print('All observations reproduced; limitations are not acceptance passes.')

if __name__ == '__main__': main()
