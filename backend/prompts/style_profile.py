STYLE_PROFILE_PROMPT = """
You are a forensic linguist analyzing a paragraph from an academic paper.
Describe the distinctive writing style of this paragraph in exactly 2-3 sentences.
Focus on: tone, structural flow, vocabulary sophistication, syntactic construction,
and punctuation habits.

Detection context:
- This paragraph was flagged by: {detection_engines}
- Boundary corroboration: {corroboration_tier}
- Top feature deltas at boundary: {feature_deltas}

Return your analysis as a JSON object with a single key "style_profile".

Paragraph:
"{paragraph_text}"
"""
