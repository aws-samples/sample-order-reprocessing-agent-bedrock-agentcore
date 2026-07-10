"""
Bedrock Guardrails configuration — scoped to ReprocessOrder's input only
(BR-20), since it is the one tool that mutates state and submits data
downstream. Other 5 tools are read-only or purely-additive (ticket creation)
and are not intercepted.

Per business-rules.md BR-20, nfr-requirements.md's Security section.
"""

from __future__ import annotations

GUARDRAIL_CONFIG = {
    "name": "ora-reprocess-order-guardrail",
    "description": "Prevents the agent from submitting invalid, hallucinated, or "
                    "out-of-policy field values via ReprocessOrder.",
    "scoped_to_tool": "ReprocessOrder",  # applied only at this tool's invocation boundary
    "content_policy": {
        # Blocks obviously malformed/placeholder values that would indicate the
        # agent fabricated data rather than using a genuine FetchMissingData result.
        "denied_patterns": [
            r"^\s*$",              # empty/whitespace-only values
            r"^(?i)(unknown|n/a|null|none|placeholder|todo|xxx)$",  # obvious placeholders
            r"^(?i)test[-_]?data$",  # test/fake data markers
        ]
    },
    "word_policy": {
        "denied_words": ["fabricated", "guessed", "assumed value", "made up"],
    },
    "validation_rule": (
        "Every field in `updated_fields` passed to ReprocessOrder MUST correspond "
        "to a value previously returned by a FetchMissingData call within the same "
        "session — the agent must not invent, guess, or assume a field value."
    ),
}
