"""Rerun timing/transport suites with paths rebound to current exact images.

No board access. Retains simulated-time scope and separate evidence files.
"""
from pathlib import Path
import hashlib
import json
import sys
from test_defrost_lifecycle_arm import ROOT


def main():
    package='.codex-tmp/fan_zero_target_v1052_v1239_20261105'
    dest='测试证据/内机实测_20261105/BENCH_V1052_V1239'
    for script,result_name in (
        ('test_sequence_bench_timing_arm.py','sequence_test_result.json'),
        ('test_comm_poll_health_arm.py','comm_poll_test_result.json')):
        source=(ROOT/'tools'/script).read_text('utf8')
        for old in ('.codex-tmp/persistence_interlock_v1049_v1239_20261105',
                    '.codex-tmp/sequence_timing_v1047_v1238_20261104'):
            source=source.replace(old,package)
        source=source.replace('PSC330_V10.47_','PSC330_V10.52_')
        source=source.replace("v='10.49' if model==330", "v='10.52' if model==330")
        # Redirect only the report destination, not the image fixture.
        source=source.replace("(D/'sequence_test_result.json')",f"(ROOT/'{dest}/sequence_test_result.json')")
        source=source.replace(f"(ROOT/'{package}/comm_poll_test_result.json')",f"(ROOT/'{dest}/comm_poll_test_result.json')")
        print('RUN',script,flush=True)
        exec(compile(source,script,'exec'),{'__name__':'__main__','__file__':str(ROOT/'tools'/script)})
    print('CURRENT TIMING AND TRANSPORT COMPLETE',flush=True)


if __name__=='__main__':main()
