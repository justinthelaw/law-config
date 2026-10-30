"""Produce an auditable paired report without imputing missing cost, quality or time."""
import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campaign as C
import environment as E
import judge as J

TOKENS=("inputTokens","cachedInputTokens","cacheWriteInputTokens","outputTokens","reasoningOutputTokens","totalTokens")
ROLES=J.ROLES
PAIRS=(("develop","control"),("develop","upstream"),("control","upstream"))


def usage(row):
    by_thread=row.get("usage",{})
    participants=set(row.get("threads",[]))|set(row.get("children",[]))|{row.get("root")}
    def terminal(thread):
        turns=row.get("turn_meters",{}).get(thread,{})
        return bool(turns) and all(m.get("status")=="completed" and m.get("message_seq",0)>0 and
            m.get("usage_seq",0)>=m["message_seq"] for m in turns.values())
    complete=(bool(by_thread) and row.get("state")=="completed" and participants<=by_thread.keys()
              and all(terminal(t) for t in participants))
    sums=dict.fromkeys(TOKENS,None)
    micro_usd=0
    measured=False
    for meter in by_thread.values():
        values={k:meter[k] for k in TOKENS if type(meter.get(k)) is int and meter[k]>=0}
        inp,cached,out=(values.get(k) for k in ("inputTokens","cachedInputTokens","outputTokens"))
        if (inp is not None and cached is not None and cached>inp) or (out is not None and
                values.get("reasoningOutputTokens",0)>out):
            raise ValueError("inconsistent provider token counters")
        complete &= len(values)==len(TOKENS)
        for k,v in values.items():
            sums[k]=(sums[k] or 0)+v
        # When cache attribution is missing, every known input could have been cached.
        if inp is not None and cached is not None:
            micro_usd+=(inp-cached)*2+cached*.1
        else:
            micro_usd+=(inp if inp is not None else cached or 0)*.1
        micro_usd+=(out if out is not None else values.get("reasoningOutputTokens",0))*10
        measured |= any(k in values for k in ("inputTokens","cachedInputTokens","outputTokens","reasoningOutputTokens"))
    usd=micro_usd/1e6 if measured else None
    return {"coverage":"complete" if complete else "lower bound" if by_thread else "unknown",
            "tokens":sums,"threads":len(by_thread),"usd_estimate":usd}


def weighted(scores):
    if any(scores[k] is None for k in J.AXES):
        return None
    return sum(J.AXES[k]*scores[k]/4 for k in J.AXES)


def blind(name,key):
    grades={role:[] for role in ROLES}
    assessors=[]
    root=C.run_dir(name)/"judges"/key
    originals = None
    for idx in range(3):
        d=root/str(idx)
        path=d/"judgment.json"
        if not path.is_file():
            continue
        seal=E.read(path)
        mapping=C.verify_receipt(seal["mapping"])
        native=C.verify_receipt(seal["native"])
        packet=C.verify_receipt(seal["packet"])
        if E.sha((E.STATE/seal["packet"]["path"]).parent/"judge-prompt.txt")!=packet["prompt_sha256"]:
            raise ValueError("ordered judge prompt changed")
        if mapping["labels"]!=J.mapping(E.read(C.run_dir(name)/"plan.json")["seed"],key,idx):
            raise ValueError("wrong position rotation")
        if originals is None:
            originals, _ = J.table_for(name,key)
        expected = {role:{"patch":hashlib.sha256(source[0]).hexdigest(),
                          "proposal":hashlib.sha256(source[1].encode()).hexdigest()}
                    for role,source in originals.items()}
        if mapping["raw_inputs"]!=expected:
            raise ValueError("judge scored a different proposal")
        data=seal["scores"]
        observations={label:originals[role][3] for label,role in mapping["labels"].items()}
        if mapping["proposal_observations"]!=observations:
            raise ValueError("proposal availability changed")
        J.validate(data,mapping["task_sha256"],observations)
        for label,role in mapping["labels"].items():
            grades[role].append({"rotation":idx,"label":label,**data["submissions"][label]})
        assessors.append({"rotation":idx,"usage":usage(native),"wall":native.get("wall_seconds"),
                          "assessed_unix":seal["assessed_unix"],"limitations":data["limitations"]})
    summary={}
    for role,rows in grades.items():
        anchors={}
        for axis in J.AXES:
            scores=[r["scores"][axis] for r in rows if r["scores"][axis] is not None]
            anchors[axis]=statistics.median(scores) if len(scores)>=2 else None
        totals=[x for r in rows if (x:=weighted(r["scores"])) is not None]
        summary[role]={"axes":anchors,"score":weighted(anchors),
                       "range":[min(totals),max(totals)] if totals else None,"judgments":rows,
                       "flags":[{"rotation":r["rotation"],"flag":f} for r in rows for f in r["flags"]]}
    # Include failed assessment attempts in the separate evaluator budget.
    costs=[usage(E.read(p)) for p in root.glob("*/*/native.json")]
    return summary,assessors,costs


