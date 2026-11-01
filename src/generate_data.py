#!/usr/bin/env python3
"""Create reproducible synthetic experimentation data (stdlib only; Python 3.7+)."""
import argparse
import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261022
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCENARIOS = ["balanced", "unbalanced", "srm", "delayed", "guardrail_regression", "balanced", "unbalanced", "delayed", "srm", "guardrail_regression"]
TABLES = {
    "experiments": ["experiment_id", "name", "hypothesis", "status", "randomization_unit", "allocation_method", "seed", "start_at", "end_at", "analysis_plan_id", "primary_metric_id", "conversion_window_days", "scenario"],
    "variants": ["variant_id", "experiment_id", "name", "allocation_ratio", "is_control", "effective_from", "effective_to"],
    "audience_members": ["audience_member_id", "experiment_id", "user_id", "eligible_at", "eligibility_status", "segment", "region"],
    "assignments": ["assignment_id", "experiment_id", "audience_member_id", "user_id", "variant_id", "assigned_at", "randomization_seed", "assignment_status"],
    "exposure_events": ["exposure_id", "experiment_id", "assignment_id", "user_id", "variant_id", "exposed_at", "surface", "telemetry_status"],
    "conversion_events": ["conversion_id", "experiment_id", "assignment_id", "user_id", "variant_id", "occurred_at", "event_name", "value_usd", "is_primary_conversion"],
    "metric_definitions": ["metric_id", "experiment_id", "name", "metric_type", "numerator_event", "denominator", "unit", "window_days", "version", "effective_from", "effective_to", "is_primary"],
    "guardrail_metrics": ["guardrail_id", "experiment_id", "metric_id", "name", "direction", "threshold", "unit", "severity"],
    "experiment_results": ["result_id", "experiment_id", "variant_id", "metric_id", "metric_version", "analysis_population", "n_assigned", "n_exposed", "numerator", "denominator", "estimate", "control_estimate", "absolute_effect", "relative_effect", "std_error", "ci95_low", "ci95_high", "p_value", "srm_p_value", "guardrail_status", "decision", "analysis_at", "analysis_plan_id"],
}

