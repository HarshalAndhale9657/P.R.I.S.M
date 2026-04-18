import fitz
with open("test_paper.pdf", "rb") as f:
    pdf_bytes = f.read()

doc = fitz.open(stream=pdf_bytes, filetype="pdf")
page = doc[0]
blocks = page.get_text("blocks")
for b in blocks:
    if b[-1] == 0:  # block_type 0 is text
        print("BLOCK:", repr(b[4]))
