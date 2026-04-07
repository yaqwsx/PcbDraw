#!/usr/bin/env python3
from __future__ import annotations
import codecs
import os
import re
import shlex
import sys
from copy import deepcopy
from itertools import chain
from typing import List, Optional, Any, Tuple, Dict

import click
import pybars  # type: ignore
import yaml

import mistune
from mistune.plugins.footnotes import footnotes as plugin_footnotes
from mistune.plugins.table import table as plugin_table
from mistune.renderers.markdown import MarkdownRenderer

from .pcbnew_common import fakeKiCADGui
from .plot import find_data_file, get_global_datapaths

PKG_BASE = os.path.dirname(__file__)


def parse_pcbdraw(inline: Any, m: re.Match[str], state: Any) -> int:
    text = m.group("pcbdraw_content")
    side, components = text.split("|")
    components = [x.strip() for x in components.split(",")]
    state.append_token({
        "type": "pcbdraw",
        "raw": text,
        "attrs": {"side": side, "components": components},
    })
    return m.end()


PCBDRAW_PATTERN = (
    r"\[\["                               # [[
    r"(?P<pcbdraw_content>[\s\S]+?\|[\s\S]+?)"  # side| component
    r"\]\](?!\])"                         # ]]
)


def pcbdraw_plugin(md: mistune.Markdown) -> None:
    md.inline.register("pcbdraw", PCBDRAW_PATTERN, parse_pcbdraw, before="link")


def Renderer(base_cls: type, initial_components: List[str]) -> Any:
    """
    Create a renderer instance that tracks assembly steps.

    For HTMLRenderer: methods receive simple text args.
    For MarkdownRenderer: methods receive (token, state) args.
    """
    if base_cls is mistune.HTMLRenderer:
        return _HtmlStepRenderer(initial_components)
    else:
        return _MarkdownStepRenderer(initial_components)


class _StepRendererMixin:
    """Common state tracking for both HTML and Markdown renderers."""

    def __init__(self, initial_components: List[str]) -> None:
        self.items: List[Dict[str, Any]] = []
        self.current_item: Optional[Dict[str, Any]] = None
        self.active_side: str = "front"
        self.visited_components: List[str] = list(initial_components)
        self.active_components: List[str] = []

    def append_comment(self, html: str) -> None:
        if self.current_item is not None and self.current_item["type"] == "steps":
            self.items.append(self.current_item)
        if self.current_item is None or self.current_item["type"] == "steps":
            self.current_item = {
                "is_comment": True,
                "type": "comment",
                "content": ""
            }
        self.current_item["content"] += html

    def append_step(self, step: Dict[str, Any]) -> None:
        if self.current_item is not None and self.current_item["type"] == "comment":
            self.items.append(self.current_item)
        if self.current_item is None or self.current_item["type"] == "comment":
            self.current_item = {
                "is_step": True,
                "type": "steps",
                "steps": []
            }
        self.current_item["steps"].append(step)

    def output(self) -> List[Dict[str, Any]]:
        items = list(self.items)
        if self.current_item is not None:
            items.append(self.current_item)
        return items

    def handle_pcbdraw(self, side: str, components: List[str]) -> None:
        self.active_side = side
        self.visited_components += components
        self.active_components = components

    def handle_step(self, text: str) -> None:
        step = {
            "side": self.active_side,
            "components": list(self.visited_components),
            "active_components": list(self.active_components),
            "comment": text,
        }
        self.append_step(deepcopy(step))


