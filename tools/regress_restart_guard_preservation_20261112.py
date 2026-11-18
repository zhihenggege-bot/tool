"""Rebind existing ARM suites to the new exact images; keep earlier evidence."""
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[1]
name=sys.argv[1]
assert name in ('focused','shared','protection','lifecycle','comm','fan_threshold','scaling')
dest=R/'测试证据/四项复核_20261112/restart_fix/arm'
dest.mkdir(parents=True,exist_ok=True)
if name=='fan_threshold':script='test_fan_thresholds_arm_20261111.py'
elif name=='scaling':script='test_vfd_scale_arm_20261112.py'
elif name=='focused':script='test_issuefix_arm_20261111.py'
else:script='test_issuefix_preservation_20261111.py'
p=R/'tools'/script
s=p.read_text('utf8')
for old in ('.codex-tmp/issuefix_v1059_v1241_20261111','.codex-tmp/vfd_scale_v1242_20261112'):
    s=s.replace(old,'.codex-tmp/restart_guard_v1060_v1243_20261112')
for old in ('测试证据/修复回归_20261111','测试证据/四项复核_20261112'):
    # Replace once from the historical path, avoiding a second substitution
    # into the newly expanded destination.
    if old in s:
        s=s.replace(old,'__CURRENT_ARM_DEST__')
s=s.replace('__CURRENT_ARM_DEST__','测试证据/四项复核_20261112/restart_fix/arm')
s=s.replace('12.41','12.43').replace('12.42','12.43').replace('10.59','10.60')
exec(compile(s,str(p),'exec'),dict(__name__='__main__',__file__=str(p)))
