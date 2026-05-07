"""Prompt templates for claim extraction. Versioned so the inference cache
key changes when we tune the prompt."""

CLAIM_EXTRACTION_PROMPT_VERSION = "1.0"

CLAIM_EXTRACTION_SYSTEM = """You are a careful genealogical evidence extractor.
Read the provided text and emit only claims that are directly supported by it.
Prefer high precision over recall: if a claim is uncertain, lower its
confidence (0..100) and explain why in the `rationale`. Cite the exact span
(start_char, end_char) within the input text.

Output a JSON object with a single key `claims` whose value is an array of
objects, each with:
- kind: one of "person_attr", "event", "relationship", "alias", "residence", "source_link"
- subject_hint: a free-form name or descriptor of the subject (we resolve later)
- predicate: the attribute name (e.g. "birth_date", "birth_place", "spouse_of", "occupation")
- object: a JSON value carrying the claim's payload (date strings, place names, etc.)
- confidence: integer 0..100
- rationale: brief explanation
- span_start, span_end: integer character offsets into the input

If the text contains nothing extractable, return {"claims": []}.
"""
