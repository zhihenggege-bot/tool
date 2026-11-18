"""Select exact V10.55 build/date before importing any bench helper."""
import os
from pathlib import Path
os.environ['PSC_BENCH_PACKAGE']='.codex-tmp/special_display_v1055_v1239_20261109'
os.environ['PSC_BENCH_INDOOR_VERSION']='10.55'
_root=Path(__file__).resolve().parents[1]
_dest=_root/'测试证据/内机实测_20261105/BENCH_V1055_V1239'
_dest.mkdir(parents=True,exist_ok=True)
if not (_dest/'remaining_571_manifest.json').exists():
    (_dest/'remaining_571_manifest.json').write_bytes((_root/'测试证据/内机实测_20261105/BENCH_V1054_V1239/remaining_571_manifest.json').read_bytes())
from heat_dynamic_board_20261106 import *
runtime.EXPECTED[5]=9
