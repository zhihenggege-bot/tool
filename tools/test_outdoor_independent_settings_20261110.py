"""Exercise the actual monitor write method without a port or Tk window."""
import json
import sys
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'psc330_monitor_tool/psc330_monitor'))
from app import Psc330MonitorApp, ModbusError, OUTDOOR_GATEWAY_BASE, OUTDOOR_GATEWAY_STEP, INDOOR_SHARED_OUTDOOR, POLL_BLOCKS

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=ROOT/'测试证据/机型风机全局共享_20261110/independent_settings_monitor.json')
args=parser.parse_args()

rows=[]
def check(name, got, want):
    rows.append(dict(name=name,observed=got,expected=want,passed=got==want))
    assert got==want,rows[-1]

def fixture(unit,pair,step=0,fail=False,shared=0):
    app=object.__new__(Psc330MonitorApp)
    app.values={};app.calls=[]
    base=OUTDOOR_GATEWAY_BASE+(unit-1)*OUTDOOR_GATEWAY_STEP
    registers={709:step,1319:shared,base:pair[0],base+1:pair[1]}
    app.read_now=lambda addr,n:[registers[addr+i] for i in range(n)]
    def write(base_arg,address,parameter,value):
        app.calls.append([base_arg,address,parameter,value])
        if not fail:registers[address]=value
    app.write_outdoor_gateway_register=write
    return app,registers,base

for unit in range(1,5):
    for order in ((165,166),(166,165)):
        a,r,b=fixture(unit,[0,0])
        for p in order:
            other=b+1 if p==165 else b;before=r[other]
            result=a.write_outdoor_spec_field(unit,p,1 if p==165 else 2)
            check(f'unit{unit}/order{order}/{p}/other-unchanged',r[other],before)
            check(f'unit{unit}/order{order}/{p}/one-word',a.calls[-1],[b,b+p-165,p,1 if p==165 else 2])
        check(f'unit{unit}/order{order}/final',list(result),[1,2])
    for p in (165,166):
        a,r,b=fixture(unit,[0,0],step=2)
        try:a.write_outdoor_spec_field(unit,p,1)
        except ModbusError:pass
        else:raise AssertionError('running configuration was accepted')
        check(f'unit{unit}/{p}/running-no-write',a.calls,[])
for unit,p,value in ((0,165,1),(5,166,2),(1,164,0),(1,165,3),(1,166,5),(1,165,-1)):
    a,r,b=fixture(1,[0,0])
    try:a.write_outdoor_spec_field(unit,p,value)
    except ValueError:pass
    else:raise AssertionError('invalid setting accepted')
    check(f'invalid/{unit}/{p}/{value}/no-write',a.calls,[])
a,r,b=fixture(1,[0,0],fail=True)
try:a.write_outdoor_spec_field(1,165,1)
except ModbusError:pass
else:raise AssertionError('readback mismatch accepted')
check('readback-mismatch-no-cache-success',b not in a.values,True)

class Variable:
    def __init__(self,v):self.v=v
    def get(self):return self.v
    def set(self,v):self.v=v
class Combo:
    def configure(self,**kwargs):self.kwargs=kwargs
a,r,b=fixture(1,[0,0])
a._outdoor_spec_syncing=False
a.outdoor_unit_type_var=Variable('1: 0-43')
a.outdoor_fan_type_var=Variable('0: 双速')
a.outdoor_fan_type_combo=Combo()
a._set_outdoor_spec_status=lambda text:None
a._on_outdoor_unit_type_selected(None)
check('select165-keeps166-selection',a.outdoor_fan_type_var.get(),'0: 双速')
check('select165-all-five-fan-options',len(a.outdoor_fan_type_combo.kwargs['values']),5)

for unit in range(1,5):
    for parameter in (165,166):
        a,r,b=fixture(unit,[0,1],shared=1)
        try:a.write_outdoor_spec_field(unit,parameter,2)
        except ModbusError:pass
        else:raise AssertionError('shared-on per-unit write was accepted')
        check(f'shared-on/unit{unit}/{parameter}/no-write',a.calls,[])
for address,lo,hi in ((1343,0,2),(1344,0,4)):
    definition=next(d for d in INDOOR_SHARED_OUTDOOR if d.address==address)
    check(f'shared-definition/{address}/bounds',[definition.minimum,definition.maximum],[lo,hi])
    check(f'shared-definition/{address}/polled',any(b.start<=address<b.start+b.count for b in POLL_BLOCKS),True)

dest=args.output
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(dict(hardware_tested=False,passed=len(rows),total=len(rows),rows=rows),ensure_ascii=False,indent=2)+'\n','utf8')
print('MONITOR',len(rows),'passed')
