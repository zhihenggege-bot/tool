"""Offline regression against the built Keil AXFs; never connects to hardware.

Requires unicorn and pyelftools (or .codex-tmp/defrost_test_deps).
Run after building BOTH firmware projects: py -3 tools/test_defrost_lifecycle_arm.py
Executes actual firmware functions, including static functions, with RAM/IO inputs
injected in Unicorn. Does not emulate physical relays or serial transport timing.
"""
from pathlib import Path
import io
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.codex-tmp/defrost_test_deps'))
from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarf_expr import DWARFExprParser
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0


class Firmware:
    def __init__(self, path):
        self.elf = ELFFile(io.BytesIO((ROOT / path).read_bytes()))
        self.symbols = {s.name: (s['st_value'], s['st_size']) for s in
                        self.elf.get_section_by_name('.symtab').iter_symbols() if s.name}
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for addr, size in [(0x08000000, 0x200000), (0x20000000, 0x80000),
                           (0x40000000, 0x100000), (0xE0000000, 0x100000)]:
            self.uc.mem_map(addr, size)
        for seg in self.elf.iter_segments():
            if seg['p_type'] == 'PT_LOAD' and seg['p_filesz']:
                self.uc.mem_write(seg['p_vaddr'], seg.data())
        # ARMCC stores RW initializers compressed in flash. Loading PT_LOAD
        # alone leaves nonzero C initializers unset. Execute only the runtime's
        # scatter loader, stopping before library init/main/hardware access.
        self.uc.reg_write(UC_ARM_REG_SP, 0x20070000)
        runtime_entry = self.symbols['__rt_entry'][0] & ~1
        self.uc.emu_start(self.symbols['__scatterload'][0] | 1, runtime_entry,
                          count=2000000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == runtime_entry, 'C data initialization failed'
        self.structs = {}
        dwarf = self.elf.get_dwarf_info()
        parser = DWARFExprParser(dwarf.structs)
        for cu in dwarf.iter_CUs():
            for die in cu.iter_DIEs():
                if die.tag != 'DW_TAG_structure_type' or 'DW_AT_name' not in die.attributes:
                    continue
                name = die.attributes['DW_AT_name'].value.decode(errors='replace')
                if name not in ('UNIT_STATUS_STRU_Read', 'UNIT_STATUS_STRU_Write') or name in self.structs:
                    continue
                members = {}
                for child in die.iter_children():
                    if 'DW_AT_data_member_location' in child.attributes:
                        loc = child.attributes['DW_AT_data_member_location'].value
                        offset = loc if isinstance(loc, int) else parser.parse_expr(loc)[0].args[0]
                        members[child.attributes['DW_AT_name'].value.decode()] = offset
                self.structs[name] = (die.attributes['DW_AT_byte_size'].value, members)

    def write(self, addr, value, size=4):
        self.uc.mem_write(addr, (value & ((1 << (size*8))-1)).to_bytes(size, 'little'))

    def read(self, addr, size=4):
        return int.from_bytes(self.uc.mem_read(addr, size), 'little')

    def var(self, name, value=None, index=0, width=None):
        addr, length = self.symbols[name]
        width = width or length
        addr += index * width
        if value is not None:
            self.write(addr, value, width)
        return self.read(addr, width)

    def p(self, index, value=None):
        return self.var('Parameter', value, index, 2)

    def field(self, write, unit, member, index=0, value=None, width=2):
        size, fields = self.structs['UNIT_STATUS_STRU_' + ('Write' if write else 'Read')]
        addr = self.symbols['UnitWriteStatus' if write else 'UnitReadStatus'][0] + unit*size + fields[member] + index*width
        if value is not None:
            self.write(addr, value, width)
        return self.read(addr, width)

    def call(self, name, *args):
        sp = 0x20070000
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.uc.reg_write(UC_ARM_REG_LR, 0x081F0001)
        for i, arg in enumerate(args):
            if i < 4:
                self.uc.reg_write(UC_ARM_REG_R0+i, arg)
            else:
                self.write(sp+(i-4)*4, arg)
        self.uc.emu_start(self.symbols[name][0] | 1, 0x081F0000, count=2000000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == 0x081F0000, name + ': execution did not return'
        return self.uc.reg_read(UC_ARM_REG_R0)


OUT = 'PSC316RK-V12-外机/OBJ/PSC316RK-V12-20250327.axf'
IN = 'PSC330RK-V10-内机/Project/Obj/PSC330RK-V10.axf'
passed = 0


def check(condition, label):
    global passed
    assert condition, label
    passed += 1
    print('PASS', label)


def outdoor(running=(1, 1), disabled_second=False):
    f = Firmware(OUT)
    f.var('BoardAddressSet', 1)
    for addr, value in {1: 1, 182: 100, 183: 30, 184: 4, 185: 10,
                        186: -20, 187: 100, 188: 30, 189: 35, 190: 400,
                        191: 4, 192: 3, 1409: 1, 1410: 1, 1422: 50,
                        153: int(disabled_second)}.items():
        f.p(addr, value)
    for i, run in enumerate(running):
        f.var('output', run, i, 1)
        f.var('Comp', run, i, 1)
    f.call('DefrostProcess')
    return f


def tick(f, n):
    f.var('uc1s', 1)
    for _ in range(n):
        for i in range(2):
            f.var('output', f.var('Comp', index=i, width=1), i, 1)
        f.call('DefrostProcess')
    f.var('uc1s', 0)


def indoor():
    f = Firmware(IN)
    f.p(214, 5)
    # These fixtures model connected units whose full settings were read.
    for i in range(4):
        f.var('PSC316SetValid', 1, i, 1)
    for i in range(8):
        f.p(250+i, 1)
    return f


def feedback(o, i):
    # Same status words used by the Modbus parser, without serial timing.
    for c in range(2):
        i.field(False, 1, 'CanDefrost', c, o.p(1420+c))
        i.field(False, 1, 'CompStatus', c, 4 if o.var('Comp', index=c, width=1) else 0)


def main():
    o = outdoor()
    check(o.p(1420) == o.p(1421) == 8, 'active lifecycle published to BOTH real status registers')
    check(o.var('Comp', index=0, width=1) == o.var('Comp', index=1, width=1) == 1,
          'already running compressors stay on')
    for comp, raw in [(0, 'X_00'), (1, 'X_02')]:
        f = outdoor()
        f.var(raw, 1)  # Debounced X00_En / X02_En remain zero.
        f.call('CompErrAction')
        f.call('DefrostProcess')
        check(f.var('Comp', index=comp, width=1) == 0 and
              f.var('Comp', index=1-comp, width=1) == 1,
              f'raw high-pressure {comp+1}: same scan stops ONLY its compressor')
        check(f.p(606) == f.p(607) == 0, f'raw high-pressure {comp+1}: no new high-pressure alarm')
        f.var(raw, 0)
        tick(f, 40)
        check(f.var('Comp', index=comp, width=1) == 0 and f.p(1420+comp) == 8,
              f'compressor {comp+1} cannot restart this defrost; lifecycle remains active')
    o.var('X_00', 1)
    o.var('X_02', 1)
    o.call('DefrostProcess')
    check(o.p(1420) == o.p(1421) == 7 and o.var('PSC316DefrostState') == 2,
          'both ended: all stopped and recovery published')
    i = indoor()
    i.field(False, 2, 'CanDefrost', value=1)
    i.var('PSC316DefrostOwner', 1)
    for c in range(2):
        i.field(True, 1, 'CompControl', c, 1)
    feedback(o, i)
    i.call('PSC316UpdateDefrostOwner')
    check(i.var('PSC316DefrostOwner') == 1, 'second outdoor request waits during recovery')
    check(i.call('IndoorOutdoorStopped') == 0 and i.call('IndoorDefrostActive') == 1,
          'indoor shutdown and auxiliary control still see recovery as defrost')
    i.call('CompNormalStopAction')
    check(i.field(True, 1, 'CompControl', 0) == i.field(True, 1, 'CompControl', 1) == 0,
          'normal shutdown retires requests after actual compressors stop in recovery')
    tick(o, 59)
    o.call('CompErrAction')
    check(o.p(1420) == 7 and o.p(606) == o.p(607) == 0,
          '59 seconds: recovery and high-pressure alarm masking remain')
    tick(o, 1)
    check(o.p(1420) == o.p(1421) == 0 and o.var('PSC316DefrostState') == 0,
          '60 seconds: lifecycle registers clear to complete')
    feedback(o, i)
    i.call('PSC316UpdateDefrostOwner')
    check(i.var('PSC316DefrostOwner') == 2, 'completed unit releases owner to next outdoor')
    i.call('CompNormalStopAction')
    check(i.field(True, 1, 'CompControl', 0) == i.field(True, 1, 'CompControl', 1) == 0,
          'completed stopped compressors have shutdown requests cleared without restart')
    o.call('CompErrAction')
    check(o.p(606) == o.p(607) == 1, 'still-open high-pressure switches alarm after recovery')
    tick(o, 2)
    check(o.p(1420) == o.p(1421) == 0, 'old request does not retrigger completed defrost')
    f = outdoor(running=(1, 0))
    tick(f, 29)
    check(f.var('Comp', index=1, width=1) == 0, 'second compressor remains off before 30 seconds')
    tick(f, 1)
    check(f.var('Comp', index=1, width=1) == 1, 'second compressor starts at 30 seconds')
    f = outdoor(disabled_second=True)
    check(f.p(1420) == 8 and f.p(1421) == 6, 'disabled circuit is excluded from lifecycle')
    f.var('X_00', 1)
    f.call('DefrostProcess')
    check(f.p(1420) == 7 and f.p(1421) == 6, 'excluded circuit cannot block recovery')
    f.p(1, 0)
    f.call('DefrostProcess')
    check(f.p(1420) == f.p(1421) == 0, 'leaving heating clears published lifecycle')
    f = indoor()
    for state in (0, 1, 5, 6, 7, 8):
        f.field(False, 1, 'CanDefrost', value=state)
        check(f.call('PSC316UnitDefrostActive', 1) == int(state in (7, 8)),
              f'indoor state {state}: request/disabled distinguished from active/recovery')
    f.field(False, 1, 'CanDefrost', value=0)
    f.field(False, 1, 'CompStatus', value=4)
    check(f.call('PSC316UnitDefrostActive', 1) == 1, 'legacy running status 4 remains supported')
    f.var('UnitCommErr', 1, 1, 2)
    check(f.call('PSC316UnitDefrostActive', 1) == 0, 'communication failure does not retain stale lifecycle')
    for state in (7, 8):
        f = indoor()
        f.field(False, 1, 'CanDefrost', value=1)
        f.field(False, 3, 'CanDefrost', value=state)
        f.call('PSC316UpdateDefrostOwner')
        check(f.var('PSC316DefrostOwner') == 3 and f.field(True, 1, 'DefrostSignal') == 0,
              f'owner lost/restarted: observed state {state} takes priority over a new request')
        f.var('CompMinStopCount', 1000, 6, 4)
        check(f.call('CompCanLoad', 3, 0) == 0,
              f'state {state}: capacity loading excluded even after minimum stop time')
        f.field(False, 3, 'CompStatus', value=3)
        f.field(True, 3, 'CompControl', value=1)
        f.var('CompMinRunCount', 1000, 6, 4)
        check(f.call('CompCanUnload', 3, 0) == 0,
              f'state {state}: capacity unloading excluded even with running feedback')
    for cause in ('fault', 'disabled', 'communication', 'phase'):
        f = indoor()
        f.field(False, 1, 'CanDefrost', value=7)
        f.field(True, 1, 'CompControl', value=1)
        if cause == 'fault':
            f.field(False, 1, 'CompStatus', value=1)
        elif cause == 'disabled':
            f.p(250, 0)
        elif cause == 'communication':
            f.var('UnitCommErr', 1, 1, 2)
        else:
            f.var('X00_En', 1)
        f.call('CompNormalStopAction')
        check(f.field(True, 1, 'CompControl') == 0,
              f'{cause} protection still clears requests during recovery')
    for pid in (0, 1):
        f = indoor()
        f.p(236, 1)
        f.p(365, pid)
        f.p(10, 500)
        f.p(12, 500)
        f.p(21, 350)
        f.p(411, 200)
        f.p(709, 3)
        # First EEV_Action homes; modeled position is already zero.
        f.field(False, 1, 'CanDefrost', value=8)
        f.call('EEV_Action', 0)
        f.p(1153, 0)
        f.call('EEV_Action', 0)
        check(f.p(1145) == 350, f'EEV option {pid}: active defrost with zero compressor request opens valve')
        f.field(False, 1, 'CanDefrost', value=7)
        f.p(1153, 350)
        f.call('EEV_Action', 0)
        check(f.p(1145) == 350, f'EEV option {pid}: stopped recovery holds defrost opening')
        f.field(False, 1, 'CanDefrost', value=0)
        f.var('uc1s', 1)
        f.call('EEV_Action', 0)
        check(f.p(1145) == 350 and f.p(1153) == 370,
              f'EEV option {pid}: completion adds normal 20-step seating travel and consumes one20-step tick')
    print(f'{passed} checks passed against built ARM firmware.')


if __name__ == '__main__':
    main()
