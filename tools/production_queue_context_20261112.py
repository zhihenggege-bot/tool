"""Bind exact PRODUCTION images and preserve the existing BENCH drivers.

Only test-driver assertions/deadlines are adapted; no firmware source is edited.
The exact adapted Python source is saved for review before hardware access.
"""
import full_queue_context_20261112 as bench
import inspect
import sys
import textwrap

DAY=bench.R/'测试证据/剩余全队列_20261112/PRODUCTION'
DAY.mkdir(parents=True,exist_ok=True)
I=bench.I.parent/'PRODUCTION'
BOARDS=[tuple([*b[:-1],b[-1].replace('BENCH_ONLY_3S','PRODUCTION')]) for b in bench.BOARDS]
module=bench.bound;seen=set()
while id(module) not in seen:
    seen.add(id(module));module.DAY=module.D=DAY;module.I=I;module.BOARDS=BOARDS
    module.LIMITS='330 V10.60 /316 V12.43 PRODUCTION; real elapsed time, software inputs/outputs; not physical terminals'
    if not hasattr(module,'prior'):break
    module=module.prior
bench.runtime.D=DAY;bench.runtime.I=I;bench.runtime.BOARDS[:]=BOARDS
bench.runtime.RESULTS=DAY/'case_results.json'
bench.heat.D=DAY;bench.heat.I=I;bench.heat.BOARDS=BOARDS
bench.precondition.DAY=DAY;bench.precondition.I=I;bench.precondition.BOARDS=BOARDS

from joint_v1060_context_20261112 import *

def adapt(function, replacements, name):
    source=textwrap.dedent(inspect.getsource(function))
    for old,new in replacements:
        assert source.count(old)==1,(name,old)
        source=source.replace(old,new)
    dest=DAY/'adapted_driver_sources';dest.mkdir(exist_ok=True)
    (dest/(name+'.py')).write_text(source,encoding='utf8')
    namespace=dict(function.__globals__)
    namespace.update(D=DAY,DAY=DAY,I=I,BOARDS=BOARDS)
    exec(compile(source,str(dest/(name+'.py')),'exec'),namespace)
    return namespace[function.__name__]

runtime.ControlBench.__init__=adapt(runtime.ControlBench.__init__,[('==[15107]','==[0]')],'production_constructor')
Base=current_bench_class()

class ProductionBench(Base):
    def record_local(self,cid,passed,actual,entry):
        actual=actual.replace('V10.55','V10.60 /316 V12.43 PRODUCTION')
        entry['profile']='PRODUCTION'
        return super().record_local(cid,passed,actual,entry)
    def wr(self,a,value):
        floors={42:120,43:180,1298:300}
        if a in floors and value<floors[a]:
            self.log.setdefault('formal_driver_parameter_floors',[]).append(dict(address=a,legacy_request=value,actual_request=floors[a]))
            value=floors[a]
        return super().wr(a,value)
    def start(self,special_ready=False):
        self.wr(398,1)
        return self.wait('PRODUCTION start complete',lambda s:s['state'][9]==2,360)
    def stop(self):
        self.wr(398,0)
        return self.wait('PRODUCTION normal stop',lambda s:s['state'][9]==0,900,True)

def current_bench_class():return ProductionBench
bench.bound.current_bench_class=current_bench_class

import bench_current_20261112 as common
common.DAY=DAY;common.I=I;common.BOARDS=BOARDS
production_audit=adapt(common.audit,[("q['profile'][1]==15107","q['profile'][1]==0")],'production_audit')

def audit(label='production_independent_audit',image=False):return production_audit(label,image)

