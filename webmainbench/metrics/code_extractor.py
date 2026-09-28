# webmainbench/metrics/extractors/code_extractor.py
import html
import re
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
        text = self._promote_indented_code(text)
        parser = markdown.Markdown(extensions=["fenced_code"])
        # Python-Markdown otherwise turns every four-space-indented paragraph
        # into code.  Frozen pages include wrapped prose with that layout, so
        # only the conservative, code-shaped blocks promoted above qualify.
        parser.parser.blockprocessors.deregister("indent")
        parser.parser.blockprocessors.deregister("code")
        rendered = parser.convert(text)
        soup = BeautifulSoup(rendered, "html.parser")
        code_parts = []
        for node in soup.find_all(["pre", "code", "cccode-inline", "cccode-block"]):
            if node.name == "code" and node.find_parent(
                ["pre", "cccode-inline", "cccode-block"]
            ) is not None:
                continue
            content = node.get_text().strip("\n")
            if node.name.startswith("cccode-") and len(content) >= 2:
                if content[0] == content[-1] == "`":
                    content = content[1:-1]
            if content.strip():
                code_parts.append(content)
        return code_parts

    @staticmethod
    def _looks_like_code(lines: List[str]) -> bool:
        """Reject layout-indented prose while retaining common code forms."""
        starts_like_code = re.compile(
            r"^(?:>>>|\.\.\.|[$#>]\s|(?:async\s+)?(?:def|class|function)\s+|"
            r"(?:from|import|return|yield|throw|const|let|var|public|private|protected)\b|"
            r"(?:if|for|while|switch|try|catch)\s*\(|(?:print|console\.log)\s*\(|"
            r"</?[A-Za-z][^>]*>|//|/\*|\*\/|[{}])"
        )
        code_punctuation = re.compile(r"(?:[{};]|=>|==|!=|:=|\w+\([^)]*\)|</?\w+[^>]*>)")
        return any(starts_like_code.search(line) for line in lines) or sum(
            bool(code_punctuation.search(line)) for line in lines
        ) >= 2

    @classmethod
    def _promote_indented_code(cls, text: str) -> str:
        """Turn only code-shaped Markdown indents into explicit ``pre`` nodes."""
        protected = []
        for pattern in (
            r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$",
            r"(?is)<(?:pre|code)\b[^>]*>.*?</(?:pre|code)\s*>",
        ):
            protected.extend(match.span() for match in re.finditer(pattern, text))

        indent_pattern = re.compile(
            r"(?:\n\s*\n)((?:(?: {4,}|\t+)[^\n]*(?:\n|$)){2,})(?=\n\s*\n|$)",
            re.MULTILINE,
        )
        replacements = []
        for match in indent_pattern.finditer(text):
            start, end = match.span(1)
            if any(start < protected_end and end > protected_start
                   for protected_start, protected_end in protected):
                continue
            raw_lines = [line for line in match.group(1).splitlines() if line.strip()]
            cleaned = [line[4:] if line.startswith("    ") else line[1:]
                       if line.startswith("\t") else line for line in raw_lines]
            if len(cleaned) < 2 or not cls._looks_like_code([line.strip() for line in cleaned]):
                continue
            replacement = '<pre data-webmainbench-indented-code="true">' + (
                html.escape("\n".join(cleaned))
            ) + "</pre>"
            replacements.append((start, end, replacement))

        for start, end, replacement in reversed(replacements):
            text = text[:start] + replacement + text[end:]
        return text

    def _llm_enhance(self, basic_results: List[str]) -> List[str]:
        """Code extraction does not use LLM enhancement."""
        return basic_results
