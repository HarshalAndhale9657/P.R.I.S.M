COMPARE_PROMPT = """
You are a forensic linguist. Analyze these two consecutive paragraphs from a document.
A mathematical clustering algorithm (HDBSCAN) has flagged that a boundary exists here,
indicating these two paragraphs were likely written by different authors.

Explain in natural language WHY these styles differ. Focus on vocabulary, tone, 
sentence structure, and academic formality. Explain why paragraph B looks like an anomalous insertion.

Return the result as a JSON object:
{
    "explanation": "Your natural language explanation (2-3 sentences max)."
}

Paragraph A (Prior section):
"{para_A}"

Paragraph B (Anomalous transition):
"{para_B}"
"""
