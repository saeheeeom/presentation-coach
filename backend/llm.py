"""Optional LLM-assisted segmentation with a free local Hugging Face model.

Install with `uv sync --extra llm`. The model is chosen with the PC_LLM_MODEL
environment variable (default: Qwen/Qwen2.5-1.5B-Instruct, which runs on CPU
and is fast on a PACE GPU node). The LLM only chooses where segment
boundaries go; the text always comes from the original sentences.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from .segmenter import sentence_units

DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

_PROMPT = """You split a presentation script into practice segments.
A good segment is one complete idea, usually 1-3 sentences and 15-45 words.
Never put sentences from different paragraphs in the same segment.

Numbered sentences (paragraphs separated by blank lines):
{numbered}

Reply with ONLY a JSON list of lists of sentence numbers, in order, covering
every sentence exactly once. Example: [[1, 2], [3], [4, 5, 6]]"""


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _pipeline():
    if not available():
        raise LLMUnavailable("transformers/torch not installed; run `uv sync --extra llm`")
    import torch
    from transformers import pipeline

    model = os.environ.get("PC_LLM_MODEL", DEFAULT_MODEL)
    device = 0 if torch.cuda.is_available() else -1
    return pipeline("text-generation", model=model, device=device, torch_dtype="auto")


def _generate(prompt: str) -> str:
    out = _pipeline()(
        [{"role": "user", "content": prompt}],
        max_new_tokens=512,
        do_sample=False,
    )
    return out[0]["generated_text"][-1]["content"]


def parse_groups(reply: str, paragraphs: list[list[str]]) -> list[str]:
    """Validate the model's grouping and rebuild segment texts from it.

    Raises ValueError unless the groups cover every sentence once, in order,
    without crossing a paragraph boundary.
    """
    match = re.search(r"\[\s*\[.*\]\s*\]", reply, re.DOTALL)
    if not match:
        raise ValueError("no JSON list in model reply")
    groups = json.loads(match.group(0))

    sentences: list[str] = []
    paragraph_of: list[int] = []
    for p_idx, para in enumerate(paragraphs):
        sentences.extend(para)
        paragraph_of.extend([p_idx] * len(para))

    flat = [n for g in groups for n in g]
    if flat != list(range(1, len(sentences) + 1)):
        raise ValueError("groups do not cover every sentence in order")
    texts = []
    for group in groups:
        if not group or len({paragraph_of[n - 1] for n in group}) != 1:
            raise ValueError("group is empty or crosses a paragraph")
        texts.append(" ".join(sentences[n - 1] for n in group))
    return texts


def split_with_llm(script: str) -> list[str]:
    paragraphs = sentence_units(script)
    lines, n = [], 1
    for para in paragraphs:
        for sentence in para:
            lines.append(f"{n}. {sentence}")
            n += 1
        lines.append("")
    return parse_groups(_generate(_PROMPT.format(numbered="\n".join(lines).strip())), paragraphs)
