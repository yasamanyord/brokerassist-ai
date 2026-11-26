"""Manual synthetic-only Zendesk GET + local deduplication test.

No live customer data shall be used. Report contains checks only, no ticket text.
"""
import argparse, json, os, tempfile
from pathlib import Path
from unittest.mock import patch
from app import store
from app.engine import analyze
from app.integrations import zendesk

EXPECTED_SUBJECT="BrokerAssist synthetic MT5 test"
EXPECTED_MESSAGE="SYNTHETIC: MT5 displays Invalid Account. How do I select the correct trading server?"
ROOT=Path(__file__).resolve().parents[1]

def probe(ticket_id):
    # Read one specified ticket only. Do not import arbitrary CRM content into CI.
    remote=zendesk.fetch_ticket(ticket_id)
    if remote.get("subject")!=EXPECTED_SUBJECT or remote.get("description","").strip()!=EXPECTED_MESSAGE:
        raise ValueError("Ticket is not the exact documented synthetic fixture")
    payload=zendesk.normalize(remote)
    with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{"BROKERASSIST_DB":temp+"/crm.db"}):
        store.initialize()
        one,first_duplicate=store.intake(**payload)
        two,second_duplicate=store.intake(**payload)
        a=analyze(one,allow_llm=False)
        checks={"first_import":not first_duplicate,"duplicate_blocked":second_duplicate and one["id"]==two["id"],
                "crm_channel":one["channel"]=="CRM","no_self_verification":not one["verified"],
                "expected_category":a["category"]=="MT5","expected_policy":a["citations"][0]["id"]=="KB-001",
                "requires_operator_review":a["decision"]=="Review","no_model_call":a["mode"]=="offline policy draft"}
    return {"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,
            "note":"Exact synthetic sandbox fixture, read-only CRM GET; no ticket content or credentials in report."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticket-id",type=int,required=True)
    p.add_argument("--confirm-synthetic-data",action="store_true")
    p.add_argument("--output",type=Path,default=ROOT/"runtime/crm_probe.json")
    args=p.parse_args()
    if not args.confirm_synthetic_data or os.getenv("ALLOW_ZENDESK_SANDBOX")!="yes":
        p.error("Explicit synthetic sandbox confirmation required")
    try: result=probe(args.ticket_id)
    except Exception:
        result={"status":"FAIL","note":"Sandbox lookup or exact synthetic fixture validation failed; inspect configuration privately."}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