def pair_quality(left,right,items):
    a,b=items[left],items[right]
    if a["status"] in ("unavailable","pending") or b["status"] in ("unavailable","pending"):
        return {"verdict":"unresolved","reason":"missing or disputed evidence"}
    if a["status"]!=b["status"]:
        return {"verdict":left if a["status"]=="ready" else right,"reason":"hard gates"}
    if a["status"]!="ready":
        return {"verdict":"both failed","reason":"hard gates"}
    x,y=a["review"],b["review"]
    if x["score"] is None or y["score"] is None:
        return {"verdict":"unresolved","reason":"missing scores"}
    votes=[]
    differences=[]
    for i,j in zip(x["judgments"],y["judgments"]):
        s,t=weighted(i["scores"]),weighted(j["scores"])
        if s is not None and t is not None:
            differences.append(s-t)
            votes.append(left if s>t else right if t>s else "tie")
    if len(differences)!=3:
        return {"verdict":"unresolved","reason":"missing paired rotations"}
    delta=statistics.median(differences)
    direction=left if delta>=5 else right if delta<=-5 else "tie"
    agrees=(sum(abs(d)<5 for d in differences)>=2 if direction=="tie" else votes.count(direction)>=2)
    resolved=direction if agrees else "unresolved"
    return {"verdict":resolved,"reason":"blinded rubric","score_delta":delta,"votes":votes,
            "order_sensitive":len(set(votes))>1}


def goal_win(row):
    a, b = row["develop"], row["control"]
    return (a["status"] == "ready" and all(r["state"] == "completed" and
            r["coverage"] == "complete" and r["usd_estimate"] is not None and
            r.get("proposal_sha256") not in (None, hashlib.sha256(b"").hexdigest()) for r in (a, b))
            and {j["rotation"] for j in row["assessors"]} == {0, 1, 2}
            and row["pairs"]["develop_control"]["verdict"] == "develop"
            and a["usd_estimate"] <= b["usd_estimate"])


