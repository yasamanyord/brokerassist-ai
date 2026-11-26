"""Run offline golden cases. These synthetic examples do not establish production quality."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.engine import analyze

def run():
    cases=json.loads((ROOT/"evaluations/golden_cases.json").read_text())
    results=[]
    for c in cases:
        a=analyze({"subject":"","message":c["message"],"customer":"Golden case","verified":False},allow_llm=False)
        category_ok=a["category"]==c["category"]
        escalation_ok=a["mandatory_escalation"]==c["escalate"]
        source_ok=bool(a["citations"])
        injection_ok=not c.get("injection") or a["injection_detected"]
        blocked_tool_ok=not any(t["status"]=="ok" for t in a["tool_calls"])
        results.append({"id":c["id"],"expected_category":c["category"],"actual_category":a["category"],"expected_escalation":c["escalate"],"actual_escalation":a["mandatory_escalation"],"category_ok":category_ok,"escalation_ok":escalation_ok,"source_ok":source_ok,"injection_ok":injection_ok,"blocked_tool_ok":blocked_tool_ok,"passed":all((category_ok,escalation_ok,source_ok,injection_ok,blocked_tool_ok))})
    n=len(results); critical=[r for r in results if r["expected_escalation"]]
    summary={"cases":n,"passed":sum(r["passed"] for r in results),"category_accuracy":round(100*sum(r["category_ok"] for r in results)/n,1),"escalation_accuracy":round(100*sum(r["escalation_ok"] for r in results)/n,1),"required_escalation_recall":round(100*sum(r["actual_escalation"] for r in critical)/len(critical),1),"cited_response_coverage":round(100*sum(r["source_ok"] for r in results)/n,1),"unauthorized_tool_successes":sum(not r["blocked_tool_ok"] for r in results),"failed_cases":[r for r in results if not r["passed"]]}
    return {"summary":summary,"results":results}

if __name__=="__main__":
    report=run()
    print(json.dumps(report["summary"],indent=2))
    (ROOT/"evaluations/results.json").write_text(json.dumps(report,indent=2)+"\n")
    sys.exit(0 if not report["summary"]["failed_cases"] else 1)
