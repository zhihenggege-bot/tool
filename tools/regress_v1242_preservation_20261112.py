"""Rebind existing ARM regressions without editing historical harnesses."""
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[1]
name=sys.argv[1]
assert name in ('focused','shared','protection','lifecycle','comm')
script='test_issuefix_arm_20261111.py' if name=='focused' else 'test_issuefix_preservation_20261111.py'
path=R/'tools'/script
s=path.read_text('utf8').replace('.codex-tmp/issuefix_v1059_v1241_20261111',
    '.codex-tmp/vfd_scale_v1242_20261112').replace('测试证据/修复回归_20261111',
    '测试证据/四项复核_20261112').replace('12.41','12.42')
exec(compile(s,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
