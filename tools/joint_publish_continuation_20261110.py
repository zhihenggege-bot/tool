"""Record restored continuation subscopes, retaining prior failures and limits."""
from pathlib import Path
import json,csv,io,collections

ROOT=Path(__file__).resolve().parents[1];DAY=ROOT/'测试证据/内外机联合实测_20261110'


def latest(pattern):
    paths=sorted(DAY.glob(pattern))
    if not paths:return None,None
    p=paths[-1];return p,json.loads(p.read_text('utf8'))


def main():
    updates={};details=[]
    p,j=latest('outdoor_NTC_protection_recovery_*.json')
    if j and j.get('restored') and not j.get('today_cleanup_error'):
        e=j['continuation_case']
        for r in e['cases']:
            if 'alarm_auto_cleared_without_reset' not in r:continue
            system=r['system'];scope='本台两压机停' if system is None else f'系统{system+1}停，另一系统继续'
            detail=f'两压机实际制热前置；原始NTC{r["channel"]} ADC=0模拟异常，316[{r["alarm_parameter"]}]=1时{scope}；保持源再恢复，未发复位，当前报警及故障分层自动清除。另一台外机反馈{r.get("other_outdoor_status")}。330镜像单次回读为出现{r.get("330_fault_mirror")}/恢复{r.get("recovered_330_mirror")}，不同步刷新边沿未完成稳定等待，镜像确认另验；非真实断线/端子，非双探头同时故障或手动路径验收。'
            updates[r['id']]=dict(status='探头保护/自动消警子范围通过；镜像等另验',detail=detail,path=p)
            details.append((r['id'],detail,p))
    p,j=latest('outdoor_running_disable_*.json')
    if j and j.get('restored') and not j.get('today_cleanup_error'):
        e=j['continuation_case']
        if not e.get('execution_error') and e.get('allowed_again'):
            grouped={}
            for r in e['cases']:grouped.setdefault(r['id'],[]).append(r)
            for cid,rs in grouped.items():
                detail=f'配对{e["type_pair"]}、正常330制热命令；'+ '；'.join(r['label']+'→WJ1压机输出'+str(r['wanted']) for r in rs)+'。各段稳定观察2秒，另一外机两压机保持制热；解除全部禁用后普通自动需求使WJ1两压机重新运行。仅当前配对自动运行路径；手动及其余配对另验。'
                updates[cid]=dict(status='自动运行禁用子范围通过；手动/其它配对另验',detail=detail,path=p);details.append((cid,detail,p))
    p,j=latest('O-HEATFAN-002_two_fixed_hysteresis_*.json')
    if j and j.get('restored') and not j.get('today_cleanup_error'):
        e=j['continuation_case']
        if not e.get('execution_error') and len(e['points'])==7 and all(r.get('status')=='软件子范围通过' for r in e['points']):
            detail='0/1两定配对、双压机制热，NTC0原始ADC模拟环温6.9→7→9→12→12.1→10→6.9℃；每点精确输入连续33秒。风机数量分别2/2/2/2/1/1/2，跨阈值前28.5秒不提前改变。验证7/12℃等号与中间保持、30秒保持后动作；最低启停及机械端子、等时长轮换、单压机和其余配对另验。'
            cid=e['id'];updates[cid]=dict(status='双压机制热回差子范围通过；轮换/单压机另验',detail=detail,path=p);details.append((cid,detail,p))
    table=ROOT/'室外机逐项测试表_20261110.csv.txt';rows=list(csv.DictReader(io.StringIO(table.read_text('utf8'))));assert len(rows)==156
    for r in rows:
        if r['用例'] in updates:
            u=updates[r['用例']];r['状态']=u['status'];r['实测结论']=u['detail'];r['证据路径']=u['path'].relative_to(ROOT).as_posix()
    buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows);table.write_text(buf.getvalue(),encoding='utf8')
    lines=['# 联合续测结果（2026-11-10）','','用户要求继续测试、先报告原因且暂不改代码。本页为10:24之后新增结果；仍为BENCH软件/输入模拟，不代表物理端子或正式档验收。','','[四项问题与规格原文对照](四项实测问题与规格原文对照_20261110.md)记录解释及用户后续确认：定时化霜额外固定10℃门槛现判不符合，急停收尾方案仍待确定；原始数据保留。','','|用例|本次覆盖及限制|证据|','|---|---|---|']
    for cid,detail,p in details:lines.append(f'|{cid}|{detail}|[{p.stem}]({p.relative_to(ROOT).as_posix()})|')
    lines+=['','本次新增软件子范围涉及 '+str(len(updates))+' 行；各行均保留未覆盖组合，不能据行数认定完整通过。','', '外机156行状态：'+json.dumps(dict(collections.Counter(r['状态'] for r in rows)),ensure_ascii=False)+'。']
    p,j=latest('final_independent_readback_*.json')
    if j:lines+=['',f'最近独立回读：[原始检查]({p.relative_to(ROOT).as_posix()})，检查时间{j["started"]}，passed={j["passed"]}。仅证明该时间点，若晚于此回读还有运行测试须再收尾。']
    (ROOT/'内外机联合续测结果_20261110.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (DAY/'continuation_result_summary.json').write_text(json.dumps(dict(updated_ids=sorted(updates),outdoor_status_counts=dict(collections.Counter(r['状态'] for r in rows))),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Updated',sorted(updates))


if __name__=='__main__':main()
