# tests/test/test_code_extraction.py
# !/usr/bin/env python
"""Test code extraction functionality"""

import unittest
import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from webmainbench.metrics.base import BaseMetric, MetricResult
from webmainbench.metrics.text_metrics import CodeEditMetric


class TestCodeExtractionMetric(BaseMetric):
    """Concrete implementation class for testing"""

    def _setup(self) -> None:
        pass

    def _calculate_score(self, predicted: str, groundtruth: str, **kwargs) -> MetricResult:
        return MetricResult(
            metric_name=self.name,
            score=1.0,
            details={"test": True}
        )


class TestCodeExtraction(unittest.TestCase):
    """Test code extraction functionality"""

    def setUp(self):
        self.metric = TestCodeExtractionMetric("test_metric")

    def test_empty_text(self):
        """Test empty text"""
        result = BaseMetric._extract_from_markdown("")
        self.assertEqual(result['code'], '')
        self.assertEqual(result['text'], '')

    def test_inline_code(self):
        """Inline code is part of the declared code population."""
        text = "This is an example of `inline code`"
        result = BaseMetric._extract_from_markdown(text)
        self.assertEqual(result['code'], 'inline code')
        self.assertEqual(result['text'], text)

    def test_raw_html_code_preserves_links_and_table_structure(self):
        """Semantic HTML fallbacks still expose their code text to scoring."""
        text = """
<table><tr><td>source</td><td><pre><a href="#L1">one()</a>
two()</pre></td></tr></table>

Use <code>result</code> below.
"""
        result = BaseMetric._extract_from_markdown(text)
        self.assertEqual(result['code'], 'one()\ntwo()\nresult')

    def test_fenced_html_is_not_double_counted(self):
        """HTML-looking source inside a fence remains one code block."""
        text = """```html
<pre><code>literal</code></pre>
```"""
        result = BaseMetric._extract_from_markdown(text)
        self.assertEqual(result['code'], '<pre><code>literal</code></pre>')

    def test_code_population_is_defined_by_the_reference(self):
        """Prediction-only code cannot change one method's denominator."""
        metric = CodeEditMetric("code_edit", {"use_llm": False})
        outside_scope = metric.calculate("`invented()`", "plain reference")
        self.assertFalse(outside_scope.success)
        self.assertEqual(outside_scope.details["availability"], "reference_defined")

        missing_prediction = metric.calculate("plain prediction", "use `expected()`")
        self.assertTrue(missing_prediction.success)
        self.assertEqual(missing_prediction.score, 0.0)

    def test_code_block(self):
        """Test code block"""
        text = """
I have the following string: `"aaaabbbb"`
How can I get the last four characters and store them in a string using Python?
Like this:
```python
>>> mystr = "abcdefghijkl"
>>> mystr[-4:]
'ijkl'
```
        """

        result = BaseMetric._extract_from_markdown(text)

        # Verify extracted code
        expected_code = ("""
"aaaabbbb"
>>> mystr = "abcdefghijkl"
>>> mystr[-4:]
'ijkl'
        """)
        self.assertEqual(result['code'], expected_code.strip())
        self.assertEqual(result['formula'], '')

    # def test_code_with_leading_trailing_spaces(self):
    #     """Test code with leading/trailing spaces"""
    #     text = "before `  code  ` after"
    #     result = BaseMetric._extract_from_markdown(text)
    #     self.assertEqual(result['code'], 'code')  # should strip spaces
    #     self.assertEqual(result['text'], text)

    # def test_multiline_inline_code(self):
    #     """Test multiline inline code (should not match)"""
    #     text = "`line1\nline2`"
    #     result = BaseMetric._extract_from_markdown(text)
    #     self.assertEqual(result['code'], '')  # should not match multiline inline code
    #     self.assertEqual(result['text'], text)  # preserve as-is

    def test_indent_code_block(self):
        """Test indented code block"""
        text = """
I have the following string: `"aaaabbbb"`
How can I get the last four characters and store them in a string using Python?
Like this:
    
    print("hello world")
    print("hi")

        """

        result = BaseMetric._extract_from_markdown(text)

        # Verify extracted code
        expected_code = ("""
"aaaabbbb"
print("hello world")
print("hi")
        """)
        self.assertEqual(result['code'], expected_code.strip())
        self.assertEqual(result['formula'], '')


if __name__ == '__main__':
    unittest.main()
