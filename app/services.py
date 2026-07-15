import os
import re
import json
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

MIN_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.6"))

# ── Disable unwanted foreign recognizers (UK/US specific) ────────────────────
# These cause Indian phone numbers to show as <UK_NHS>, US numbers to override etc.
RECOGNIZERS_TO_REMOVE = [
    "UsBankRecognizer", "UsPassportRecognizer", "UsSsnRecognizer",
    "UsItinRecognizer", "UsLicenseRecognizer", "UsNpiRecognizer",
    "NhsRecognizer",  # UK NHS — was tagging Indian phone numbers as <UK_NHS>
    "AuAbnRecognizer", "AuAcnRecognizer", "AuTfnRecognizer", "AuMedicareRecognizer",
    "EsNifRecognizer", "InPanRecognizer",  # Presidio's built-in PAN (less accurate than ours)
]
for name in RECOGNIZERS_TO_REMOVE:
    try:
        recognizer = analyzer.registry.get_recognizer(name)
        analyzer.registry.remove_recognizer(name)
    except Exception:
        pass  # Already absent — no problem

# ── Money ─────────────────────────────────────────────────────────────────────
# Fix: Indian comma format Rs. 2,75,000 — groups can be 1-3 digits after first group
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="MONEY",
    patterns=[Pattern(
        name="money_pattern",
        regex=(
            r"(?:\$|Rs\.?\s?|₹|£|€)\s?\d+(?:,\d{1,3})*(?:\.\d{2})?"  # ₹/Rs. prefix
            r"|\b\d+(?:,\d{1,3})*(?:\.\d{2})?\s?(?:USD|INR|dollars?|rupees?|EUR|GBP)\b"  # suffix
        ),
        score=0.88
    )]
))

# ── Salary ────────────────────────────────────────────────────────────────────
# Negative lookahead (?![-/]) prevents matching IDs like EMP-2026-1042
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="SALARY",
    patterns=[Pattern(
        name="salary_pattern",
        regex=r"\b(?:salary|earns?|earning|compensation|package|income|pay|wage|wages)\b(?:\s+\w+){0,3}?\s+(?:\$|Rs\.?|₹)?\s?(\d+(?:,\d{1,3})*(?:\.\d{2})?)\b(?![-/])",
        score=0.9
    )]
))

# ── Indian Phone ──────────────────────────────────────────────────────────────
# score=0.95 beats Presidio's DATE_TIME and UK_NHS misclassifications
# Must be registered BEFORE bank account to ensure phone wins on overlap
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="PHONE_NUMBER",
    patterns=[Pattern(
        name="indian_phone_pattern",
        regex=r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b|\b[6-9]\d{9}\b",
        score=0.95
    )]
))

# ── Employee ID ───────────────────────────────────────────────────────────────
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="EMPLOYEE_ID",
    patterns=[Pattern(
        name="employee_id_pattern",
        regex=r"\bEMP[-/]?\d{2,6}[-/]?\d{0,6}\b",
        score=0.92
    )],
    context=["employee", "emp", "staff", "id"]
))

# ── Student ID ────────────────────────────────────────────────────────────────
# Two patterns:
#   1. Alphanumeric: MBMCS23045 (letters + digits)
#   2. Pure numeric: 2343546 — needs context words "student id" to avoid false positives
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="STUDENT_ID",
    patterns=[
        Pattern(name="student_id_alpha", regex=r"\b[A-Z]{2,8}\d{4,8}\b", score=0.80),
        Pattern(name="student_id_numeric", regex=r"\b\d{5,10}\b",          score=0.65),
    ],
    context=["student", "roll", "enrollment", "id", "student id", "roll no", "roll number"]
))

# ── Credit Card ───────────────────────────────────────────────────────────────
# Spaced 16-digit: 4111 1111 1111 1111
# score=0.95 — must win over BANK_ACCOUNT for the same number
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="CREDIT_CARD",
    patterns=[Pattern(
        name="credit_card_pattern",
        regex=r"\b(?:\d{4}[\s-]){3}\d{4}\b",
        score=0.95
    )],
    context=["credit", "card", "visa", "mastercard", "debit"]
))

