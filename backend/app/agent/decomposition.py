"""
app/agent/decomposition.py - Multi-Question Decomposition Engine for ASTERION.

Detects question boundaries across composite and batch prompts:
- Q-labels: Q51, Q52, Q53, etc.
- Numbered lists: 1., 2., (1), 1), etc.
- Lettered lists: A., B., etc.
- Question prefixes: "Question 1:", "Question 2.", etc.
- Paragraph boundaries where each paragraph is an independent question
- Conjunctions (" AND ") connecting complete interrogative sentences

Preserves original question IDs and guarantees that no question silently disappears.
"""

import re
from typing import List
from dataclasses import dataclass


@dataclass
class SubQuestion:
    index: int
    label: str  # e.g., "Q51", "Q52", "1", "Part 1"
    raw_text: str
    cleaned_text: str

    def to_dict(self):
        return {
            "index": self.index,
            "label": self.label,
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text
        }


def decompose_query(query: str) -> List[SubQuestion]:
    """
    Decomposes a user query into atomic subquestions.
    Preserves question IDs and formatting.
    """
    if not query or not query.strip():
        return []

    q_strip = query.strip()

    # Pattern 1: Explicit Q-numbers or list items at line starts
    # Matches: Q51., Q51:, Q51 , 1., 1), (1), Question 1:, A., - Q51., * Q51.
    boundary_pattern = r'(?=(?:^|\n)\s*(?:[-*•]\s*)?(?:Q\d+[\.:\s]|\d+[\.\)]\s+|Question\s+\d+[:\.]|[A-Za-z][\.\)]\s+))'
    splits = [s.strip() for s in re.split(boundary_pattern, q_strip) if s.strip()]

    if len(splits) > 1:
        results = []
        for i, raw in enumerate(splits, start=1):
            m = re.match(r'^(?:[-*•]\s*)?(Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\s]*', raw, re.IGNORECASE)
            label = m.group(1).upper() if m else f"Q{i}"
            if label.startswith("QUESTION"):
                label = label.replace("QUESTION", "Q").replace(" ", "")
            cleaned = re.sub(r'^(?:[-*•]\s*)?(?:Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\s]*', '', raw, flags=re.IGNORECASE).strip()
            results.append(SubQuestion(index=i, label=label, raw_text=raw, cleaned_text=cleaned or raw))
        return results

    # Pattern 2: Paragraph splits (\n\s*\n) where paragraphs are distinct questions
    paras = [p.strip() for p in re.split(r'\n\s*\n+', q_strip) if p.strip()]
    if len(paras) > 1:
        results = []
        for i, p in enumerate(paras, start=1):
            m = re.match(r'^(?:[-*•]\s*)?(Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\)]\s*', p, re.IGNORECASE)
            if m:
                label = m.group(1).upper()
                if label.startswith("QUESTION"):
                    label = label.replace("QUESTION", "Q").replace(" ", "")
                cleaned = re.sub(r'^(?:[-*•]\s*)?(?:Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\)]\s*', '', p, flags=re.IGNORECASE).strip()
            else:
                label = f"Q{i}"
                cleaned = p
            results.append(SubQuestion(index=i, label=label, raw_text=p, cleaned_text=cleaned or p))
        return results

    # Pattern 3: Explicit conjunction " AND " connecting separate questions
    if " AND " in q_strip:
        and_parts = [p.strip() for p in q_strip.split(" AND ") if len(p.strip()) > 15]
        if len(and_parts) > 1 and all("?" in p or any(p.lower().startswith(w) for w in ["how", "what", "which", "give", "trace", "calculate"]) for p in and_parts):
            results = []
            for i, p in enumerate(and_parts, start=1):
                results.append(SubQuestion(index=i, label=f"Part {i}", raw_text=p, cleaned_text=p))
            return results

    # Single question fallback
    m = re.match(r'^(?:[-*•]\s*)?(Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\)]\s*', q_strip, re.IGNORECASE)
    if m:
        label = m.group(1).upper()
        if label.startswith("QUESTION"):
            label = label.replace("QUESTION", "Q").replace(" ", "")
        cleaned = re.sub(r'^(?:[-*•]\s*)?(?:Q\d+|\d+|Question\s+\d+|[A-Za-z])[\.:\)]\s*', '', q_strip, flags=re.IGNORECASE).strip()
    else:
        label = "Q1"
        cleaned = q_strip
    return [SubQuestion(index=1, label=label, raw_text=q_strip, cleaned_text=cleaned or q_strip)]
