"""
Hierarchical & Layout-Aware Chunker.

Solves the Chunking Strategy & Table/Boundary Problem in RAG:
- Parent-Child Chunking: Small child chunks for high-resolution vector/BM25 retrieval, mapped to larger parent chunks for LLM context.
- Markdown Table Protection: Detects markdown tables and keeps them intact within a single chunk rather than slicing rows in half.
- Sentence & Paragraph Boundary Preservation: Splits text on natural semantic boundaries (paragraphs, full stops, question marks).
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_id: str
    content: str
    parent_id: Optional[str] = None
    is_parent: bool = False
    metadata: Optional[Dict[str, Any]] = None


class HierarchicalChunker:
    """
    Hierarchical chunker that generates:
    1. Parent Chunks: Large contextual units (500-1500 characters) containing full explanations.
    2. Child Chunks: Focused sub-units (150-300 characters) for pinpoint retrieval matching.
    """

    def __init__(
        self,
        parent_chunk_size: int = 800,
        parent_overlap: int = 150,
        child_chunk_size: int = 200,
        child_overlap: int = 50,
    ):
        self.parent_chunk_size = parent_chunk_size
        self.parent_overlap = parent_overlap
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    def chunk_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[TextChunk], List[TextChunk]]:
        """
        Split document into (parent_chunks, child_chunks).
        Returns a tuple: (list of parent TextChunk, list of child TextChunk).
        """
        if not text or not text.strip():
            return [], []

        clean_text = text.strip()

        # Step 1: Detect tables or preserve markdown structures
        raw_parents = self._split_into_paragraphs(clean_text, max_size=self.parent_chunk_size)

        parents: List[TextChunk] = []
        children: List[TextChunk] = []

        for p_idx, p_text in enumerate(raw_parents):
            p_id = f"{doc_id}_p{p_idx}"
            parent_chunk = TextChunk(
                chunk_id=p_id,
                content=p_text,
                parent_id=None,
                is_parent=True,
                metadata={**(metadata or {}), "doc_id": doc_id, "parent_index": p_idx},
            )
            parents.append(parent_chunk)

            # Step 2: Split parent into child chunks
            raw_children = self._split_sentences(p_text, max_size=self.child_chunk_size)
            for c_idx, c_text in enumerate(raw_children):
                c_id = f"{p_id}_c{c_idx}"
                child_chunk = TextChunk(
                    chunk_id=c_id,
                    content=c_text,
                    parent_id=p_id,
                    is_parent=False,
                    metadata={**(metadata or {}), "doc_id": doc_id, "parent_id": p_id},
                )
                children.append(child_chunk)

        return parents, children

    def _split_into_paragraphs(self, text: str, max_size: int) -> List[str]:
        """Split text by paragraphs while respecting table blocks and sentence boundaries."""
        # Check for markdown table blocks (|...|) allowing leading/trailing spaces on each row
        table_pattern = re.compile(r"((?:^[ \t]*\|[^\r\n]+\|[ \t]*(?:\r?\n|$))+)", re.MULTILINE)
        blocks = []
        last_end = 0

        for match in table_pattern.finditer(text):
            start, end = match.span()
            if start > last_end:
                blocks.append(text[last_end:start])
            # Keep table block completely intact
            matched_table = "\n".join(line.strip() for line in match.group(0).splitlines() if line.strip())
            blocks.append(matched_table)
            last_end = end

        if last_end < len(text):
            blocks.append(text[last_end:])

        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for b in blocks:
            b_str = b.strip()
            if not b_str:
                continue

            # If it's a table, push it as a distinct block
            if b_str.startswith("|") and b_str.endswith("|"):
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                chunks.append(b_str)
                continue

            if current_len + len(b_str) > max_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [b_str]
                current_len = len(b_str)
            else:
                current_chunk.append(b_str)
                current_len += len(b_str)

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_sentences(self, text: str, max_size: int) -> List[str]:
        """Split text into smaller sentence units."""
        sentences = re.split(r"(?<=[.!?؟\n])\s+", text)
        sub_chunks: List[str] = []
        curr = ""

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if len(curr) + len(s_clean) > max_size and curr:
                sub_chunks.append(curr.strip())
                curr = s_clean
            else:
                curr = f"{curr} {s_clean}".strip()

        if curr:
            sub_chunks.append(curr.strip())

        return sub_chunks
