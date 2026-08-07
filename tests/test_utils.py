"""
Unit tests for renderers/utils.py
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from renderers.utils import escape_latex, format_address


class TestEscapeLatex(unittest.TestCase):
    """Test LaTeX special character escaping."""

    def test_escape_ampersand(self):
        """Ampersand should be escaped."""
        self.assertEqual(escape_latex("AT&T"), "AT\\&T")

    def test_escape_percent(self):
        """Percent should be escaped."""
        self.assertEqual(escape_latex("100%"), "100\\%")

    def test_escape_dollar(self):
        """Dollar sign should be escaped."""
        self.assertEqual(escape_latex("$100"), "\\$100")

    def test_escape_hash(self):
        """Hash should be escaped."""
        self.assertEqual(escape_latex("#tag"), "\\#tag")

    def test_escape_underscore(self):
        """Underscore should be escaped."""
        self.assertEqual(escape_latex("variable_name"), "variable\\_name")

    def test_escape_curly_braces(self):
        """Curly braces should be escaped."""
        self.assertEqual(escape_latex("{value}"), "\\{value\\}")

    def test_escape_tilde(self):
        """Tilde should be escaped."""
        self.assertEqual(escape_latex("~"), "\\textasciitilde{}")

    def test_escape_caret(self):
        """Caret should be escaped."""
        self.assertEqual(escape_latex("^"), "\\textasciicircum{}")

    def test_escape_backslash(self):
        """Backslash should be escaped."""
        self.assertEqual(escape_latex("\\path"), "\\textbackslash{}path")

    def test_escape_backslash_before_special(self):
        """Backslash before special char should escape the char."""
        self.assertEqual(escape_latex("\\&"), "\\&")

    def test_escape_curly_quotes(self):
        """Curly quotes should be converted to LaTeX quotes."""
        self.assertEqual(escape_latex("\u201chello\u201d"), "``hello''")
        self.assertEqual(escape_latex("\u2018hello\u2019"), "`hello'")

    def test_escape_em_dash(self):
        """Em dash should be converted to LaTeX dash."""
        self.assertEqual(escape_latex("—"), "---")

    def test_escape_en_dash(self):
        """En dash should be converted to LaTeX dash."""
        self.assertEqual(escape_latex("–"), "--")

    def test_escape_non_breaking_space(self):
        """Non-breaking space should be converted to regular space."""
        self.assertEqual(escape_latex("hello\xa0world"), "hello world")

    def test_escape_multiple_special_chars(self):
        """Multiple special characters should all be escaped."""
        self.assertEqual(escape_latex("AT&T_100%"), "AT\\&T\\_100\\%")

    def test_escape_plain_text(self):
        """Plain text without special chars should remain unchanged."""
        self.assertEqual(escape_latex("Hello World"), "Hello World")

    def test_escape_empty_string(self):
        """Empty string should remain empty."""
        self.assertEqual(escape_latex(""), "")

    def test_escape_non_string(self):
        """Non-string input should be returned as-is."""
        self.assertEqual(escape_latex(123), 123)
        self.assertEqual(escape_latex(None), None)


class TestFormatAddress(unittest.TestCase):
    """Test address formatting for LaTeX and HTML."""

    def test_format_address_list_latex(self):
        """List address formatted for LaTeX."""
        address = ["123 Main St", "Apt 4B", "Berlin, 10115"]
        result = format_address(address, latex=True)
        self.assertEqual(result, "123 Main St \\\\\n  Apt 4B \\\\\n  Berlin, 10115")

    def test_format_address_list_html(self):
        """List address formatted for HTML."""
        address = ["123 Main St", "Apt 4B", "Berlin, 10115"]
        result = format_address(address, latex=False)
        self.assertEqual(result, "123 Main St<br/>Apt 4B<br/>Berlin, 10115")

    def test_format_address_string_latex(self):
        """String address formatted for LaTeX."""
        address = "123 Main St\nApt 4B\nBerlin, 10115"
        result = format_address(address, latex=True)
        self.assertEqual(result, "123 Main St \\\\\n  Apt 4B \\\\\n  Berlin, 10115")

    def test_format_address_string_html(self):
        """String address formatted for HTML."""
        address = "123 Main St\nApt 4B\nBerlin, 10115"
        result = format_address(address, latex=False)
        self.assertEqual(result, "123 Main St<br/>Apt 4B<br/>Berlin, 10115")

    def test_format_address_single_line_latex(self):
        """Single line address formatted for LaTeX."""
        address = "123 Main St"
        result = format_address(address, latex=True)
        self.assertEqual(result, "123 Main St")

    def test_format_address_single_line_html(self):
        """Single line address formatted for HTML."""
        address = "123 Main St"
        result = format_address(address, latex=False)
        self.assertEqual(result, "123 Main St")

    def test_format_address_empty_list_latex(self):
        """Empty list address formatted for LaTeX."""
        address = []
        result = format_address(address, latex=True)
        self.assertEqual(result, "")

    def test_format_address_empty_list_html(self):
        """Empty list address formatted for HTML."""
        address = []
        result = format_address(address, latex=False)
        self.assertEqual(result, "")

    def test_format_address_empty_string_latex(self):
        """Empty string address formatted for LaTeX."""
        address = ""
        result = format_address(address, latex=True)
        self.assertEqual(result, "")

    def test_format_address_empty_string_html(self):
        """Empty string address formatted for HTML."""
        address = ""
        result = format_address(address, latex=False)
        self.assertEqual(result, "")

    def test_format_address_with_special_chars_latex(self):
        """Address with special chars should be escaped for LaTeX."""
        address = ["AT&T Corp", "100% Building"]
        result = format_address(address, latex=True)
        self.assertIn("\\&", result)
        self.assertIn("\\%", result)

    def test_format_address_with_special_chars_html(self):
        """Address with special chars should not be escaped for HTML."""
        address = ["AT&T Corp", "100% Building"]
        result = format_address(address, latex=False)
        self.assertIn("&", result)
        self.assertIn("%", result)


if __name__ == '__main__':
    unittest.main()
