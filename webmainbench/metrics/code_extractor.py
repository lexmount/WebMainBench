# webmainbench/metrics/extractors/code_extractor.py
from typing import List, Dict, Any

from bs4 import BeautifulSoup
import markdown

from .base_content_splitter import BaseContentSplitter, _metrics_debug


class CodeSplitter(BaseContentSplitter):
    """Extract code blocks from text."""

    def extract(self, text: str, field_name: str = None) -> str:
        """Extract code blocks."""
        code_blocks = self.extract_basic(text)
        return '\n'.join(code_blocks)

    def extract_basic(self, text: str) -> List[str]:
        """Extract Markdown and raw-HTML code in document order.

        Browser extractors may preserve links or table structure by returning
        ``<pre>``/``<code>`` HTML.  Parsing the Markdown first gives fenced,
        indented and inline code the same representation while retaining those
        HTML fallbacks.  A ``code`` inside ``pre`` is skipped separately so one
        block is counted once.
        """
        rendered = markdown.markdown(text, extensions=["fenced_code"])
        soup = BeautifulSoup(rendered, "html.parser")
        code_parts = []
        for node in soup.find_all(["pre", "code"]):
            if node.name == "code" and node.find_parent("pre") is not None:
                continue
            content = node.get_text().strip("\n")
            if content.strip():
                code_parts.append(content)
        return code_parts

    def _llm_enhance(self, basic_results: List[str]) -> List[str]:
        """Code extraction does not use LLM enhancement."""
        return basic_results