def case_row(name,c):
    key=c["id"]
    plan=E.read(C.run_dir(name)/"plan.json")
    reference=plan["references"][key]
    C.check_case(c,plan,deps=False)
    summaries,assessors,evaluator_cost=blind(name,key)
    path=C.run_dir(name)/"adjudications"/(key+".json")
    rulings=E.read(path) if path.is_file() else {}
    result={}
    for role in ROLES:
        if role=="upstream":
            grade=C.verified_grade(reference["gold_grade"])
            row={"state":"merged"}
            executable=grade.get("applied",False) and grade["replayed_tree"]==grade["target_tree"]
        else:
            row=C.read_attempt(name,key,role)
            grade=C.verified_grade(row["grade"]) if row.get("grade") else {}
            executable=(row["state"]=="completed" and bool(grade) and grade.get("applied",False)
                        and row.get("final_phase")=="final_answer" and C.complete_proposal(row.get("final",""))
                        and row.get("wall_seconds",float("inf"))<=plan["references"][key]["deadline_seconds"])
        exits={key:s["exit"] for key,s in grade.get("stages",{}).items()}
        mandatory={"build","native","contract","preserve"}|({"independent"} if c.get("independent") else set())
        gates=executable and set(exits)>=mandatory and all(exits[k]==0 for k in mandatory)
        issue=rulings.get(role,{})
        if issue and (issue.get("resolution") not in ("confirmed","cleared") or
                      not isinstance(issue.get("evidence"),str) or not issue["evidence"].strip()):
            raise ValueError("unsubstantiated integrity ruling")
        status=("unavailable" if row["state"] in {"unreleased","blocked","interrupted"} else
                "failed" if not gates or issue.get("resolution")=="confirmed" else
                "pending" if len(assessors)<3 or (summaries[role]["flags"] and not issue) else "ready")
        result[role]={"state":row["state"],"status":status,"executable_pass":gates,"stages":exits,
                      "grade_receipt":reference["gold_grade"] if role=="upstream" else row.get("grade"),
                      "review":summaries[role],"adjudication":issue}
        if role!="upstream":
            result[role].update(usage(row))
            result[role].update({k:row.get(k) for k in ("wall_seconds","proposal_wall_seconds","end_to_end_seconds",
                "setup_seconds","grading_seconds","captured_unix","start_unix","patch_sha256","proposal_sha256","error")})
    result["pairs"]={a+"_"+b:pair_quality(a,b,result) for a,b in PAIRS}
    result.update(case=key,repo=c["repo"],pr=c["pr"],split=c["split"],stratum=c["stratum"],
                  language=c["language"],domain=c["domain"],base_files=c["base_files"],base_bytes=c["base_bytes"],
                  pr_delta=c["delta"],first_commit=c["first_commit"],assessors=assessors,
                  authorship=c["authorship"],base_grade_receipt=reference["base_grade"],
                  deadline_seconds=reference["deadline_seconds"],first_arm=plan["order"][key][0],
                  upstream_observed_at=E.upstream(key)["observed_at"],
                  evaluator_cost=evaluator_cost,pr_open_to_merge_seconds=(datetime.fromisoformat(c["merged"].replace("Z","+00:00"))-
                  datetime.fromisoformat(c["opened"].replace("Z","+00:00"))).total_seconds())
    return result


def bootstrap(pairs,fn,seed=20261028):
    if len(pairs)<2:
        return None
    rng=random.Random(seed)
    draws=sorted(fn(rng.choices(pairs,k=len(pairs))) for _ in range(5000))
    return [draws[125],draws[4874]]


def group(rows):
    def costs(rows,field):
        return [[c["control"][field],c["develop"][field]] for c in rows
                if all(c[x][field] is not None and
                    (c[x]["coverage"]=="complete" if field=="usd_estimate" else c[x]["state"]=="completed")
                    for x in ROLES[:2])]
    totals={}
    for field in ("usd_estimate","proposal_wall_seconds","wall_seconds","end_to_end_seconds"):
        pairs=costs(rows,field)
        if pairs:
            ratio=lambda p:sum(y for x,y in p)/sum(x for x,y in p)
            totals[field]={"pairs":len(pairs),"pure_sum":sum(x for x,y in pairs),"develop_sum":sum(y for x,y in pairs),
                "ratio":ratio(pairs),"median_pair_ratio":statistics.median(y/x for x,y in pairs if x),
                "ratio_interval":bootstrap(pairs,ratio)}
    scores=[[r["control"]["review"]["score"],r["develop"]["review"]["score"]] for r in rows
            if len(r["assessors"])==3 and r["control"]["review"]["score"] is not None
            and r["develop"]["review"]["score"] is not None]
    if scores:
        f=lambda p:statistics.mean(y-x for x,y in p)
        totals["quality_delta"]={"pairs":len(scores),"mean":f(scores),"interval":bootstrap(scores,f)}
    counts={x:{k:sum(c[x]["status"]==k for c in rows) for k in ("ready","failed","pending","unavailable")} for x in ROLES}
    judgements={}
    for a,b in PAIRS:
        key=a+"_"+b;categories=(a,b,"tie","unresolved","both failed")
        judgements[key]={v:sum(c["pairs"][key]["verdict"]==v for c in rows) for v in categories}
    simultaneous=[c["case"] for c in rows if all(c[x]["coverage"]=="complete" for x in ROLES[:2])
                  and c["pairs"]["develop_control"]["verdict"] in {"develop","tie"}
                  and c["develop"]["status"]=="ready" and c["develop"]["usd_estimate"]<c["control"]["usd_estimate"]
                  and c["develop"]["proposal_wall_seconds"]<c["control"]["proposal_wall_seconds"]]
    observed={}
    for role in ROLES[:2]:
        entries=[r[role] for r in rows]
        observed[role]={"usd_estimate":sum(e["usd_estimate"] or 0 for e in entries),
                        "usd_observations":sum(e["usd_estimate"] is not None for e in entries),
                        "complete":sum(e["coverage"]=="complete" for e in entries),
                        "timed_attempts":sum(e["proposal_wall_seconds"] is not None for e in entries),
                        "observed_proposal_wall_seconds":sum(e["proposal_wall_seconds"] or 0 for e in entries),
                        "tokens":{k:sum(e["tokens"][k] or 0 for e in entries) for k in TOKENS}}
    return {"n":len(rows),"status_counts":counts,"paired":totals,"observed_by_arm":observed,
            "preferences":judgements,"simultaneous":simultaneous}


