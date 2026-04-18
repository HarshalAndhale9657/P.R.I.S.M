import fitz
with open("test_paper.pdf", "rb") as f:
    pdf_bytes = f.read()

doc = fitz.open(stream=pdf_bytes, filetype="pdf")
page = doc[0]
text = page.get_text("text")
print("repr of text:")
print(repr(text))
