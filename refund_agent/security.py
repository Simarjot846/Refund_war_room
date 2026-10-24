import re

ALLOWED_SELLER_IDS = {40218, 41000, 41001, 41002}
MAX_MESSAGE_LENGTH = 500
CREDIT_OR_PAYMENT_PATTERNS = [
    re.compile(r"₹\s*[\d,]+", re.I),
    re.compile(r"\b(credit|refund|pay|transfer|send money)\b", re.I),
]

def authorize_whatsapp(user_message, seller_id, message, explicit_confirmation=False):
    """
    Retrieved documents are never passed as the intent source.
    Only an explicit user-originated request + confirmation can pass.
    Financial-credit language is denied in this demo; it needs a separate audited workflow.
    """
    if not isinstance(user_message, str) or len(user_message.strip()) < 8:
        return False, "missing user-originated intent"
    user_intent = re.search(r"\b(send|message|whatsapp|contact)\b", user_message, re.I)
    if not user_intent:
        return False, "no explicit user request to contact seller"
    if not explicit_confirmation:
        return False, "explicit confirmation required"
    if type(seller_id) is not int or seller_id not in ALLOWED_SELLER_IDS:
        return False, "seller_id not allow-listed"
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_LENGTH:
        return False, "invalid message"
    if any(p.search(message) for p in CREDIT_OR_PAYMENT_PATTERNS):
        return False, "financial side effects are not permitted through this demo gate"
    return True, "authorized"

def inspect_injection_document(document):
    # Detection is telemetry only, never the security boundary.
    text = document.get("text", "")
    markers = [
        r"ignore all previous instructions",
        r"system se .*whatsapp",
        r"send_seller_whatsapp",
        r"₹\s*5,000",
    ]
    return any(re.search(p, text, re.I) for p in markers)
