import os
import json
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Microsoft Presidio Engines
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

# Confidence threshold for PII detections (configurable via env)
MIN_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.6"))

# Custom Pattern Recognizers for Salary and Money
# Matches: $45000, 45,000 USD, Rs. 50000, ₹1200000, etc.
money_pattern = Pattern(
    name="money_pattern",
    regex=r"(?:\b|\s|^)(?:\$|Rs\.?|₹|£|€)\s?\d+(?:,\d{3})*(?:\.\d{2})?\b|\b\d+(?:,\d{3})*(?:\.\d{2})?\s?(?:USD|INR|dollars|rupees|EUR|GBP)\b",
    score=0.85
)

# Matches salary descriptions, e.g. "salary of 45000", "earns 800000", "pay is 120000"
salary_pattern = Pattern(
    name="salary_pattern",
    regex=r"\b(?:salary|earns|earning|earn|compensation|package|income|pay|wage|wages)\b(?:\s+\w+){0,3}?\s+(\d+(?:,\d{3})*(?:\.\d{2})?)\b",
    score=0.9
)

money_recognizer = PatternRecognizer(supported_entity="MONEY", patterns=[money_pattern])
salary_recognizer = PatternRecognizer(supported_entity="SALARY", patterns=[salary_pattern])

analyzer.registry.add_recognizer(money_recognizer)
analyzer.registry.add_recognizer(salary_recognizer)

# --- Indian PII Custom Patterns ---
aadhaar_pattern = Pattern(
    name="aadhaar_pattern",
    regex=r"\b[2-9]\d{3}\s\d{4}\s\d{4}\b|\b[2-9]\d{11}\b",
    score=0.85
)

pan_pattern = Pattern(
    name="pan_pattern",
    regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    score=0.9
)

passport_pattern = Pattern(
    name="passport_pattern",
    regex=r"\b[A-Z][0-9]{7}\b",
    score=0.85
)

dl_pattern = Pattern(
    name="dl_pattern",
    regex=r"\b[A-Z]{2}[0-9]{2}\s?[0-9]{11}\b",
    score=0.85
)

vehicle_pattern = Pattern(
    name="vehicle_pattern",
    regex=r"\b[A-Z]{2}[0-9]{2}\s?[A-Z]{1,2}\s?[0-9]{4}\b",
    score=0.85
)

ifsc_pattern = Pattern(
    name="ifsc_pattern",
    regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    score=0.9
)

upi_pattern = Pattern(
    name="upi_pattern",
    regex=r"\b[a-zA-Z0-9_.-]+@[a-zA-Z0-9_-]+\b",
    score=0.85
)

gstin_pattern = Pattern(
    name="gstin_pattern",
    regex=r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
    score=0.9
)

voter_pattern = Pattern(
    name="voter_pattern",
    regex=r"\b[A-Z]{3}[0-9]{7}\b",
    score=0.85
)

pincode_pattern = Pattern(
    name="pincode_pattern",
    regex=r"\b[1-9][0-9]{5}\b",
    score=0.75
)

# Broad numeric pattern for accounts requires contextual trigger words to score high
bank_acc_pattern = Pattern(
    name="bank_acc_pattern",
    regex=r"\b[0-9]{9,18}\b",
    score=0.5
)

# Register Indian PII recognizers
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="AADHAAR", patterns=[aadhaar_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="PAN", patterns=[pan_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="PASSPORT", patterns=[passport_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="DRIVING_LICENSE", patterns=[dl_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="VEHICLE_REG", patterns=[vehicle_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IFSC", patterns=[ifsc_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="UPI", patterns=[upi_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="GSTIN", patterns=[gstin_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="VOTER_ID", patterns=[voter_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="PIN_CODE", patterns=[pincode_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="BANK_ACCOUNT",
    patterns=[bank_acc_pattern],
    context=["account", "acc", "bank", "savings", "current", "a/c"]
))

# Initialize Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

groq_cache = {}

def ask_groq_tie_breaker(sentence: str, word: str) -> str:
    """
    If Presidio is confused about an ambiguous word (like Apple),
    this checks via Groq Llama-3 to resolve if it is a brand or a common noun.
    Uses in-memory caching to optimize response times.
    """
    word_key = word.lower().strip()
    if word_key in groq_cache:
        return groq_cache[word_key]

    if not groq_client:
        return "REDACT"
        
    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze the sentence. Is the specific word referring to a corporate brand/private entity or a general common noun/fruit? Respond with strictly one word: 'REDACT' or 'KEEP'."
                },
                {
                    "role": "user",
                    "content": f"Sentence: '{sentence}'. Word to check: '{word}'."
                }
            ],
            temperature=0.0
        )
        decision = chat_completion.choices[0].message.content.strip().upper()
        groq_cache[word_key] = decision
        return decision
    except Exception:
        return "REDACT"

