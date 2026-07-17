from __future__ import annotations

import re

_START_MARKERS = (
    "ARP Global Capital Limited is regulated by the DFSA",
    "All communications and services are directed at Professional Clients only",
)
_END_MARKER = "or any of its related parties or persons."

# If the closing sentence is missing, remove from start through a bounded window
# so mid-body disclaimers do not wipe the rest of a long email.
_FALLBACK_MAX_CHARS = 1200


def strip_regulatory_disclaimer(text: str) -> str:
    """Remove ARP regulatory disclaimer blocks wherever they appear in the body."""
    if not text:
        return text

    result = text
    while True:
        lower = result.lower()
        start_idx = -1
        for marker in _START_MARKERS:
            idx = lower.find(marker.lower())
            if idx != -1 and (start_idx == -1 or idx < start_idx):
                start_idx = idx
        if start_idx == -1:
            break

        end_search = result[start_idx:]
        end_rel = end_search.lower().find(_END_MARKER.lower())
        if end_rel != -1:
            end_idx = start_idx + end_rel + len(_END_MARKER)
        else:
            end_idx = min(start_idx + _FALLBACK_MAX_CHARS, len(result))

        result = (result[:start_idx] + result[end_idx:]).strip()
        result = re.sub(r"\n{3,}", "\n\n", result)

    return result