class _HtmlStepRenderer(_StepRendererMixin, mistune.HTMLRenderer):
    """Renderer for HTML output that tracks assembly steps."""

    def __init__(self, initial_components: List[str]) -> None:
        _StepRendererMixin.__init__(self, initial_components)
        mistune.HTMLRenderer.__init__(self)

    def pcbdraw(self, text: str, side: str = "", components: Optional[List[str]] = None) -> str:
        self.handle_pcbdraw(side, components or [])
        return ""

    def block_code(self, code: str, info: Optional[str] = None) -> str:
        retval = super().block_code(code, info)
        self.append_comment(retval)
        return retval

    def block_quote(self, text: str) -> str:
        retval = super().block_quote(text)
        self.append_comment(retval)
        return retval

    def block_html(self, html: str) -> str:
        retval = super().block_html(html)
        self.append_comment(retval)
        return retval

    def heading(self, text: str, level: int, **attrs: Any) -> str:
        retval = super().heading(text, level, **attrs)
        self.append_comment(retval)
        return retval

    def thematic_break(self) -> str:
        retval = super().thematic_break()
        self.append_comment(retval)
        return retval

    def list(self, text: str, ordered: bool, **attrs: Any) -> str:
        return ""

    def list_item(self, text: str) -> str:
        self.handle_step(text)
        return ""

    def paragraph(self, text: str) -> str:
        retval = super().paragraph(text)
        self.append_comment(retval)
        return retval

    def table(self, text: str) -> str:  # type: ignore[override]
        # table() is registered by the table plugin, not on the base class
        self.append_comment(text)
        return text


