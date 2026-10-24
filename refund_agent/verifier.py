
import re

NUMBER_RE = re.compile(
    r"(?<![A-Za-z-])(?:₹\s*)?\b\d+(?:\.\d+)?%?\b"
)


def _normalize_number(value):
    """Normalize a numeric token for exact comparison."""
    return value.replace("₹", "").replace("%", "").strip()


def _collect_numbers(value):
    """Collect complete numeric values from structured SQL results."""
    numbers = set()

    if isinstance(value, dict):
        for item in value.values():
            numbers.update(_collect_numbers(item))

    elif isinstance(value, (list, tuple)):
        for item in value:
            numbers.update(_collect_numbers(item))

    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        numbers.add(str(value))

    elif isinstance(value, str):
        for match in NUMBER_RE.findall(value):
            numbers.add(_normalize_number(match))

    return numbers


def verify_claims(claims, trace, docs, as_of_date="2026-10-22"):
    """
    Deterministic verifier:
    - SQL evidence must match a successful recorded query and hash.
    - Document quotations must be exact substrings.
    - Numeric tokens in fact claims must be supported by evidence.
    - Superseded policy evidence is flagged.
    """
    issues = []

    successful_sql = [
        entry["result"]
        for entry in trace
        if entry.get("tool") == "run_sql"
        and entry.get("status") == "ok"
        and entry.get("result")
    ]

    doc_by_id = {doc["id"]: doc for doc in docs}

    for i, claim in enumerate(claims):
        if claim.get("tag") != "fact":
            continue

        evidence = claim.get("evidence", {})
        claim_text = claim.get("text", "")

        if evidence.get("type") == "sql":
            matched_results = [
                result
                for result in successful_sql
                if result.get("sql") == evidence.get("sql")
                and result.get("sha256") == evidence.get("sha256")
            ]

            if not matched_results:
                issues.append({
                    "claim_index": i,
                    "reason": (
                        "SQL query/hash not found in successful tool trace"
                    ),
                })
                continue

            result = matched_results[0]
            supported_numbers = _collect_numbers(
                result.get("rows", [])
            )

            for number in NUMBER_RE.findall(claim_text):
                normalized = _normalize_number(number)

                if normalized not in supported_numbers:
                    issues.append({
                        "claim_index": i,
                        "reason": (
                            f"number {number!r} not re-derivable "
                            "from SQL rows"
                        ),
                    })

        elif evidence.get("type") == "document":
            document = doc_by_id.get(
                evidence.get("document_id")
            )
            quote = evidence.get("quote", "")

            if (
                not document
                or not quote
                or quote not in document.get("text", "")
            ):
                issues.append({
                    "claim_index": i,
                    "reason": (
                        "quoted span is not verbatim in cited document"
                    ),
                })
                continue

            for number in NUMBER_RE.findall(claim_text):
                normalized = _normalize_number(number)
                quote_numbers = {
                    _normalize_number(match)
                    for match in NUMBER_RE.findall(quote)
                }

                if normalized not in quote_numbers:
                    issues.append({
                        "claim_index": i,
                        "reason": (
                            f"number {number!r} is not supported "
                            "by quoted span"
                        ),
                    })

            if document.get("type") == "policy":
                effective_to = document.get("effective_to")

                if effective_to and as_of_date > effective_to:
                    issues.append({
                        "claim_index": i,
                        "reason": (
                            "claim leans on superseded policy; "
                            "must be flagged"
                        ),
                    })

        else:
            issues.append({
                "claim_index": i,
                "reason": "fact claim has no recognized evidence type",
            })

    return {
        "passed": not issues,
        "issues": issues,
    }
