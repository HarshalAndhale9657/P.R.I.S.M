import fitz
import io
import asyncio
from services.pdf_parser import AcademicPDFParser
from models import PipelineContext

parser = AcademicPDFParser()
ctx = PipelineContext()

with open("test_paper.pdf", "rb") as f:
    pdf_bytes = f.read()

res = parser.parse(pdf_bytes, ctx)

print("Parsed Method:", res["extraction_method"])
print("Paragraphs found:", len(res["paragraphs"]))
if not res["paragraphs"]:
    print("Warnings from ctx:")
    import json
    for w in ctx.warnings:
        print(w.model_dump())
