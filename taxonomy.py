"""
Shared taxonomy helpers for the tech-news classifier.

HARD_CLASSES is the FIXED, human-curated top-level taxonomy used by the primary
Gemini classifier (see config.SYSTEM_PROMPT). It must not change implicitly.

normalize_classification() repairs label drift in the model output: Gemini
occasionally returns a different case ("other") or a shortened name
("IoT & Smart Sensors" instead of "AI, IoT & Smart Sensors"). Normalizing keeps
the dashboard from splitting one real category into several buckets. Unknown
labels are returned stripped but otherwise unchanged (never silently dropped).
"""

HARD_CLASSES = [
    "Sustainability & Environmental Impact",
    "Fabric Care & Textile Engineering",
    "Chemical Interaction & Smart Dosing",
    "Hygiene & Health Technologies",
    "AI, IoT & Smart Sensors",
    "Other",
]

# lowercase canonical name -> canonical name
_CANON = {c.lower(): c for c in HARD_CLASSES}

# Known model variants -> canonical hard class.
_ALIASES = {
    "iot & smart sensors": "AI, IoT & Smart Sensors",
    "ai, iot and smart sensors": "AI, IoT & Smart Sensors",
    "ai, iot & sensors": "AI, IoT & Smart Sensors",
}


def normalize_classification(label):
    """Map a raw Classification label onto a canonical HARD_CLASSES name.

    Returns the original (stripped) string if it is not a recognized hard class
    or alias, so genuinely unexpected labels survive for inspection.
    """
    if not isinstance(label, str):
        return label
    key = label.strip().lower()
    if key in _CANON:
        return _CANON[key]
    if key in _ALIASES:
        return _ALIASES[key]
    return label.strip()


def is_other(label):
    """True if the (normalized) label is the catch-all 'Other' class."""
    return normalize_classification(label) == "Other"
