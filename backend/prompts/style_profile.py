STYLE_PROFILE_PROMPT = """
You are a forensic linguist analyzing a paragraph from an academic paper.
Describe the distinctive writing style of this paragraph in exactly 2-3 sentences.
Focus on identifying characteristics such as tone, structural flow, vocabulary sophistication,
and syntactic structure. 
Return your analysis as a JSON object with a single key "style_profile".

Paragraph:
"{paragraph_text}"
"""
