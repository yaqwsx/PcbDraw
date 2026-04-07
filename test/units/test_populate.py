"""Tests for the populate module's mistune 3 integration."""

import mistune
from mistune.renderers.markdown import MarkdownRenderer

from pcbdraw.populate import (
    Renderer,
    parse_content,
    load_content,
    pcbdraw_plugin,
    PCBDRAW_PATTERN,
)


class TestPcbDrawSyntaxParsing:
    """Test that the [[side|components]] syntax is parsed correctly."""

    def test_pattern_matches(self):
        import re
        m = re.search(PCBDRAW_PATTERN, "[[front|R1,R2]]")
        assert m is not None
        assert m.group(1) == "front|R1,R2"

    def test_pattern_back_side(self):
        import re
        m = re.search(PCBDRAW_PATTERN, "[[back|C1, C2, C3]]")
        assert m is not None
        assert m.group(1) == "back|C1, C2, C3"

    def test_pattern_no_match_single_bracket(self):
        import re
        m = re.search(PCBDRAW_PATTERN, "[front|R1]")
        assert m is None


def _steps(result):
    """Extract step blocks from parse result."""
    return [r for r in result if r["type"] == "steps"]


def _comments(result):
    """Extract non-empty comment blocks from parse result."""
    return [r for r in result if r["type"] == "comment" and r["content"].strip()]


class TestHtmlRenderer:
    def test_basic_step(self):
        renderer = Renderer(mistune.HTMLRenderer, [])
        content = "[[front|R1,R2]]\n\n- Solder R1 and R2\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        assert len(steps) == 1
        assert len(steps[0]["steps"]) == 1
        step = steps[0]["steps"][0]
        assert step["side"] == "front"
        assert "R1" in step["components"]
        assert "R2" in step["components"]
        assert "R1" in step["active_components"]
        assert "R2" in step["active_components"]

    def test_comment_then_step(self):
        renderer = Renderer(mistune.HTMLRenderer, [])
        content = "# Header\n\n[[front|R1]]\n\n- Do something\n"
        result = parse_content(renderer, content)
        comments = _comments(result)
        steps = _steps(result)
        assert len(comments) >= 1
        assert any("<h1>" in c["content"] for c in comments)
        assert len(steps) == 1

    def test_initial_components_carried(self):
        renderer = Renderer(mistune.HTMLRenderer, ["C1", "C2"])
        content = "[[front|R1]]\n\n- Step one\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        step = steps[0]["steps"][0]
        assert "C1" in step["components"]
        assert "C2" in step["components"]
        assert "R1" in step["components"]

    def test_multiple_steps(self):
        renderer = Renderer(mistune.HTMLRenderer, [])
        content = "[[front|R1]]\n\n- Step one\n- Step two\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        assert len(steps) == 1
        assert len(steps[0]["steps"]) == 2

    def test_back_side(self):
        renderer = Renderer(mistune.HTMLRenderer, [])
        content = "[[back|U1]]\n\n- Solder IC\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        assert steps[0]["steps"][0]["side"] == "back"

    def test_cumulative_components(self):
        renderer = Renderer(mistune.HTMLRenderer, [])
        content = "[[front|R1]]\n\n- Step one\n\n[[front|R2]]\n\n- Step two\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        assert len(steps) == 2
        step2 = steps[1]["steps"][0]
        assert "R1" in step2["components"]
        assert "R2" in step2["components"]
        assert step2["active_components"] == ["R2"]


class TestMarkdownRenderer:
    def test_basic_step(self):
        renderer = Renderer(MarkdownRenderer, [])
        content = "[[front|R1,R2]]\n\n- Solder R1 and R2\n"
        result = parse_content(renderer, content)
        steps = _steps(result)
        assert len(steps) == 1
        step = steps[0]["steps"][0]
        assert step["side"] == "front"
        assert "R1" in step["components"]

    def test_comment_then_step(self):
        renderer = Renderer(MarkdownRenderer, [])
        content = "# Header\n\n[[front|R1]]\n\n- Do something\n"
        result = parse_content(renderer, content)
        comments = _comments(result)
        steps = _steps(result)
        assert len(comments) >= 1
        assert len(steps) == 1


class TestLoadContent:
    def test_with_yaml_header(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\nboard: test.kicad_pcb\ntype: html\n...\n# Hello\n")
        header, content = load_content(str(f))
        assert header is not None
        assert header["board"] == "test.kicad_pcb"
        assert "# Hello" in content

    def test_without_header(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Just markdown\n\nSome text.\n")
        header, content = load_content(str(f))
        assert header is None
        assert "# Just markdown" in content
