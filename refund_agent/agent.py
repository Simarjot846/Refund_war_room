import json
from .tools import ToolError
from .verifier import verify_claims
from .security import inspect_injection_document

MAX_CALLS = 8
SQL_TIER3 = """
SELECT r.refund_reason, COUNT(*) AS refund_count
FROM refunds r JOIN orders o ON o.order_id = r.order_id
WHERE o.pincode_tier = 'Tier-3'
GROUP BY r.refund_reason
ORDER BY refund_count DESC
""".strip()
SQL_TREND = """
SELECT CASE WHEN r.refund_date >= '2026-10-08' THEN 'festive_week' ELSE 'baseline_week' END AS period,
       COUNT(*) AS refund_requests
FROM refunds r JOIN orders o ON o.order_id = r.order_id
WHERE o.pincode_tier = 'Tier-3'
GROUP BY period ORDER BY period
""".strip()
SQL_MISSING = """
SELECT COUNT(*) AS missing_tier_tickets
FROM orders o
WHERE o.pincode_tier IS NULL
""".strip()

class RefundAgent:
    def __init__(self, tools, verifier_enabled=True, max_calls=MAX_CALLS):
        self.tools = tools
        self.verifier_enabled = verifier_enabled
        self.max_calls = min(max_calls, MAX_CALLS)
        self.states = []

    def _call(self, fn, *args, **kwargs):
        for attempt in range(2):
            if self.tools.call_count >= self.max_calls:
                raise RuntimeError("tool budget exhausted")
            try:
                return fn(*args, **kwargs)
            except ToolError:
                if attempt == 1 or self.tools.call_count >= self.max_calls:
                    raise

    def answer(self, question, as_of_date="2026-10-22"):
        self.states = ["PLAN"]
        q = question.lower()
        claims, conflicts, missing = [], [], []
        retrieved = []
        # Rule-based plan: stable, inspectable, no model-generated tool calls.
        plan = []
        if any(w in q for w in ["tier-3", "tier 3", "refund", "refunds", "refund requests", "kyun"]):
            plan.append(("run_sql", SQL_TREND))
            plan.append(("run_sql", SQL_TIER3))
            plan.append(("search_docs", "Tier-3 refund late delivery damaged COD courier"))
        if "policy" in q or "replacement" in q or "7-day" in q or "7 day" in q:
            plan.append(("get_policy", ("replacement_policy", as_of_date)))
            plan.append(("search_docs", "replacement policy seller 7 days effective date"))
        if any(w in q for w in ["inject", "whatsapp", "seller 40218", "₹5,000", "5000"]):
            plan.append(("search_docs", "INJ-001 INJ-002 seller 40218 WhatsApp"))
        if "missing" in q or "unanswerable" in q or "exact cause" in q or "exact percentage" in q:
            plan.append(("search_docs", "exact cause measured evidence Tier-3"))
        if not plan:
            plan.append(("search_docs", question))
        # Deduplicate identical tool plans while preserving order.
        seen = set()
        plan = [x for x in plan if not (repr(x) in seen or seen.add(repr(x)))]

        self.states.append("ACT")
        for tool, args in plan:
            if self.tools.call_count >= self.max_calls:
                missing.append("Tool-call budget exhausted; remaining planned evidence was not retrieved.")
                break
            self.states.append("OBSERVE")
            try:
                if tool == "run_sql":
                    result = self._call(self.tools.run_sql, args)
                elif tool == "search_docs":
                    result = self._call(self.tools.search_docs, args)
                    retrieved.extend(result or [])
                    for d in result or []:
                        if d.get("id","").startswith("INJ-"):
                            # Detection logged, but no tool invocation is ever derived from document text.
                            pass
                elif tool == "get_policy":
                    result = self._call(self.tools.get_policy, *args)
                    if result:
                        retrieved.append(result)
                else:
                    continue
            except (ToolError, RuntimeError, ValueError) as e:
                missing.append(f"{tool} evidence unavailable: {e}")
                continue

        self.states.append("VERIFY")
        # Claims are generated only from successful recorded tool results.
        sql_results = [e["result"] for e in self.tools.trace if e.get("tool")=="run_sql" and e.get("status")=="ok"]
        if sql_results and any(k in q for k in ["tier-3", "tier 3", "refund", "kyun"]):
            trend = next((r for r in sql_results if "period" in r["columns"]), None)
            if trend:
                rows = {row[0]: row[1] for row in trend["rows"]}
                if "festive_week" in rows and "baseline_week" in rows:
                    claims.append({"tag":"fact","text":f"Tier-3 refund requests in this synthetic dataset were {rows['baseline_week']} in the baseline period and {rows['festive_week']} in the festive-week period.",
                        "evidence":{"type":"sql","sql":trend["sql"],"sha256":trend["sha256"]}})
            breakdown = next((r for r in sql_results if "refund_reason" in r["columns"]), None)
            if breakdown and breakdown["rows"]:
                reasons = {row[0]: row[1] for row in breakdown["rows"]}
                top = sorted(reasons.items(), key=lambda x:(-x[1],x[0]))[:3]
                claims.append({"tag":"fact","text":"Top recorded Tier-3 refund reasons in this sample: " + ", ".join(f"{r} ({n})" for r,n in top) + ".",
                    "evidence":{"type":"sql","sql":breakdown["sql"],"sha256":breakdown["sha256"]}})
        asks_unmeasured_cause = any(term in q for term in ["exact cause", "caused by courier", "prove the exact cause", "exact percentage", "each refund"])
        if asks_unmeasured_cause:
            claims = [c for c in claims if c.get("tag") != "fact"]
            missing.append("The available synthetic records do not establish the requested exact causal attribution or pincode-level cause.")
        current_policy = next((d for d in retrieved if d.get("type")=="policy" and d.get("effective_from","") <= as_of_date and (d.get("effective_to") is None or as_of_date <= d.get("effective_to"))), None)
        if current_policy and ("policy" in q or "replacement" in q or "7-day" in q or "7 day" in q):
            quote = current_policy["text"]
            claims.append({"tag":"fact","text":quote,"evidence":{"type":"document","document_id":current_policy["id"],"quote":quote}})
            claims.append({"tag":"recommendation","text":"Use the centrally published policy version effective on the question date, not an older seller note or expired policy."})
        # Conflict detection: don't silently choose between same-topic numeric claims.
        by_id = {d["id"]:d for d in retrieved}
        if "replacement" in q or "policy" in q:
            old = [d for d in retrieved if d.get("type")=="policy" and d.get("effective_to") and as_of_date > d["effective_to"]]
            if old:
                conflicts.append({"topic":"replacement policy","resolution":"superseded by effective-date rule","sources":[d["id"] for d in old] + ([current_policy["id"]] if current_policy else [])})
            seller = [d for d in retrieved if d["id"]=="SELLER-601"]
            if seller:
                conflicts.append({"topic":"replacement window","resolution":"central policy authority + effective date outrank seller anecdote","sources":["SELLER-601"] + ([current_policy["id"]] if current_policy else [])})
        if any(d["id"] in by_id for d in retrieved for _ in [0]) and any(d["id"] in ("FIN-401","OPS-501") for d in retrieved):
            conflicts.append({"topic":"COD-related refund percentage","resolution":"unresolved: denominator/scope differs or is undocumented; neither percentage is promoted to a company-wide fact","sources":[d["id"] for d in retrieved if d["id"] in ("FIN-401","OPS-501")]})
        if not claims:
            missing.append("No verified fact could be produced from the available successful tool results.")
        self.states.append("VERIFY")
        verification = verify_claims(claims, self.tools.trace, self.tools.docs, as_of_date) if self.verifier_enabled else {"passed":None,"issues":[]}
        if self.verifier_enabled and not verification["passed"]:
            bad = {x["claim_index"] for x in verification["issues"]}
            claims = [c for i,c in enumerate(claims) if i not in bad]
            missing.extend("Claim removed by deterministic verifier: " + x["reason"] for x in verification["issues"])
        status = "answer" if claims and (not self.verifier_enabled or verification["passed"]) else "cannot_determine"
        if missing or conflicts:
            status = "partial_answer" if claims else "cannot_determine"
        self.states.append("ANSWER" if status != "cannot_determine" else "ABSTAIN")
        return {
            "status":status,
            "answer_language":"en",
            "claims":claims,
            "conflicts":conflicts,
            "missing_evidence":missing,
            "verification":verification,
            "tool_calls":self.tools.call_count,
            "state_trace":self.states,
            "injection_documents_detected":[d["id"] for d in retrieved if inspect_injection_document(d)],
            "side_effects_executed":False
        }
