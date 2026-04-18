import fitz
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from services.pdf_parser import PDFParser
from services.feature_engine import FeatureEngine

def test():
    parser = PDFParser()
    try:
        parsed = parser.parse_pdf("ai_generated_test.pdf")
    except Exception as e:
        print(f"Failed to parse PDF: {e}")
        return
        
    paragraphs = parsed.get("paragraphs", [])
    print(f"Total paragraphs parsed: {len(paragraphs)}")
    
    if not paragraphs:
        print("No text!")
        return

    engine = FeatureEngine()
    features = engine.extract_all(paragraphs)
    
    profiles = features.get("profiles", [])
    print(f"Extracted {len(profiles)} profiles.")
    
    scores = []
    for p in profiles:
        b_score = p.get("burstiness_score", 0)
        paras = p.get("paragraph_index")
        print(f"Para {paras}: Burstiness = {b_score}")
        if b_score > 0.01:
            scores.append(b_score)
            
    print(f"Valid burstiness scores > 0.01: {len(scores)}")
    if len(scores) < 3:
        print("Too few paragraphs for AI generation check!")
    else:
        avg = sum(scores) / len(scores)
        print(f"Average AI burstiness: {avg:.4f}")
        if avg < 0.55:
            print("AI DETECTED!")
        else:
            print("No AI detected.")

if __name__ == "__main__":
    test()
