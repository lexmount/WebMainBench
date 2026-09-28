import unittest

from webmainbench.metrics.calculator import MetricCalculator


class TestReferenceDefinedMetricPopulation(unittest.TestCase):
    def setUp(self):
        self.calculator = MetricCalculator({"use_llm": False})

    def test_prediction_only_special_content_does_not_expand_population(self):
        result = self.calculator.calculate_all(
            predicted_content="`invented()`\n\n$x$\n\n| a |\n|---|\n| b |",
            groundtruth_content="plain reference text",
        )
        for metric in ("code_edit", "formula_edit", "table_edit", "table_TEDS"):
            with self.subTest(metric=metric):
                self.assertFalse(result[metric].success)
        self.assertTrue(result["text_edit"].success)

    def test_missing_prediction_scores_zero_inside_reference_population(self):
        result = self.calculator.calculate_all(
            predicted_content="plain prediction",
            groundtruth_content=(
                "use `expected()` and $x$\n\n"
                "| a |\n|---|\n| b |"
            ),
        )
        for metric in ("code_edit", "formula_edit", "table_edit", "table_TEDS"):
            with self.subTest(metric=metric):
                self.assertTrue(result[metric].success)
                self.assertEqual(result[metric].score, 0.0)


if __name__ == "__main__":
    unittest.main()