# ── Address (full postal address) ─────────────────────────────────────────────
# Matches full Indian address lines: "Flat 18B, Lotus Residency, Sector 14, Kota, Rajasthan"
# Pattern: starts with a door/flat/plot number or building name, ends with a city/state
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="ADDRESS",
    patterns=[Pattern(
        name="indian_address_pattern",
        regex=(
            r"\b(?:Flat|House|Plot|Door|H\.?No\.?|Block|Sector|Survey|S\.?No\.?|Room|Floor|Wing)[\s.#-]*"
            r"[\w/,-]+(?:[,\s]+[\w\s/.-]+){2,8}"
            r"(?:[,\s]+(?:Delhi|Mumbai|Chennai|Bangalore|Bengaluru|Hyderabad|Kolkata|Pune|Ahmedabad|Jaipur|Kota|Jodhpur|Udaipur|Lucknow|Kanpur|Nagpur|Indore|Bhopal|Patna|Surat|Vadodara|Rajkot|Coimbatore|Visakhapatnam|Agra|Nashik|Noida|Gurgaon|Gurugram|Faridabad|Chandigarh|Dehradun|Guwahati|Ranchi|Bhubaneswar|Thiruvananthapuram|Mysuru|Mangaluru))"
            r"(?:[,\s]+(?:Rajasthan|Maharashtra|Karnataka|Tamil Nadu|Uttar Pradesh|West Bengal|Gujarat|Telangana|Andhra Pradesh|Madhya Pradesh|Bihar|Odisha|Kerala|Punjab|Haryana|Uttarakhand|Jharkhand|Assam|Himachal Pradesh|Goa|Delhi|NCR))?"
        ),
        score=0.82
    )],
    context=["address", "flat", "house", "plot", "street", "road", "nagar", "colony", "sector", "near", "lane"]
))

# ── Indian PII ────────────────────────────────────────────────────────────────
INDIAN_PII = {
    # Aadhaar: spaced (1234 5678 9012) or unspaced 12-digit
    # score=0.75 with context so random numbers don't get flagged
    "AADHAAR":        (r"\b\d{4}\s\d{4}\s\d{4}\b|\b\d{12}\b",                    0.75,
                       ["aadhaar", "aadhar", "uid", "uidai", "aadhar number", "aadhaar number"]),
    "PAN":            (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",                              0.90, None),
    "PASSPORT":       (r"\b[A-Z][0-9]{7}\b",                                       0.85, None),
    "DRIVING_LICENSE":(r"\b[A-Z]{2}[0-9]{2}\s?[0-9]{11}\b",                      0.85, None),
    "VEHICLE_REG":    (r"\b[A-Z]{2}[0-9]{2}\s?[A-Z]{1,2}\s?[0-9]{4}\b",         0.85, None),
    "IFSC":           (r"\b[A-Z]{4}0[A-Z0-9]{6}\b",                               0.90, None),
    "UPI":            (r"\b[a-zA-Z0-9_.-]+@[a-zA-Z0-9_-]+\b",                    0.85, None),
    "GSTIN":          (r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",  0.90, None),
    "VOTER_ID":       (r"\b[A-Z]{3}[0-9]{7}\b",                                    0.85, None),
    "PIN_CODE":       (r"\b[1-9][0-9]{5}\b",                                        0.75, None),
    # BANK_ACCOUNT score=0.96 so it wins over PHONE_NUMBER for 9-18 digit numbers
    # but context words are still required to avoid false positives on random numbers
    "BANK_ACCOUNT":   (r"\b[0-9]{9,18}\b",                                         0.96,
                       ["account", "acc", "bank", "savings", "current", "a/c"]),
}

for entity, (regex, score, context) in INDIAN_PII.items():
    kwargs = dict(
        supported_entity=entity,
        patterns=[Pattern(name=f"{entity.lower()}_pattern", regex=regex, score=score)]
    )
    if context:
        kwargs["context"] = context
    analyzer.registry.add_recognizer(PatternRecognizer(**kwargs))

# ── Groq client ───────────────────────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Cache: (word, local_context) → "REDACT" | "KEEP"
groq_cache: dict = {}


def ask_groq_tie_breaker(chunk: str, word: str, start_idx: int) -> str:
    """
    Resolves ambiguous ORGANIZATION detections like 'Apple' (fruit vs company).
    Uses a 60-char window around the specific occurrence so each instance is
    judged independently — "developer in apple" vs "eating an apple".
    Returns 'REDACT' (real org) or 'KEEP' (common noun).
    """
    ctx_start     = max(0, start_idx - 60)
    ctx_end       = min(len(chunk), start_idx + len(word) + 60)
    local_context = chunk[ctx_start:ctx_end]

    cache_key = (word.lower().strip(), local_context.lower().strip())
    if cache_key in groq_cache:
        return groq_cache[cache_key]

    if not groq_client:
        return "REDACT"

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a PII entity classifier. Given a text snippet and a word, decide:\n"
                        "- Return REDACT if the word is a real company, brand, or organization.\n"
                        "- Return KEEP if it is a common noun, fruit, object, or generic concept.\n\n"
                        "Examples:\n"
                        "'developer in apple and' + 'apple' → REDACT\n"
                        "'is eating an apple and' + 'apple' → KEEP\n"
                        "'works at Google' + 'Google' → REDACT\n\n"
                        "Respond with exactly one word: REDACT or KEEP."
                    )
                },
                {"role": "user", "content": f"Context: '{local_context}'\nWord: '{word}'"}
            ],
            temperature=0.0
        )
        raw      = response.choices[0].message.content.strip().upper()
        decision = "REDACT" if "REDACT" in raw else "KEEP"
        groq_cache[cache_key] = decision
        return decision
    except Exception:
        return "REDACT"