def extract_pii_with_groq(text: str) -> list:
    """
    Leverages Groq Cloud to run a precise contextual scan for names, organizations,
    and salaries that statistical models like spaCy might miss.
    """
    if not groq_client:
        return []
    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise PII detection assistant. Analyze the text and extract "
                        "all names of people (type: PERSON), companies/organizations (type: ORGANIZATION), "
                        "and salaries/earnings/monetary amounts (type: SALARY). "
                        "Respond with strictly a JSON list of objects containing 'text' (the exact word/phrase "
                        "from the input) and 'type' ('PERSON', 'ORGANIZATION', or 'SALARY'). "
                        "Do not return any other text, markdown formatting, or explanation. Only the raw JSON list."
                    )
                },
                {
                    "role": "user",
                    "content": f"Text: \"{text}\""
                }
            ],
            temperature=0.0
        )
        response_text = chat_completion.choices[0].message.content.strip()
        
        # Clean markdown formatting if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
                
        return json.loads(response_text.strip())
    except Exception as e:
        print("Groq extraction error:", e)
        return []

def chunk_text(text: str, chunk_size: int = 2000) -> list:
    """
    Splits the document into slices of chunk_size characters,
    splitting at space characters where possible to avoid cutting words.
    Returns a list of tuples: (chunk_text, start_index)
    """
    chunks = []
    start = 0
    total_len = len(text)
    
    while start < total_len:
        end = start + chunk_size
        if end >= total_len:
            chunks.append((text[start:total_len], start))
            break
            
        # Try to find a space or newline near the boundary to avoid splitting a word
        boundary = text.rfind(" ", start, end)
        if boundary != -1 and boundary > start + (chunk_size // 2):
            end = boundary
            
        chunks.append((text[start:end], start))
        start = end
        
    return chunks

def chunk_needs_groq(chunk: str) -> bool:
    """
    Heuristic check to skip calling the Groq LLM on non-PII chunks.
    If the chunk has no capital letters or numbers, it doesn't contain names/orgs/salaries.
    """
    has_upper = any(c.isupper() for c in chunk)
    has_digit = any(c.isdigit() for c in chunk)
    return has_upper or has_digit

def merge_overlapping_spans(results: list) -> list:
    """
    Sorts and merges overlapping or duplicate RecognizerResult spans.
    Resolves conflicts by keeping the span with the higher score or longer length.
    """
    if not results:
        return []
        
    # Sort results by start index, then by end index descending
    sorted_results = sorted(results, key=lambda r: (r.start, -r.end))
    
    merged = []
    for current in sorted_results:
        if not merged:
            merged.append(current)
            continue
            
        prev = merged[-1]
        
        # Overlap check
        if current.start < prev.end:
            prev_len = prev.end - prev.start
            curr_len = current.end - current.start
            
            # Keep current if score is higher, or if scores are equal and current is longer
            if current.score > prev.score or (current.score == prev.score and curr_len > prev_len):
                merged[-1] = current
            # Else, keep prev and discard current
        else:
            merged.append(current)
            
    return merged

def process_text_redaction(raw_text: str, redact_style: str = "PLACEHOLDER") -> dict:
    """
    Main pipeline:
    1. Slice document into optimal chunk sizes.
    2. Analyze each chunk locally with Presidio.
    3. Supplement PII-rich chunks with Groq contextual scanning.
    4. Apply confidence thresholding and ORGANIZATION tie-breaker validations.
    5. Merge overlapping/duplicate spans.
    6. Anonymize the document using the requested redaction style.
    """
    if not raw_text.strip():
        return {
            "secured_text": "",
            "entities": [],
            "metrics": {
                "characters_processed": 0,
                "identities_masked": 0
            }
        }
        
    chunks = chunk_text(raw_text, chunk_size=2000)
    all_final_results = []
    
    for chunk, chunk_start in chunks:
        # 1. Run local Presidio Analyzer
        chunk_analysis = analyzer.analyze(text=chunk, language="en")
        
        # 2. Run Groq scan if chunk contains potential PII
        groq_entities = []
        if chunk_needs_groq(chunk):
            groq_entities = extract_pii_with_groq(chunk)
            
        # 3. Merge Groq entities into the chunk analyzer results
        additional_results = []
        for ent in groq_entities:
            ent_text = ent.get("text", "")
            ent_type = ent.get("type", "")
            if not ent_text or not ent_type:
                continue
                
            start_idx = 0
            while True:
                start_idx = chunk.find(ent_text, start_idx)
                if start_idx == -1:
                    break
                end_idx = start_idx + len(ent_text)
                
                # Check for overlap
                overlap = False
                for r in chunk_analysis:
                    if not (end_idx <= r.start or start_idx >= r.end):
                        overlap = True
                        break
                        
                if not overlap:
                    additional_results.append(RecognizerResult(
                        entity_type=ent_type,
                        start=start_idx,
                        end=end_idx,
                        score=1.0
                    ))
                start_idx += 1
                
        chunk_all_results = list(chunk_analysis) + additional_results
        
        # 4. Confidence Score Filtering
        chunk_all_results = [r for r in chunk_all_results if r.score >= MIN_CONFIDENCE_THRESHOLD]
        
        # 5. Handle ambiguity tie-breakers on ORGANIZATION
        chunk_final = []
        for result in chunk_all_results:
            entity_word = chunk[result.start:result.end]
            
            if result.entity_type == "ORGANIZATION" and len(entity_word) > 2:
                is_extracted_by_groq = any(ent.get("text", "").lower() == entity_word.lower() for ent in groq_entities)
                if not is_extracted_by_groq:
                    decision = ask_groq_tie_breaker(chunk, entity_word)
                    if decision == "KEEP":
                        continue
                        
            chunk_final.append(result)
            
        # Offset chunk results to match global raw_text coordinate index space
        for r in chunk_final:
            r.start += chunk_start
            r.end += chunk_start
            all_final_results.append(r)
            
    # 6. Merge overlapping spans globally
    merged_results = merge_overlapping_spans(all_final_results)
    
    # 7. Construct operators based on redact_style configuration
    operators = {}
    entity_types = set(r.entity_type for r in merged_results)
    for ent_type in entity_types:
        if redact_style == "REDACTED":
            operators[ent_type] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
        elif redact_style == "MASK":
            # Direct custom function configuration
            operators[ent_type] = OperatorConfig("custom", {
                "custom_anonymizer": lambda val: "█" * len(val)
            })
        elif redact_style == "HIDDEN":
            clean_label = ent_type.replace("IN_", "").replace("_", " ").title()
            operators[ent_type] = OperatorConfig("replace", {"new_value": f"<{clean_label} Hidden>"})
        else:
            operators[ent_type] = OperatorConfig("replace", {"new_value": f"<{ent_type}>"})

    # 8. Pass results to anonymizer engine
    anonymized_result = anonymizer.anonymize(
        text=raw_text,
        analyzer_results=merged_results,
        operators=operators
    )
    
    # Compile rich entity list
    entities_list = []
    for r in merged_results:
        entities_list.append({
            "text": raw_text[r.start:r.end],
            "type": r.entity_type,
            "score": r.score,
            "start": r.start,
            "end": r.end
        })
        
    return {
        "secured_text": anonymized_result.text,
        "entities": entities_list,
        "metrics": {
            "characters_processed": len(raw_text),
            "identities_masked": len(merged_results)
        }
    }