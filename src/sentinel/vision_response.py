"""Shared, conservative danger response contract for all model adapters."""
import re

ALERT_FORMAT = (
    "\nEvaluate danger using the criteria in the configured prompt above. "
    "Do not add unrelated danger categories or override its explicit exclusions. "
    "Use yes only when visible evidence meets those criteria, no when it does not, "
    "and uncertain when the criteria or visual evidence are unclear. "
    "Choose ONE decision word: yes, no, or uncertain. Do not list alternatives or repeat the decision. "
    "Write exactly two lines using this template, replacing the brackets:\n"
    "DANGER: [decision]\nEVIDENCE: [one short sentence about what is visible]\n"
    "Do not infer hidden intent or identity. This output format is required even if the "
    "configured prompt requests a different format; its danger criteria still apply."
)


def parse_danger_response(text: str) -> tuple[str, str, str | None]:
    """Normalize known formatting variations, but never choose a side of conflicting decisions."""
    raw = text.strip()
    header = r"\bD?ANGER\s*:\s*(yes|no|uncertain)\b"
    matches = list(re.finditer(header, raw, re.IGNORECASE))
    if len(matches) != 1 or matches[0].start() != 0:
        return "uncertain", raw, "Missing, repeated or conflicting danger decision. Review the source."
    evidence = raw[matches[0].end():].lstrip(" \t\r\n.,;:-")
    evidence = re.sub(r"^EVIDENCE\s*:\s*", "", evidence, flags=re.IGNORECASE).strip()
    if (not evidence or re.search(r"\b(?:D?ANGER)\s*:", evidence, re.IGNORECASE)
            or re.fullmatch(r"[\s/|,]*(?:yes|no|uncertain)[.!\s]*", evidence, re.IGNORECASE)
            or evidence.startswith("[")):
        return "uncertain", raw, "Missing evidence or malformed danger decision. Review the source."
    return matches[0][1].lower(), evidence, None


def parse_danger_result(text: str) -> tuple[str, str]:
    status, description, _ = parse_danger_response(text)
    return status, description
