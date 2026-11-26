"""Deterministic safety boundaries independent of the retrieval ranking.

These English-focused rules are defense in depth, not a complete abuse detector.
No rule, model output, or customer statement grants account authorization.
"""
from __future__ import annotations
import re
import unicodedata

VERSION = "2.0"

def normalize(text: str) -> str:
    # Normalize Unicode punctuation and full-width text; remove zero-width format chars.
    text = unicodedata.normalize("NFKC",text).replace("’","'").replace("‘","'")
    return " ".join("".join(c for c in text if unicodedata.category(c)!="Cf").split()).lower()

def matches(pattern: str, text: str) -> bool:
    return bool(re.search(pattern,text,re.I))

# Priority is explicit: retrieval relevance cannot override costly failure categories.
RULES = (
    ("prompt_injection","Security",r"\b(disregard|forget|ignore)\b.{0,45}\b(instructions|policy|policies|rules|guardrails)\b|\bpretend (you are|to be)\b.{0,35}\b(admin|administrator|finance|compliance)\b|\brole\s*:\s*(system|developer)\b|\bdeveloper instructions\b|\b(show|print|leak)\b.{0,25}\b(system prompt|api key|internal prompt)\b"),
    ("security_or_privacy","Security",r"\b(hacked|compromised|unauthorized|stolen|fraud|another (user|customer)|someone else.s account|seed phrase|private key|otp|one.time (passcode|code)|2fa code|api key|password leak)\b|\b(reset|change|disable|bypass)\b.{0,35}\b(password|two.factor|2fa|authentication|account security)\b|\b(password|otp|api key|private key)\s*=\s*\[redacted\]"),
    ("identity_and_kyc","KYC",r"\b(kyc|identity verification|proof of address|passport|identity document|id document|verify my identity|government id|verification (rejected|failed|pending)|document rejected)\b"),
    ("withdrawal_or_payout","Withdrawal",r"\b(withdrawal|withdrawals|payout|payouts|cash out|withdraw (my|the|funds|money|\$|\d))\b"),
    ("deposit_or_refund","Deposit",r"\b(deposit|deposits|refund|refunded|chargeback|missing funds|credited|transaction reference)\b|\b(credit|add|reverse|modify|adjust|change)\b.{0,30}\b(my |the )?(balance|funds|payment|transaction)\b"),
    ("trade_execution_or_dispute","Trading disputes",r"\b(slippage|requote|trade dispute|order execution|order rejected|wrong price|position closed)\b|\b(execute|place|open|close|cancel|modify|adjust|change|reverse)\b.{0,30}\b(my |the )?(trade|position|order|stop loss|take profit)\b"),
    ("promotion_mutation","Bonus",r"\b(activate|approve|grant|credit|extend|apply|add|override)\b.{0,32}\b(my |the |a )?(bonus|promotion|promo credit)\b"),
    ("account_mutation","Accounts",r"\b(close|delete|unlock|suspend|reopen|disable|enable|transfer|modify)\b.{0,24}\b(my |the |a )?(client |trading )?account\b|\bchange\b.{0,18}\b(account email|registered email|email address)\b"),
)

def risk_signals(text: str) -> list[dict]:
    normalized=normalize(text)
    return [{"code":code,"category":category} for code,category,pattern in RULES if matches(pattern,normalized)]

# Explicit claims/requests that must not be presented as a completed action.
# These intentionally narrow high-signal patterns avoid penalizing safe negation.
DRAFT_RULES = (
    ("credential_request",r"\b(send|share|provide|give|tell|email|disclose|enter|submit)\b.{0,28}\b(your|the)\s+(password|trading password|otp|one.time (code|passcode)|2fa code|private key|seed phrase|api key)\b"),
    ("identity_document_in_chat",r"\b(send|share|email|upload|attach|provide)\b.{0,22}\b(your|the)\s+(passport|identity document|id document)\b.{0,25}\b(here|in this chat|by email|to this email)\b"),
    ("unauthorized_action_claim",r"\b(i|we)\s+(have\s+|just\s+)?(approved|processed|completed|refunded|credited|reversed|executed|closed|changed|reset|unlocked|activated)\b.{0,40}\b(your|the|my)\s+(deposit|withdrawal|refund|payout|funds|payment|balance|order|trade|position|password|account|bonus)\b"),
    ("misleading_completion_claim",r"\b(your|the)\s+(deposit|withdrawal|refund|payout|payment|funds|account|bonus)\s+(has been|have been|is now|are now|was)\s+(credited|approved|refunded|completed|paid|processed|unlocked|activated)\b"),
    ("guaranteed_outcome",r"\b(i|we)\s+guarantee\b.{0,60}\b(payment|payout|withdrawal|deposit|refund|return|profit|arrival|today|tomorrow)\b|\bguaranteed\s+(profit|returns|payment|payout)\b"),
    ("investment_instruction",r"\b(i recommend|we recommend|you should|you must)\s+(buy|sell|trade|invest in)\b"),
)

def unsafe_draft_reasons(text: str) -> list[str]:
    normalized=normalize(text)
    # Recognize common explicit safety warnings (e.g., "do not share your password").
    # Split on sentence boundaries; test each clause so a warning in one sentence
    # never suppresses a dangerous request in another.
    clauses=re.split(r"[.!?;\n]+|\b(?:but|however|instead)\b",normalized)
    results=[]
    for clause in clauses:
        for code,pattern in DRAFT_RULES:
            for match in re.finditer(pattern,clause,re.I):
                prefix=clause[max(0,match.start()-36):match.start()]
                if re.search(r"\b(?:do not|don't|never|cannot|can't|must not|should not|will not|won't|avoid)\s*$",prefix):
                    continue
                if code not in results: results.append(code)
    return results
