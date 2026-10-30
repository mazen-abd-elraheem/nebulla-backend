"""
Dump full text of benefits_section.docx to markdown file
"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

docx_path = Path("benefits_section.docx")
with zipfile.ZipFile(docx_path) as z:
    xml_content = z.read("word/document.xml")

tree = ET.fromstring(xml_content)
namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

paragraphs = []
for p in tree.iterfind('.//w:p', namespaces):
    texts = [node.text for node in p.iterfind('.//w:t', namespaces) if node.text]
    if texts:
        paragraphs.append("".join(texts))

out_p = Path("scripts/benefits_extracted.txt")
out_p.write_text("\n\n".join(paragraphs), encoding="utf-8")
print(f"Dumped {len(paragraphs)} paragraphs to {out_p}")
