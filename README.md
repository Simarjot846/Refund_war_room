# Bharat Bazaar — Refund War Room

A small, reproducible Python/SQLite assessment implementation. It demonstrates a bounded state machine, recorded evidence, deterministic verification, conflict handling, fault injection, and a separately gated side-effect tool.

## Requirements
- Python 3.10+
- No third-party packages required

## Run
```bash
python run_eval.py
```

The command generates a fresh synthetic dataset, runs the 12-question evaluation with the verifier enabled and disabled, and prints a comparison table. Data is synthetic and must not be presented as real Bharat Bazaar operational data.

## Run one question
```bash
python -m refund_agent.cli "Tier-3 pincodes mein refund requests kyun badh gaye?"
```

## Design
- `refund_agent/agent.py`: explicit PLAN → ACT → OBSERVE → VERIFY → ANSWER/ABSTAIN loop with a hard eight-tool-call budget.
- `refund_agent/tools.py`: read-only SQL, document search, date-aware policy lookup, fault-injection wrapper, and logged WhatsApp side-effect.
- `refund_agent/verifier.py`: deterministic number/quote/policy checks against recorded tool results.
- `refund_agent/security.py`: allow-list, argument validation, user-originated intent requirement, and default-deny gate for WhatsApp.
- `refund_agent/data.py`: reproducible synthetic database/documents with conflicting records, outdated policy, missing field, and two prompt-injection documents.
- `refund_agent/evaluation.py`: 12 cases and metrics for verifier ON/OFF.
- `architecture.mmd`: architecture diagram.

## Important limitations
This is a reference implementation for an assessment, not a production refund decision system. The demo uses a rule-based planner so results are deterministic and need no paid LLM/API key. A production deployment should add authentication, authorization, audit retention, PII controls, query allow-listing, database-level read-only credentials, observability, and human approval for financial side effects.

The synthetic data generator deliberately creates conflicting sources and injected documents. Search results are untrusted data. Injection detection is not the security boundary: the boundary is that retrieved content cannot trigger tools, and the side-effect tool is denied unless the original user message expresses a supported, explicit action.
# Refund_war_room
