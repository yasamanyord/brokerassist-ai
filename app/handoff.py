"""Evidence-only handoff packet. It is a local record, never a send operation."""

NEXT_STEPS = {
    "Finance": "Verify the transaction through the approved secure internal system; confirm the next permitted step.",
    "Compliance": "Review the identity, policy or advice-related issue through the approved compliance process.",
    "Security": "Investigate through approved security channels; verify identity before disclosing account information.",
    "Trading Operations": "Review the order reference and execution evidence through the approved dispute process.",
    "Technical Support": "Confirm the error, environment and steps attempted; investigate against approved troubleshooting guidance.",
    "Partnerships": "Review the request against the approved partnership process.",
    "Promotions": "Check eligibility and policy with the authorized promotions team.",
    "General Support": "Clarify the issue and confirm the current approved policy before responding.",
}


def packet(ticket, history):
    """Derive a read-only handoff from the finalized ticket and its audit evidence."""
    analysis = ticket.get("analysis")
    if ticket["status"] != "Escalated" or not analysis:
        raise ValueError("A finalized local escalation is required")
    event = next((row for row in history if row["action"] == "escalated"), None)
    if not event:
        raise ValueError("Escalation audit evidence is missing")
    team = analysis["team"]
    return {
        "ticket_id": ticket["id"],
        "issue": ticket["subject"],
        "category": analysis["category"],
        "priority": analysis["priority"],
        "recommended_team": team,
        "reason": analysis["reason"],
        "policy_ids": [source["id"] for source in analysis["citations"]],
        "risk_flags": [flag["code"] for flag in analysis.get("risk_signals", [])],
        "tool_attempts": [{"tool": call["tool"], "status": call["status"],
                           "simulated": bool(call.get("simulated"))}
                          for call in analysis.get("tool_calls", [])],
        "analysis_revision": ticket["analysis_revision"],
        "knowledge_revision": analysis.get("knowledge_revision"),
        "recorded_by": event["actor"],
        "recorded_at": event["created_at"],
        "next_step": NEXT_STEPS.get(team, NEXT_STEPS["General Support"]),
        "delivery_status": "local_only_not_sent",
        "customer_impact": "Operator must verify impact; no outcome or deadline confirmed.",
    }
