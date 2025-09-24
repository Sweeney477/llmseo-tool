from __future__ import annotations

import unittest

from llmseo.utils import normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_adds_scheme_and_trailing_slash_for_domain(self) -> None:
        self.assertEqual(normalize_url("example.com"), "https://example.com/")

    def test_preserves_path_when_scheme_missing(self) -> None:
        self.assertEqual(normalize_url("example.com/path"), "https://example.com/path")

    def test_keeps_query_parameters(self) -> None:
        self.assertEqual(normalize_url("example.com/path?x=1"), "https://example.com/path?x=1")

    def test_handles_localhost_with_port(self) -> None:
        self.assertEqual(normalize_url("localhost:8000/foo"), "https://localhost:8000/foo")

    def test_rejects_relative_paths(self) -> None:
        with self.assertRaises(ValueError):
            normalize_url("/just/a/path")

    def test_rejects_blank_values(self) -> None:
        with self.assertRaises(ValueError):
            normalize_url("   ")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