def seconds(value):
    if value is None:return "—"
    m,s=divmod(round(value),60)
    return f"{m}m {s:02}s"


def decimal(val,digits=1):
    return "—" if val is None else f"{val:.{digits}f}"


def report(name):
    plan=C.plan_for(name)
    rows=[case_row(name,c) for c in E.CASES.values()]
    groups={k:group([q for q in rows if k=="all" or q["split"]==k or q["stratum"]==k])
            for k in ("all","tuning","confirmation","external","owner-maintenance")}
    all_cost=[s for r in rows for s in r["evaluator_cost"]]
    endpoints=[(x["start_unix"],x["captured_unix"]) for r in rows for x in (r["control"],r["develop"])
               if x["start_unix"] is not None and x["captured_unix"] is not None]
    metrics={"plan_sha256":E.sha(C.run_dir(name)/"plan.json"),"groups":groups,"cases":rows,
             "evaluator":{"attempts":len(all_cost),"observed_usd":sum(s["usd_estimate"] or 0 for s in all_cost),
                          "complete_receipts":sum(s["coverage"]=="complete" for s in all_cost)},
             "campaign_submission_span_seconds":max(y for x,y in endpoints)-min(x for x,y in endpoints) if endpoints else None}
    native_ends=[E.read(p)["assessment_finished_unix"] for p in (C.run_dir(name)/"judges").glob("*/*/*/native.json")]
    judge_ends=[a["assessed_unix"] for r in rows for a in r["assessors"]]
    arm_ends=[x["start_unix"]+x["end_to_end_seconds"] for r in rows for x in (r["control"],r["develop"])
              if x["start_unix"] is not None and x["end_to_end_seconds"] is not None]
    ends=native_ends+judge_ends+arm_ends
    metrics["campaign_elapsed_through_last_measurement_seconds"]=max(ends)-plan["frozen_unix"] if ends else None
    dest=C.run_dir(name)/"report";dest.mkdir(exist_ok=True)
    (dest/"results.json").write_text(json.dumps(metrics,indent=2)+"\n")
    with (dest/"cases.csv").open("w",newline="") as handle:
        writer=csv.writer(handle)
        writer.writerow(["repo","pr","split","role","state","status","build","native","contract","preserve","independent",
            "rubric_score","contract_anchor","tests_anchor","design_anchor","proposal_anchor","usd_estimate","token_coverage",*TOKENS,
            "prompt_wall_s","checkout_to_proposal_s","grading_s","through_grading_s","pr_open_to_merge_s"])
        for r in rows:
            for role in ROLES:
                v=r[role];writer.writerow([r["repo"],r["pr"],r["split"],role,v["state"],v["status"],
                    *(v["stages"].get(k) for k in ("build","native","contract","preserve","independent")),v["review"]["score"],
                    *(v["review"]["axes"][k] for k in J.AXES),v.get("usd_estimate"),v.get("coverage"),
                    *(v.get("tokens",{}).get(k) for k in TOKENS),v.get("wall_seconds"),v.get("proposal_wall_seconds"),
                    v.get("grading_seconds"),v.get("end_to_end_seconds"),r["pr_open_to_merge_seconds"] if role=="upstream" else None])
    lines=["# Develop and pure Codex across twenty repositories","",
           "One fresh proposal per arm and repository. The comparison uses the same model, effort, starting tree, "
           "verification commands and deadline within each pair. The merged submission is graded alongside the two agents.","",
           "| Group | Ready pure / Develop / merged | Cost pure / Develop | Proposal wall pure / Develop | Cost / wall pairs |",
           "| --- | ---: | ---: | ---: | ---: |"]
    for k,g in groups.items():
        u=g["paired"].get("usd_estimate",{});w=g["paired"].get("proposal_wall_seconds",{})
        lines.append(f"| {k} ({g['n']}) | "+ " / ".join(str(g["status_counts"][x]["ready"]) for x in ROLES)+
            f" | ${decimal(u.get('pure_sum'),3)} / ${decimal(u.get('develop_sum'),3)} | {seconds(w.get('pure_sum'))} / {seconds(w.get('develop_sum'))} | {u.get('pairs',0)} / {w.get('pairs',0)} |")
    lines+=["","## Per repository","","P is pure Codex, D is Develop and M is the merge. Scores are on a 0–100 scale. "
            "A failed gate takes precedence. Missing values are shown as a dash. USD is a Standard rate-card estimate.","",
            "| Merged PR | Split | Judges | Readiness P / D / M | Score P / D / M | USD P / D | Proposal wall P / D | D vs P |",
            "| --- | --- | ---: | --- | ---: | ---: | --- | --- |"]
    for r in rows:
        links=f"[{r['repo']} #{r['pr']}](https://github.com/{r['repo']}/pull/{r['pr']})"
        lines.append(f"| {links} | {r['split']} | {len(r['assessors'])}/3 | "+" / ".join(r[x]["status"] for x in ROLES)+" | "+
                     " / ".join(decimal(r[x]["review"]["score"]) for x in ROLES)+" | "+
                     " / ".join(decimal(r[x]["usd_estimate"],3) for x in ROLES[:2])+" | "+
                     " / ".join(seconds(r[x]["proposal_wall_seconds"]) for x in ROLES[:2])+
                     " | "+r["pairs"]["develop_control"]["verdict"]+" |")
    lines+=["","## Measurement","",
        "Proposal wall runs from before checkout and profile setup to the frozen patch and final PR message. "
        "Prompt-to-terminal and time through independent grading are separate CSV columns. "
        "Partial usage is a lower bound. Aggregate costs use fully metered pairs. Wall comparisons use pairs with two completed, timed proposals. "
        "The JSON also gives observed totals including failures, freeze-to-last-assessment elapsed time, paired repository bootstrap intervals, preference reversals, individual anchors, gate log receipts and separate evaluator spend.","",
        "The executable gates cover selected paths. Three fresh plugin-free GPT-6.1 Sol Medium judges rotate each patch through each position. "
        "They see normalized PR text and executable evidence. Authorship clues and shared-model preferences can survive masking. "
        "This purposive sample, one attempt per repository, does not estimate the performance of every future PR. The human PR record measures open-to-merge time only.","",
        "[Machine-readable results](results.json) · [Per-submission CSV](cases.csv) · [Frozen plan](../plan.json)"]
    (dest/"comparison.md").write_text("\n".join(lines)+"\n")
    return metrics


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("name");args=p.parse_args()
    C.controller.activate();m=report(args.name)
    print(json.dumps(m["groups"]["all"],indent=2))
