"""Pure predicate regressions; extract AST helpers without bench imports."""
import ast
import copy
import json
from pathlib import Path
from test_defrost_lifecycle_arm import Firmware, ROOT


def main():
    path = ROOT / 'tools/bench_remaining_defrost_matrix_20261111.py'
    tree = ast.parse(path.read_text('utf8'))
    names = {'whole_unit_defrost_finished', 'qualified_lp_mask_sample'}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(functions) == 2
    ns = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), ns)
    rows = []

    def check(name, got, want):
        row = dict(name=name, got=got, want=want, passed=got == want)
        rows.append(row)
        assert row['passed'], row

    finished = ns['whole_unit_defrost_finished']
    base = dict(PSC316DefrostState=[0], owner=0, phase=[6, 6],
                mirror_phase=[6, 6], SysHaveDef=[0] * 5)
    check('completed-fault6-accepted', finished(base), True)
    for key, values in {'PSC316DefrostState': ([1], [2]), 'owner': (1, 2),
                        'phase': ([7, 6], [8, 6], [1, 6]),
                        'mirror_phase': ([7, 6], [8, 6]),
                        'SysHaveDef': ([1, 0, 0, 0, 0],)}.items():
        for value in values:
            s = copy.deepcopy(base); s[key] = value
            check(f'incomplete/{key}/{value}', finished(s), False)
    s = copy.deepcopy(base); s['phase'] = s['mirror_phase'] = [0, 0]
    check('ordinary-completion0-accepted', finished(s), True)
    active = ns['qualified_lp_mask_sample']
    base = dict(inputs=[0, 1] + [0] * 6, qualified_inputs=[0, 1] + [0] * 6,
                phase=[8, 8], alarms=[0] * 28)
    check('qualified-lp-in-active-defrost', active(base), True)
    for key, index, value in (('inputs', 1, 0), ('qualified_inputs', 1, 0),
                              ('phase', 0, 7), ('alarms', 0, 1)):
        s = copy.deepcopy(base); s[key][index] = value
        check(f'invalid-lp-window/{key}', active(s), False)
    # Fixtures consume these fields from the unchanged316 AXF. Validate symbol
    # presence/width offline so tomorrow's sampler does not discover a typo live.
    f = Firmware(ROOT / '.codex-tmp/ambient_scope_v1061_20261112/BENCH_ONLY_3S/PSC316_V12.43_BENCH_ONLY_3S.axf')
    for ch in range(8):
        check(f'qualified-input-symbol{ch}/width', f.symbols[f'X{ch:02d}_En'][1], 1)
    check('SysHaveDef-width', f.symbols['SysHaveDef'][1], 20)
    result = dict(hardware_access=False, scope='Synthetic predicate samples and ARM symbol metadata',
                  rows=rows, passed=len(rows), total=len(rows))
    dest = ROOT / '测试证据/环境联锁修复_20261112/bench_predicate_results.json'
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(len(rows), 'bench predicate/symbol checks passed')


if __name__ == '__main__':
    main()
