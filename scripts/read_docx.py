"""
Extract text from benefits_section.docx
"""

import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

docx_path = Path("benefits_section.docx")
if not docx_path.exists():
    print(f"File not found: {docx_path.resolve()}")
    sys.exit(1)

with zipfile.ZipFile(docx_path) as z:
    xml_content = z.read("word/document.xml")

tree = ET.fromstring(xml_content)
namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

paragraphs = []
for p in tree.iterfind('.//w:p', namespaces):
    texts = [node.text for node in p.iterfind('.//w:t', namespaces) if node.text]
    if texts:
        paragraphs.append("".join(texts))

full_text = "\n".join(paragraphs)
print("=== EXTRACTED TEXT FROM benefits_section.docx ===")
print(full_text)