class _MarkdownStepRenderer(_StepRendererMixin, MarkdownRenderer):
    """Renderer for Markdown output that tracks assembly steps."""

    def __init__(self, initial_components: List[str]) -> None:
        _StepRendererMixin.__init__(self, initial_components)
        MarkdownRenderer.__init__(self)

    def pcbdraw(self, token: Dict[str, Any], state: Any) -> str:
        attrs = token.get("attrs", {})
        self.handle_pcbdraw(attrs.get("side", ""), attrs.get("components", []))
        return ""

    def block_code(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().block_code(token, state)
        self.append_comment(retval)
        return retval

    def block_quote(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().block_quote(token, state)
        self.append_comment(retval)
        return retval

    def block_html(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().block_html(token, state)
        self.append_comment(retval)
        return retval

    def heading(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().heading(token, state)
        self.append_comment(retval)
        return retval

    def thematic_break(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().thematic_break(token, state)
        self.append_comment(retval)
        return retval

    def list(self, token: Dict[str, Any], state: Any) -> str:
        # Process children to trigger list_item calls
        children = token.get("children", [])
        for child in children:
            self.render_token(child, state)
        return ""

    def list_item(self, token: Dict[str, Any], state: Any) -> str:
        children = token.get("children", [])
        text = self.render_children(token, state)
        self.handle_step(text)
        return ""

    def paragraph(self, token: Dict[str, Any], state: Any) -> str:
        retval = super().paragraph(token, state)
        self.append_comment(retval)
        return retval


def load_content(filename: str) -> Tuple[Optional[Dict[str, Any]], str]:
    header = None
    with codecs.open(filename, encoding="utf-8") as f:
        content = f.read()
        if content.startswith("---"):
            end = content.find("...")
            if end != -1:
                header = yaml.safe_load(content[3:end])
                content = content[end+3:]
    return header, content

def parse_content(renderer: Any, content: str) -> List[Dict[str, Any]]:
    processor = mistune.Markdown(
        renderer=renderer,
        plugins=[pcbdraw_plugin, plugin_table, plugin_footnotes],
    )
    processor(content)
    return renderer.output()  # type: ignore[no-any-return]

def read_template(filename: str) -> str:
    with codecs.open(filename, encoding="utf-8") as f:
        return f.read()

def generate_html(template: str, input: List[Dict[str, Any]]) -> bytes:
    input_dict = {
        "items": input
    }
    template_fn = pybars.Compiler().compile(template)
    return template_fn(input_dict).encode("utf-8")  # type: ignore

def generate_markdown(input: List[Dict[str, Any]]) -> bytes:
    output = ""
    for item in input:
        if item["type"] == "comment":
            output += item["content"] + "\n"
        else:
            for x in item["steps"]:
                output += "#### " + x["comment"] + "\n\n"
                output += "![step](" + x["img"] + ")\n\n"
    return output.encode("utf-8")


def generate_images(content: List[Dict[str, Any]], boardfilename: str,
                    plot_args: List[str], name: str, outdir: str) -> List[Dict[str, Any]]:
    dir = os.path.dirname(os.path.join(outdir, name))
    if not os.path.exists(dir):
        os.makedirs(dir)
    counter = 0
    for item in content:
        if item["type"] != "steps":
            continue
        for x in item["steps"]:
            counter += 1
            filename = name.format(counter)
            generate_image(boardfilename, x["side"], x["components"],
                x["active_components"], plot_args, os.path.join(outdir, filename))
            x["img"] = filename
    return content

def generate_image(boardfilename: str, side: str, components: List[str],
                   active: List[str], plot_args: List[str], outputfile: str) -> None:
    from copy import deepcopy

    from .ui import plot

    plot_args = deepcopy(plot_args)

    if side.startswith("back"):
        plot_args += ["--side", "back"]
    plot_args += ["--filter", ",".join(components)]
    plot_args += ["--highlight", ",".join(active)]
    plot_args += [boardfilename, outputfile]
    try:
        plot.main(args=plot_args)
    except SystemExit as e:
        if e.code is not None and e.code != 0:
            raise e from None

def get_data_path() -> List[str]:
    paths: List[str] = []
    paths += filter(lambda x: len(x) > 0, os.environ.get("PCBDRAW_LIB_PATH", "").split(":"))
    paths += [os.path.join(PKG_BASE, "resources")]
    paths += get_global_datapaths()
    return paths

def prepare_params(params: List[str]) -> List[str]:
    p = [shlex.split(x) for x in params]
    return list(chain(*p))

@click.command()
@click.argument("input", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("output", type=click.Path(file_okay=False, dir_okay=True))
@click.option("--board", "-b", type=click.Path(exists=True, file_okay=True, dir_okay=False),
    default=None, help="override input board")
@click.option("--imgname", "-t", type=str, default=None,
    help="overide image name template, should contain exactly one {{}}")
@click.option("--template", "-t", type=str, default=None,
    help="override handlebars template for HTML output")
@click.option("--type", "-t", type=click.Choice(["md", "html"]), default=None,
    help="override output type: markdown or HTML")
def populate(input: str, output: str, board: Optional[str], imgname: Optional[str],
             template: Optional[str], type: Optional[str]) -> None:
    """
    Create assembly step-by-step guides
    """

    app = fakeKiCADGui()

    data_path = get_data_path()
    try:
        header, content = load_content(input)
    except IOError:
        sys.exit("Cannot open source file " + input)

    # We change board and output paths to absolute; then we change working
    # directory to the input file so we resolve everything according to it
    if board is not None:
        board = os.path.realpath(board)
    outputpath = os.path.realpath(output)
    input_dir = os.path.dirname(input)
    if input_dir != '':
        os.chdir(input_dir)

    # If no overriding is specified, load it from the template
    try:
        if board is None:
            if header is None:
                raise KeyError("board")
            board = header["board"]
        if imgname is None:
            if header is None:
                raise KeyError("imgname")
            imgname = header["imgname"]
        if type is None:
            if header is None:
                raise KeyError("type")
            type = header["type"]
        if template is None and type == "html":
            if header is None:
                raise KeyError("template")
            template = header["template"]
    except KeyError as e:
        sys.exit(f"Missing parameter {e} either in template file or source header")

    assert header is not None
    if type == "html":
        renderer = Renderer(mistune.HTMLRenderer, header.get("initial_components", []))
        outputfile = "index.html"
        try:
            assert template is not None
            template_file = find_data_file(template, '.handlebars', data_path, "templates")
            if template_file is None:
                raise RuntimeError(f"Cannot find template '{template}'")
            template = read_template(template_file)
        except IOError:
            sys.exit("Cannot open template file " + str(template))
    else:
        renderer = Renderer(MarkdownRenderer, header.get("initial_components", []))
        outputfile = "index.md"
    parsed_content = parse_content(renderer, content)
    parsed_content = generate_images(parsed_content, board, prepare_params(header["params"]),
                                     imgname, outputpath)
    if type == "html":
        assert template is not None
        output_content = generate_html(template, parsed_content)
    else:
        output_content = generate_markdown(parsed_content)

    with open(os.path.join(outputpath, outputfile), "wb") as f:
        f.write(output_content)

if __name__ == '__main__':
    populate()
