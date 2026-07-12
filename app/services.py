import os
import json
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
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
# Note the use of (?:\b|\s|^) to support symbol matching without strict \b word boundaries
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
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_AADHAAR", patterns=[aadhaar_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_PAN", patterns=[pan_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_PASSPORT", patterns=[passport_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_DRIVING_LICENSE", patterns=[dl_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_VEHICLE_REG", patterns=[vehicle_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_IFSC", patterns=[ifsc_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_UPI", patterns=[upi_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_GSTIN", patterns=[gstin_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_VOTER_ID", patterns=[voter_pattern]))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="IN_PIN_CODE", patterns=[pincode_pattern]))
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

def process_text_redaction(raw_text: str) -> dict:
    """
    Main pipeline:
    1. Scan text using Microsoft Presidio NER (includes custom patterns).
    2. Supplement with Groq contextual PII scan to catch names and salaries.
    3. Filter results by MIN_CONFIDENCE_THRESHOLD.
    4. Check ambiguous organization context.
    5. Anonymize the results.
    """
    # 1. Presidio Analyzer runs first to spot basic PII entities
    analysis_results = analyzer.analyze(text=raw_text, language="en")
    
    # 2. Groq contextual PII scan for high-fidelity extraction
    groq_entities = extract_pii_with_groq(raw_text)
    
    # 3. Convert Groq entities to RecognizerResult objects and merge
    additional_results = []
    for ent in groq_entities:
        ent_text = ent.get("text", "")
        ent_type = ent.get("type", "")
        if not ent_text or not ent_type:
            continue
            
        start_idx = 0
        while True:
            start_idx = raw_text.find(ent_text, start_idx)
            if start_idx == -1:
                break
            end_idx = start_idx + len(ent_text)
            
            # Check for overlap with existing Presidio results
            overlap = False
            for r in analysis_results:
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
            
    all_results = list(analysis_results) + additional_results

    # 4. Confidence Score Filtering
    all_results = [r for r in all_results if r.score >= MIN_CONFIDENCE_THRESHOLD]

    # 5. Filter results and handle ambiguity tie-breakers
    final_results = []
    for result in all_results:
        entity_word = raw_text[result.start:result.end]
        
        # Only run Groq tie-breaker check on ORGANIZATION type to avoid API bottlenecks
        if result.entity_type == "ORGANIZATION" and len(entity_word) > 2:
            is_extracted_by_groq = any(ent.get("text", "").lower() == entity_word.lower() for ent in groq_entities)
            if not is_extracted_by_groq:
                decision = ask_groq_tie_breaker(raw_text, entity_word)
                if decision == "KEEP":
                    continue
                    
        final_results.append(result)

    # 6. Pass results to anonymizer engine
    anonymized_result = anonymizer.anonymize(
        text=raw_text,
        analyzer_results=final_results
    )
    
    return {
        "secured_text": anonymized_result.text,
        "metrics": {
            "characters_processed": len(raw_text),
            "identities_masked": len(final_results)
        }
    }