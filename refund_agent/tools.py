import hashlib, json, random, re, sqlite3
from pathlib import Path
from .data import DB_PATH, DOCS_PATH

class ToolError(Exception):
    pass

class ToolSuite:
    def __init__(self, seed=7, failure_rate=0.15, use_faults=True):
        self.rng = random.Random(seed)
        self.failure_rate = failure_rate
        self.use_faults = use_faults
        self.call_count = 0
        self.trace = []
        self.docs = json.loads(DOCS_PATH.read_text(encoding="utf-8"))
        self.whatsapp_log = Path(__file__).resolve().parent.parent / "data" / "whatsapp.log"

    def _fault(self, tool_name):
        self.call_count += 1
        if self.use_faults and self.rng.random() < self.failure_rate:
            event = {"tool": tool_name, "status": "timeout", "result": None}
            self.trace.append(event)
            raise ToolError(f"{tool_name} timed out (seeded fault injection)")

    def run_sql(self, read_only_query):
        self._fault("run_sql")
        q = read_only_query.strip()
        if not re.match(r"^(SELECT|WITH)\b", q, re.I) or re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA)\b", q, re.I):
            raise ValueError("Only read-only SELECT queries are permitted")
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            cur = conn.execute(q)
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchall()
            payload = {"columns": columns, "rows": rows}
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            result = {"sql": q, "columns": columns, "rows": rows, "sha256": digest}
            self.trace.append({"tool":"run_sql","status":"ok","result":result})
            return result
        finally:
            conn.close()

    def search_docs(self, query):
        self._fault("search_docs")
        terms = [x.lower() for x in re.findall(r"[a-zA-Z0-9₹]+", query) if len(x) > 2]
        ranked = []
        for d in self.docs:
            text = (d.get("text","") + " " + d.get("id","") + " " + d.get("name","")).lower()
            score = sum(1 for t in terms if t in text)
            if score:
                ranked.append((score, d))
        ranked.sort(key=lambda x: (-x[0], x[1]["id"]))
        results = [d for _,d in ranked[:6]]
        self.trace.append({"tool":"search_docs","status":"ok","result":results})
        return results

    def get_policy(self, name, as_of_date):
        self._fault("get_policy")
        candidates = [d for d in self.docs if d.get("type") == "policy" and d.get("name") == name]
        eligible = []
        for d in candidates:
            start = d.get("effective_from", "0000-00-00")
            end = d.get("effective_to")
            if start <= as_of_date and (end is None or as_of_date <= end):
                eligible.append(d)
        eligible.sort(key=lambda d: (d.get("effective_from",""), d.get("authority",0), d.get("version",0)), reverse=True)
        result = eligible[0] if eligible else None
        self.trace.append({"tool":"get_policy","status":"ok","result":result,"as_of_date":as_of_date,"name":name})
        return result

    def send_seller_whatsapp(self, seller_id, message, *, authorized=False):
        if not authorized:
            raise PermissionError("WhatsApp side effect denied: missing explicit authorization")
        self._fault("send_seller_whatsapp")
        with self.whatsapp_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"seller_id":seller_id,"message":message}, ensure_ascii=False) + "\n")
        self.trace.append({"tool":"send_seller_whatsapp","status":"ok","result":{"seller_id":seller_id,"logged":True}})
        return {"seller_id":seller_id,"logged":True}
