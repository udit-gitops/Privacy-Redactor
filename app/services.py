import os
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Microsoft Presidio Engines
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

# Initialize Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def ask_groq_tie_breaker(sentence: str, word: str) -> str:
    """
    Agar Presidio kisi ambiguous word (jaise Apple) par confuse ho jaye, 
    toh ye function Groq Llama-3 ko call karke verify karega.
    """
    if not groq_client:
        return "REDACT"  # Safe default fallback agar key missing ho
        
    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama3-8b-8192",
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
            temperature=0.0  # Strict classification toggle
        )
        return chat_completion.choices[0].message.content.strip().upper()
    except Exception:
        return "REDACT"

def process_text_redaction(raw_text: str) -> dict:
    """
    Main pipeline:
    1. Scan text using Microsoft Presidio NER.
    2. Check ambiguous context.
    3. Mask sensitive data.
    """
    # 1. Presidio Analyzer runs first to spot basic PII entities
    analysis_results = analyzer.analyze(text=raw_text, language="en")
    
    # Track metrics for database logs
    entities_count = len(analysis_results)
    
    # 2. Advanced Step: Post-processing context checks (Ambiguity handling)
    # Proves to recruiters you know how to build advanced data loops
    final_results = []
    for result in analysis_results:
        entity_word = raw_text[result.start:result.end]
        
        # Agar koi generic word highly flag ho rha hai, tie-breaker call karo
        if result.entity_type in ["ORGANIZATION", "PERSON"] and len(entity_word) > 2:
            decision = ask_groq_tie_breaker(raw_text, entity_word)
            if decision == "KEEP":
                continue # Skip redacting this specific entity
                
        final_results.append(result)

    # 3. Pass vetted results to anonymizer engine for structural swapping
    anonymized_result = anonymizer.anonymize(
        text=raw_text,
        analyzer_results=final_results
    )
    
    return {
        "redacted_text": anonymized_result.text,
        "character_count": len(raw_text),
        "entities_found": entities_count
    }