def iso(dt): return dt.isoformat().replace("+00:00", "Z")
def add_days(dt, days): return dt + timedelta(days=days)
def csv_write(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def stable_id(prefix, n, width=6):
    if prefix in ("EXPOS", "CONV"):
        return "%s-2026-%0*d" % (prefix, width, n)
    return "%s-%0*d" % (prefix, width, n)

def p_value_z(z):
    # Two-sided normal approximation; sufficient for a synthetic educational dataset.
    return math.erfc(abs(z) / math.sqrt(2.0))

def chi_square_p_1df(x):
    # For 1 df, survival function is erfc(sqrt(x/2)).
    return math.erfc(math.sqrt(max(0.0, x) / 2.0))

def binom_estimate(k, n): return (k / float(n)) if n else 0.0

def build(scale, seed, outdir):
    rng = random.Random(seed)
    outdir.mkdir(parents=True, exist_ok=True)
    for p in outdir.iterdir():
        if p.is_file(): p.unlink()
        elif p.is_dir(): shutil.rmtree(str(p))
    experiments=[]; variants=[]; audience=[]; assignments=[]; exposures=[]; conversions=[]; metrics=[]; guardrails=[]
    exp_meta=[]; assignment_counts={}; all_user_no=0; exposure_no=0; conversion_no=0
    per_exp = int(math.ceil(scale / 10.0))
    for ei, scenario in enumerate(SCENARIOS, 1):
        eid="EXP-2026-%06d" % ei
        start=BASE+timedelta(days=(ei-1)*14)
        end=start+timedelta(days=30)
        plan="PLAN-%s-v1" % eid
        mid="MET-%s-PRIMARY-v1" % eid
        experiments.append(dict(experiment_id=eid,name="Synthetic checkout experiment %02d"%ei,hypothesis="A simplified checkout treatment increases 14-day purchase conversion without materially increasing support contacts.",status="analyzed",randomization_unit="user",allocation_method="deterministic_hash_with_seed",seed=seed,start_at=iso(start),end_at=iso(end),analysis_plan_id=plan,primary_metric_id=mid,conversion_window_days=14,scenario=scenario))
        ratio=(0.7,0.3) if scenario=="unbalanced" else (0.5,0.5)
        for suffix,name,alloc,is_control in [("A","control",ratio[0],True),("B","treatment",ratio[1],False)]:
            variants.append(dict(variant_id="VAR-%s-%s"%(eid,suffix),experiment_id=eid,name=name,allocation_ratio=alloc,is_control=str(is_control).lower(),effective_from=iso(start),effective_to=iso(end)))
        metrics.append(dict(metric_id=mid,experiment_id=eid,name="14-day purchase conversion",metric_type="proportion",numerator_event="purchase",denominator="assigned_users",unit="rate",window_days=14,version=1,effective_from=iso(start),effective_to=iso(end),is_primary="true"))
        metrics.append(dict(metric_id="MET-%s-SUPPORT-v1"%eid,experiment_id=eid,name="Support contact rate",metric_type="proportion",numerator_event="support_contact",denominator="assigned_users",unit="rate",window_days=14,version=1,effective_from=iso(start),effective_to=iso(end),is_primary="false"))
        guardrails.append(dict(guardrail_id="GRD-%s-SUPPORT"%eid,experiment_id=eid,metric_id="MET-%s-SUPPORT-v1"%eid,name="Support contact rate",direction="max_increase",threshold=0.015 if scenario=="guardrail_regression" else 0.02,unit="absolute_rate_difference",severity="block"))
        exp_meta.append((eid,scenario,start,ratio,mid,plan))
        # A fixed seed is used with stable, reproducible stream sequencing.
        for j in range(per_exp):
            if all_user_no>=scale: break
            all_user_no+=1; uid="USR-%07d"%all_user_no; amid="AUD-%s-%07d"%(eid,j+1)
            eligible_at=start+timedelta(minutes=j%1440)
            audience.append(dict(audience_member_id=amid,experiment_id=eid,user_id=uid,eligible_at=iso(eligible_at),eligibility_status="eligible",segment=["new","returning","high_value"][j%3],region=["NA","EU","APAC"][j%3]))
            # PRNG assignment allows controlled SRM in one scenario; all assignment decisions are persisted.
            if scenario=="srm": treatment = rng.random()<0.62
            else: treatment = rng.random()>=ratio[0]
            vid="VAR-%s-%s"%(eid,"B" if treatment else "A")
            aid="ASG-%s-%s"%(eid,uid)
            assigned_at=eligible_at+timedelta(minutes=1)
            assignments.append(dict(assignment_id=aid,experiment_id=eid,audience_member_id=amid,user_id=uid,variant_id=vid,assigned_at=iso(assigned_at),randomization_seed=seed,assignment_status="assigned"))
            assignment_counts[(eid,vid)]=assignment_counts.get((eid,vid),0)+1
            # 8% noncompliance; telemetry missing for 4%. Exposure can lag assignment.
            compliant=rng.random()>=0.08
            telemetry_ok=rng.random()>=0.04
            exp_time=assigned_at+timedelta(minutes=rng.randint(1,240))
            if telemetry_ok:
                exposure_no+=1
                exposures.append(dict(exposure_id=stable_id("EXPOS",exposure_no),experiment_id=eid,assignment_id=aid,user_id=uid,variant_id=vid,exposed_at=iso(exp_time),surface="checkout",telemetry_status="observed"))
            # Outcome is generated from assignment (ITT); treatment effect and guardrail regression are controlled.
            pconv=0.08 + (0.012 if treatment else 0.0)
            if scenario=="guardrail_regression" and treatment: pconv=0.075
            if rng.random()<pconv:
                lag=rng.randint(1,12) if scenario=="delayed" else rng.randint(0,7)
                occurred=exp_time+timedelta(days=lag)
                conversion_no+=1
                conversions.append(dict(conversion_id=stable_id("CONV",conversion_no),experiment_id=eid,assignment_id=aid,user_id=uid,variant_id=vid,occurred_at=iso(occurred),event_name="purchase",value_usd=round(rng.uniform(18,240),2),is_primary_conversion="true"))
            # Support guardrail event, elevated under designated regression.
            support_p=0.025+(0.022 if scenario=="guardrail_regression" and treatment else 0.0)
            if rng.random()<support_p:
                conversion_no+=1
                conversions.append(dict(conversion_id=stable_id("CONV",conversion_no),experiment_id=eid,assignment_id=aid,user_id=uid,variant_id=vid,occurred_at=iso(exp_time+timedelta(days=rng.randint(0,5))),event_name="support_contact",value_usd=0.0,is_primary_conversion="false"))
    # Results are derived from assigned populations and observed event records, not sampled independently.
    by_assignment={a["assignment_id"]:a for a in assignments}
    by_event=defaultdict(list)
    for c in conversions: by_event[c["assignment_id"]].append(c)
    exposed_ids={e["assignment_id"] for e in exposures}
    results=[]
    for ei,(eid,scenario,start,ratio,mid,plan) in enumerate(exp_meta,1):
        arms=[]
        nA=assignment_counts.get((eid,"VAR-%s-A"%eid),0); nB=assignment_counts.get((eid,"VAR-%s-B"%eid),0)
        expectedA=ratio[0]*(nA+nB); chi=((nA-expectedA)**2/max(expectedA,1))+((nB-(nA+nB-expectedA))**2/max(nA+nB-expectedA,1))
        srm_p=chi_square_p_1df(chi)
        for suffix,metric_id in [("A",mid),("B",mid)]:
            vid="VAR-%s-%s"%(eid,suffix); arm=[a for a in assignments if a["experiment_id"]==eid and a["variant_id"]==vid]
            purchase_ids=set(); support_ids=set()
            for a in arm:
                for ev in by_event.get(a["assignment_id"],[]):
                    age=(datetime.fromisoformat(ev["occurred_at"].replace("Z","+00:00"))-datetime.fromisoformat(a["assigned_at"].replace("Z","+00:00"))).total_seconds()/86400.0
                    if ev["event_name"]=="purchase" and age<=14: purchase_ids.add(a["assignment_id"])
                    if ev["event_name"]=="support_contact" and age<=14: support_ids.add(a["assignment_id"])
            n=len(arm); k=len(purchase_ids); est=binom_estimate(k,n)
            arms.append((suffix,n,k,est,len(set(a["assignment_id"] for a in arm)&exposed_ids),len(support_ids)))
        control=arms[0][3]; treat=arms[1][3]; n1=arms[0][1]; n2=arms[1][1]
        se=math.sqrt(max(control*(1-control)/max(n1,1)+treat*(1-treat)/max(n2,1),0))
        effect=treat-control; z=effect/se if se else 0; p=p_value_z(z)
        support_diff=arms[1][5]/float(arms[1][1] or 1)-arms[0][5]/float(arms[0][1] or 1)
        guard_status="fail" if support_diff>next(g["threshold"] for g in guardrails if g["experiment_id"]==eid) else "pass"
        srm_status="fail" if srm_p<0.001 else "pass"
        decision="inconclusive_srm" if srm_status=="fail" else ("do_not_ship_guardrail" if guard_status=="fail" else ("ship_candidate" if p<0.05 and effect>0 else "no_evidence_of_lift"))
        for suffix,n,k,est,nexp,nsup in arms:
            results.append(dict(result_id="RES-%s-%s-PRIMARY-v1"%(eid,suffix),experiment_id=eid,variant_id="VAR-%s-%s"%(eid,suffix),metric_id=mid,metric_version=1,analysis_population="intention_to_treat",n_assigned=n,n_exposed=nexp,numerator=k,denominator=n,estimate=round(est,8),control_estimate=round(control,8),absolute_effect=round(effect,8),relative_effect=round(effect/control,8) if control else "",std_error=round(se,8),ci95_low=round(effect-1.96*se,8),ci95_high=round(effect+1.96*se,8),p_value=round(p,8),srm_p_value=round(srm_p,8),guardrail_status=guard_status,decision=decision,analysis_at=iso(end+timedelta(days=15)),analysis_plan_id=plan))
    # Explicitly labelled edge cases are added after valid baseline generation.
    ground=[]
    def label(case,entity,record_id,expected,detail): ground.append(dict(issue_id="ISS-%03d"%(len(ground)+1),issue_type=case,entity=entity,record_id=record_id,ground_truth=expected,details=detail))
    # Assigned to two variants: append a conflicting assignment with a unique key.
    seed_a=assignments[0]; alt="VAR-%s-%s"%(seed_a["experiment_id"],"B" if seed_a["variant_id"].endswith("-A") else "A")
    bad=dict(seed_a); bad.update(assignment_id=seed_a["assignment_id"]+"-DUPVAR",variant_id=alt,assignment_status="assigned")
    assignments.append(bad); label("multiple_variant_assignment","assignments",bad["assignment_id"],"invalid_assignment_integrity","Same user and experiment has assignments to both variants.")
    # Exposure before assignment.
    first=assignments[1]; exposure_no+=1
    bad_exp=dict(exposure_id=stable_id("EXPOS",exposure_no),experiment_id=first["experiment_id"],assignment_id=first["assignment_id"],user_id=first["user_id"],variant_id=first["variant_id"],exposed_at=iso(datetime.fromisoformat(first["assigned_at"].replace("Z","+00:00"))-timedelta(minutes=5)),surface="checkout",telemetry_status="observed")
    exposures.append(bad_exp); label("exposure_before_assignment","exposure_events",bad_exp["exposure_id"],"invalid_event_order","Exposure timestamp precedes the referenced assignment.")
    # Window mismatch: event beyond declared 14-day window but labelled primary conversion.
    first_exp=exp_meta[0]; first_asg=next(a for a in assignments if a["experiment_id"]==first_exp[0] and not a["assignment_id"].endswith("-DUPVAR"))
    conversion_no+=1
    bad_conv=dict(conversion_id=stable_id("CONV",conversion_no),experiment_id=first_exp[0],assignment_id=first_asg["assignment_id"],user_id=first_asg["user_id"],variant_id=first_asg["variant_id"],occurred_at=iso(datetime.fromisoformat(first_asg["assigned_at"].replace("Z","+00:00"))+timedelta(days=25)),event_name="purchase",value_usd=42.0,is_primary_conversion="true")
    conversions.append(bad_conv); label("outcome_window_inconsistent","conversion_events",bad_conv["conversion_id"],"exclude_from_primary_metric","Primary purchase occurs after the experiment's 14-day conversion window.")
    label("sample_ratio_mismatch_ignored","experiment_results","RES-%s-A-PRIMARY-v1"%next(e[0] for e in exp_meta if e[1]=="srm"),"block_decision_due_to_srm","A synthetic result record is subsequently marked as if SRM were ignored.")
    # Metric changed after results: version 2 is effective after analysis and conflicts with traceability.
    me=exp_meta[0]; metrics.append(dict(metric_id="MET-%s-PRIMARY-v2"%me[0],experiment_id=me[0],name="14-day purchase conversion",metric_type="proportion",numerator_event="purchase",denominator="assigned_users",unit="rate",window_days=7,version=2,effective_from=iso(datetime.fromisoformat(next(r["analysis_at"] for r in results if r["experiment_id"]==me[0]).replace("Z","+00:00"))+timedelta(days=1)),effective_to="",is_primary="true"))
    label("metric_definition_changed_after_results","metric_definitions","MET-%s-PRIMARY-v2"%me[0],"preserve_result_metric_version","Metric window changed after result; previous result must remain tied to v1.")
    # Mark a result's decision as ignored SRM, preserving the underlying numeric result and issue trail.
    for res in results:
        if res["experiment_id"]==next(e[0] for e in exp_meta if e[1]=="srm"):
            res["decision"]="srm_ignored_anomaly"; break
    # Write all source tables.
    data={"experiments":experiments,"variants":variants,"audience_members":audience,"assignments":assignments,"exposure_events":exposures,"conversion_events":conversions,"metric_definitions":metrics,"guardrail_metrics":guardrails,"experiment_results":results,"ground_truth":ground}
    for name,rows in data.items():
        fields=TABLES.get(name, ["issue_id","issue_type","entity","record_id","ground_truth","details"])
        csv_write(outdir/(name+".csv"),rows,fields)
        (outdir/(name+".json")).write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding="utf-8")
    # Portable SQLite DDL and seed statements with primary and foreign key constraints.
    with (outdir/"seed.sql").open("w",encoding="utf-8") as f:
        f.write("-- Synthetic experimentation seed bundle.\nPRAGMA foreign_keys = ON;\n")
        pkmap={"experiments":"experiment_id","variants":"variant_id","audience_members":"audience_member_id","assignments":"assignment_id","exposure_events":"exposure_id","conversion_events":"conversion_id","metric_definitions":"metric_id","guardrail_metrics":"guardrail_id","experiment_results":"result_id","ground_truth":"issue_id"}
        fkmap={"variants":[("experiment_id","experiments","experiment_id")],"audience_members":[("experiment_id","experiments","experiment_id")],"assignments":[("experiment_id","experiments","experiment_id"),("audience_member_id","audience_members","audience_member_id"),("variant_id","variants","variant_id")],"exposure_events":[("experiment_id","experiments","experiment_id"),("assignment_id","assignments","assignment_id"),("variant_id","variants","variant_id")],"conversion_events":[("experiment_id","experiments","experiment_id"),("assignment_id","assignments","assignment_id"),("variant_id","variants","variant_id")],"metric_definitions":[("experiment_id","experiments","experiment_id")],"guardrail_metrics":[("experiment_id","experiments","experiment_id"),("metric_id","metric_definitions","metric_id")],"experiment_results":[("experiment_id","experiments","experiment_id"),("variant_id","variants","variant_id"),("metric_id","metric_definitions","metric_id")],"ground_truth":[]}
        # Table order places all referenced parent rows before child rows; metric definitions precede results.
        for name,rows in data.items():
            fields=TABLES.get(name, ["issue_id","issue_type","entity","record_id","ground_truth","details"])
            defs=["%s TEXT%s"%(col," PRIMARY KEY" if col==pkmap[name] else "") for col in fields]
            defs += ["FOREIGN KEY (%s) REFERENCES %s(%s)"%(col,parent,parentcol) for col,parent,parentcol in fkmap.get(name,[])]
            f.write("CREATE TABLE %s (%s);\n"%(name,", ".join(defs)))
            cols=", ".join(fields)
            for row in rows:
                vals=[]
                for col in fields:
                    value=row.get(col)
                    vals.append("NULL" if value is None or value=="" else "'"+str(value).replace("'","''")+"'")
                f.write("INSERT INTO %s (%s) VALUES (%s);\n"%(name,cols,", ".join(vals)))
    summary=validate(data,scale,seed)
    (outdir/"validation_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (outdir/"source_manifest.json").write_text(json.dumps({"provenance":"fully synthetic; no external or personal data","generator":"generate_experiments.py","seed":seed,"requested_eligible_users":scale,"experiments":10,"scope":"CSV and JSON-derived portable SQL seed records","generated_at":"fixed-by-seed-and-synthetic-clock"},indent=2),encoding="utf-8")
    # Checksums exclude manifest and summary to keep the comparison stable and meaningful.
    checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(outdir.glob("*.csv"))}
    (outdir/"checksums.sha256.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    return summary

def validate(d, requested, seed):
    issues=[]; checks={}
    # Primary key uniqueness.
    pks={"experiments":"experiment_id","variants":"variant_id","audience_members":"audience_member_id","assignments":"assignment_id","exposure_events":"exposure_id","conversion_events":"conversion_id","metric_definitions":"metric_id","guardrail_metrics":"guardrail_id","experiment_results":"result_id"}
    for name,pk in pks.items():
        vals=[r[pk] for r in d[name]]; dup=len(vals)-len(set(vals)); checks[name+"_primary_key_unique"]=dup==0
        if dup: issues.append("%s has %d duplicate primary keys"%(name,dup))
    ids={name:{r[pks[name]] for r in d[name]} for name in pks}
    for r in d["variants"]:
        if r["experiment_id"] not in ids["experiments"]: issues.append("variant foreign key failure")
    for r in d["audience_members"]:
        if r["experiment_id"] not in ids["experiments"]: issues.append("audience experiment FK failure")
    for r in d["assignments"]:
        if r["experiment_id"] not in ids["experiments"] or r["audience_member_id"] not in ids["audience_members"] or r["variant_id"] not in ids["variants"]: issues.append("assignment FK failure: "+r["assignment_id"])
    for table in ("exposure_events","conversion_events"):
        for r in d[table]:
            if r["assignment_id"] not in ids["assignments"]: issues.append(table+" assignment FK failure: "+r["assignment_id"])
    for r in d["experiment_results"]:
        if r["variant_id"] not in ids["variants"] or r["metric_id"] not in ids["metric_definitions"]: issues.append("result FK failure: "+r["result_id"])
    # Distinguish intentional anomalies from unintended violations.
    checks["all_references_resolve"]=not any("FK failure" in i for i in issues)
    anomaly_types={r["issue_type"] for r in d["ground_truth"]}
    expected={"multiple_variant_assignment","exposure_before_assignment","outcome_window_inconsistent","sample_ratio_mismatch_ignored","metric_definition_changed_after_results"}
    checks["required_anomaly_coverage"]=expected.issubset(anomaly_types)
    checks["requested_audience_count"]=len(d["audience_members"])==requested
    checks["experiment_count"]=len(d["experiments"])==10
    checks["all_results_have_uncertainty"]=all(r["std_error"] is not None and r["ci95_low"] is not None and r["ci95_high"] is not None and r["p_value"] is not None for r in d["experiment_results"])
    checks["analysis_plan_traceability"]=all(bool(r["analysis_plan_id"]) and bool(r["metric_version"]) for r in d["experiment_results"])
    expmap={r["experiment_id"]:r for r in d["experiments"]}
    checks["experiment_lifecycle_and_dates"]=all(r["status"] in ("planned","running","analyzed") and r["start_at"]<r["end_at"] for r in d["experiments"])
    alloc=defaultdict(float); controls=Counter()
    for v in d["variants"]:
        alloc[v["experiment_id"]]+=float(v["allocation_ratio"])
        controls[v["experiment_id"]]+=1 if v["is_control"]=="true" else 0
    checks["allocation_and_control_reconcile"]=all(abs(alloc[e]-1.0)<1e-9 and controls[e]==1 for e in expmap)
    asgmap={r["assignment_id"]:r for r in d["assignments"]}
    audmap={r["audience_member_id"]:r for r in d["audience_members"]}
    assignment_consistent=all(r["audience_member_id"] in audmap and r["experiment_id"]==audmap[r["audience_member_id"]]["experiment_id"] and r["user_id"]==audmap[r["audience_member_id"]]["user_id"] and r["assigned_at"]>=audmap[r["audience_member_id"]]["eligible_at"] for r in d["assignments"])
    checks["assignment_audience_and_eligibility_consistent"]=assignment_consistent
    multiple=Counter((r["experiment_id"],r["user_id"]) for r in d["assignments"])
    multi_count=sum(1 for n in multiple.values() if n>1)
    checks["multiple_variant_exception_labelled"]=multi_count==1 and "multiple_variant_assignment" in anomaly_types
    preexp=[r for r in d["exposure_events"] if r["assignment_id"] in asgmap and r["exposed_at"]<asgmap[r["assignment_id"]]["assigned_at"]]
    checks["exposure_order_exception_labelled"]=len(preexp)==1 and "exposure_before_assignment" in anomaly_types
    outside=[]
    for r in d["conversion_events"]:
        a=asgmap.get(r["assignment_id"])
        if a and r["event_name"]=="purchase":
            age=(datetime.fromisoformat(r["occurred_at"].replace("Z","+00:00"))-datetime.fromisoformat(a["assigned_at"].replace("Z","+00:00"))).total_seconds()/86400.0
            if age>int(expmap[r["experiment_id"]]["conversion_window_days"]): outside.append(r)
    checks["out_of_window_exception_labelled"]=len(outside)==1 and "outcome_window_inconsistent" in anomaly_types
    # Event-to-assignment identity is checked independently; the out-of-order event remains a valid identity.
    checks["event_identity_matches_assignment"]=all(r["experiment_id"]==asgmap[r["assignment_id"]]["experiment_id"] and r["user_id"]==asgmap[r["assignment_id"]]["user_id"] and r["variant_id"]==asgmap[r["assignment_id"]]["variant_id"] for t in ("exposure_events","conversion_events") for r in d[t] if r["assignment_id"] in asgmap)
    metricmap={r["metric_id"]:r for r in d["metric_definitions"]}
    checks["result_metric_versions_match"]=all(r["metric_id"] in metricmap and int(r["metric_version"])==int(metricmap[r["metric_id"]]["version"]) for r in d["experiment_results"])
    post_change=[m for m in d["metric_definitions"] if int(m["version"])>1 and m["experiment_id"] in expmap and m["effective_from"]>max(r["analysis_at"] for r in d["experiment_results"] if r["experiment_id"]==m["experiment_id"])]
    checks["metric_change_after_results_labelled"]=len(post_change)==1 and "metric_definition_changed_after_results" in anomaly_types
    result_reconcile=True
    for r in d["experiment_results"]:
        if r["result_id"].endswith("-PRIMARY-v1"):
            eligible_asg=[a for a in d["assignments"] if a["experiment_id"]==r["experiment_id"] and a["variant_id"]==r["variant_id"] and not a["assignment_id"].endswith("-DUPVAR")]
            expected_n=len(eligible_asg); expected_k=set()
            aa={a["assignment_id"]:a for a in eligible_asg}
            for c in d["conversion_events"]:
                if c["assignment_id"] in aa and c["event_name"]=="purchase":
                    age=(datetime.fromisoformat(c["occurred_at"].replace("Z","+00:00"))-datetime.fromisoformat(aa[c["assignment_id"]]["assigned_at"].replace("Z","+00:00"))).total_seconds()/86400.0
                    if 0<=age<=int(expmap[r["experiment_id"]]["conversion_window_days"]): expected_k.add(c["assignment_id"])
            if int(r["n_assigned"])!=expected_n or int(r["denominator"])!=expected_n or int(r["numerator"])!=len(expected_k): result_reconcile=False
    checks["result_counts_reconcile_to_source"]=result_reconcile
    counts=Counter(r["decision"] for r in d["experiment_results"])
    return {"seed":seed,"requested_eligible_users":requested,"counts":{k:len(v) for k,v in d.items()},"checks":checks,"issues":issues,"overall_status":"PASS" if all(checks.values()) and not issues else "FAIL","decision_counts":dict(counts),"notes":["Injected anomaly records are expected and documented in ground_truth.csv.","The srm_ignored_anomaly decision is intentional and separately labelled.","Estimate is intention-to-treat; uncertainty uses normal approximation for a difference in proportions."]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--scale",type=int,default=50000,help="eligible audience members across ten experiments")
    ap.add_argument("--seed",type=int,default=SEED)
    ap.add_argument("--out",default="outputs/full")
    args=ap.parse_args()
    if args.scale<10: ap.error("scale must be at least 10")
    summary=build(args.scale,args.seed,Path(args.out))
    print(json.dumps(summary,indent=2))
    if summary["overall_status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