def extract_pii_with_groq(text: str) -> list:
    """
    Groq scan for names, orgs, salaries that Presidio's rule engine misses.
    All ORGANIZATIONs still go through the tie-breaker below.
    """
    if not groq_client:
        return []
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise PII detection assistant. Extract ONLY:\n"
                        "- Real people's full names → type: PERSON\n"
                        "- Actual companies or organizations → type: ORGANIZATION\n"
                        "- Salary or monetary compensation values → type: SALARY\n\n"
                        "Do NOT tag fruits, common nouns, or everyday objects as ORGANIZATION.\n"
                        "Return ONLY raw JSON: [{\"text\": \"...\", \"type\": \"...\"}]\n"
                        "No markdown, no explanation."
                    )
                },
                {"role": "user", "content": f"Text: \"{text}\""}
            ],
            temperature=0.0
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.choices[0].message.content.strip(), flags=re.DOTALL)
        return json.loads(raw)
    except Exception as e:
        print("Groq extraction error:", e)
        return []


# ── Utility helpers ───────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 2000) -> list:
    """Splits text into ~chunk_size char chunks at word boundaries."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary
        chunks.append((text[start:end], start))
        start = end
    return chunks


def chunk_needs_groq(chunk: str) -> bool:
    """Skip Groq if chunk has no uppercase or digits — no PII possible."""
    return any(c.isupper() or c.isdigit() for c in chunk)


def merge_overlapping_spans(results: list) -> list:
    """
    Merge overlapping spans keeping the higher-scored one.
    This is how BANK_ACCOUNT (0.96) beats PHONE_NUMBER (0.95) for long numbers,
    and how CREDIT_CARD (0.95) beats BANK_ACCOUNT for spaced 16-digit numbers.
    """
    if not results:
        return []
    merged = []
    for current in sorted(results, key=lambda r: (r.start, -r.end)):
        if not merged:
            merged.append(current)
            continue
        prev = merged[-1]
        if current.start < prev.end:
            curr_len = current.end - current.start
            prev_len = prev.end - prev.start
            if current.score > prev.score or (current.score == prev.score and curr_len > prev_len):
                merged[-1] = current
        else:
            merged.append(current)
    return merged


def mask_with_blocks(value: str) -> str:
    """Named function for MASK style — Presidio requires callable, not lambda."""
    return "█" * len(value)


# Presidio internal label cleanup
NRP_ALIASES = {"NRP"}


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_text_redaction(raw_text: str, redact_style: str = "PLACEHOLDER") -> dict:
    """
    Full redaction pipeline:
    1. Chunk text.
    2. Presidio NER scan (foreign recognizers already disabled at startup).
    3. Groq contextual scan for names/orgs/salaries.
    4. Remap NRP → PERSON.
    5. Confidence threshold filter.
    6. ORGANIZATION tie-breaker with local context window.
    7. Merge overlapping spans (score-based priority resolves conflicts).
    8. Apply redaction operators.
    9. Return result.
    """
    if not raw_text.strip():
        return {"secured_text": "", "entities": [], "metrics": {"characters_processed": 0, "identities_masked": 0}}

    chunks      = chunk_text(raw_text)
    all_results = []

    for chunk, chunk_start in chunks:
        presidio_results = list(analyzer.analyze(text=chunk, language="en"))

        groq_entities = extract_pii_with_groq(chunk) if chunk_needs_groq(chunk) else []

        for ent in groq_entities:
            ent_text, ent_type = ent.get("text", ""), ent.get("type", "")
            if not ent_text or not ent_type:
                continue
            idx = 0
            while True:
                idx = chunk.find(ent_text, idx)
                if idx == -1:
                    break
                end_idx = idx + len(ent_text)
                if not any(not (end_idx <= r.start or idx >= r.end) for r in presidio_results):
                    presidio_results.append(RecognizerResult(entity_type=ent_type, start=idx, end=end_idx, score=1.0))
                idx += 1

        # NRP → PERSON cleanup
        for r in presidio_results:
            if r.entity_type in NRP_ALIASES:
                r.entity_type = "PERSON"

        presidio_results = [r for r in presidio_results if r.score >= MIN_CONFIDENCE_THRESHOLD]

        final = []
        for result in presidio_results:
            word = chunk[result.start:result.end]
            if result.entity_type == "ORGANIZATION" and len(word) > 2:
                if ask_groq_tie_breaker(chunk, word, result.start) == "KEEP":
                    continue
            final.append(result)

        for r in final:
            r.start += chunk_start
            r.end   += chunk_start
        all_results.extend(final)

    merged = merge_overlapping_spans(all_results)

    # For MASK style: anonymize with placeholder first, then replace with blocks manually
    # Reason: Presidio's "custom" operator has version-dependent callable issues
    use_mask = redact_style == "MASK"
    effective_style = "PLACEHOLDER" if use_mask else redact_style

    operators = {}
    for ent_type in {r.entity_type for r in merged}:
        if effective_style == "REDACTED":
            operators[ent_type] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
        elif effective_style == "HIDDEN":
            label = ent_type.replace("IN_", "").replace("_", " ").title()
            operators[ent_type] = OperatorConfig("replace", {"new_value": f"<{label} Hidden>"})
        else:  # PLACEHOLDER (default)
            operators[ent_type] = OperatorConfig("replace", {"new_value": f"<{ent_type}>"})

    anonymized = anonymizer.anonymize(text=raw_text, analyzer_results=merged, operators=operators)
    result_text = anonymized.text

    # MASK: replace every <TAG> placeholder with █ blocks of the original entity length
    if use_mask:
        # Sort by start descending so replacements don't shift indices
        for r in sorted(merged, key=lambda x: x.start, reverse=True):
            original_len = r.end - r.start
            result_text = result_text.replace(f"<{r.entity_type}>", "█" * original_len, 1)

    return {
        "secured_text": result_text,
        "entities": [
            {"text": raw_text[r.start:r.end], "type": r.entity_type, "score": r.score, "start": r.start, "end": r.end}
            for r in merged
        ],
        "metrics": {
            "characters_processed": len(raw_text),
            "identities_masked":    len(merged)
        }
    }