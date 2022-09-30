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
import mistune # type: ignore
# The following try-catch is used to support mistune 0.8.4 and 2.x
try:
    from mistune.plugins.table import plugin_table # type: ignore
    from mistune.plugins.footnotes import plugin_footnotes # type: ignore
    InlineParser = mistune.inline_parser.InlineParser
    HTMLRenderer = mistune.renderers.HTMLRenderer
except ModuleNotFoundError:
    InlineParser = mistune.InlineLexer
    HTMLRenderer = mistune.Renderer
import pybars # type: ignore
import yaml

import pcbdraw.mdrenderer

from .pcbnew_common import fakeKiCADGui
from .plot import find_data_file, get_global_datapaths

PKG_BASE = os.path.dirname(__file__)

def parse_pcbdraw(lexer: Any, m: re.Match[str], state: Any=None) -> Any:
    text = m.group(1)
    side, components = text.split("|")
    components = list(map(lambda x: x.strip(), components.split(",")))
    return 'pcbdraw', side, components

class PcbDrawInlineLexer(InlineParser): # type: ignore
    def __init__(self, renderer: Any, **kwargs: Any) -> None:
        super(PcbDrawInlineLexer, self).__init__(renderer, **kwargs)
        self.enable_pcbdraw()

    def enable_pcbdraw(self) -> None:
        pcbdraw_pattern = (
            r"\[\["                   # [[
            r"([\s\S]+?\|[\s\S]+?)"   # side| component
            r"\]\](?!\])"             # ]]
        )
        if hasattr(self, 'register_rule'):
            # mistune v2 API
            self.rules.insert(3, 'pcbdraw')
            self.register_rule('pcbdraw', pcbdraw_pattern, parse_pcbdraw)
        else:
            # mistune v0.8.4
            self.rules.pcbdraw = re.compile(pcbdraw_pattern)
            self.default_rules.insert(3, 'pcbdraw')

    # This method is invoked by the old mistune API (i.e. v0.8.4)
    # For the new API we register `parse_pcbdraw`
    def output_pcbdraw(self, m: re.Match[str]) -> Any:
        _, side, components = parse_pcbdraw(self, m)
        return self.renderer.pcbdraw(side, components)


def Renderer(BaseRenderer, initial_components: List[str]): # type: ignore
    class Tmp(BaseRenderer): # type: ignore
        def __init__(self, initial_components: List[str]) -> None:
            super(Tmp, self).__init__(escape=False)
            self.items: List[Dict[str, Any]]= []
            self.current_item: Optional[Dict[str, Any]] = None
            self.active_side: str = "front"
            self.visited_components: List[str] = initial_components
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
            items = self.items
            if self.current_item is not None:
                items.append(self.current_item)
            return items

        def pcbdraw(self, side: str, components: List[str]) -> str:
            self.active_side = side
            self.visited_components += components
            self.active_components = components
            return ""

        def block_code(self, children: str, info: Optional[str]=None) -> Any:
            retval = super(Tmp, self).block_code(children, info)
            self.append_comment(retval)
            return retval

        def block_quote(self, text: str) -> Any:
            retval = super(Tmp, self).block_quote(text)
            self.append_comment(retval)
            return retval

        def block_html(self, html: str) -> Any:
            retval = super(Tmp, self).block_html(html)
            self.append_comment(retval)
            return retval

        def heading(self, children: str, level: int) -> Any:
            retval = super(Tmp, self).heading(children, level)
            self.append_comment(retval)
            return retval

        # Mistune 0.8.4 API
        def header(self, text: str, level: int, raw: Optional[str]=None) -> Any:
            retval = super(Tmp, self).header(text, level, raw)
            self.append_comment(retval)
            return retval

        # Mistune 0.8.4 API
        def hrule(self) -> Any:
            retval = super(Tmp, self).hrule()
            self.append_comment(retval)
            return retval

        def thematic_break(self) -> Any:
            retval = super(Tmp, self).thematic_break()
            self.append_comment(retval)
            return retval

        def list(self, text: Any, ordered: bool, level: Any=None, start: Any=None) -> str:
            return ""

        def list_item(self, text: str, level: Any=None) -> str:
            step = {
                "side": self.active_side,
                "components": self.visited_components,
                "active_components": self.active_components,
                "comment": text
            }
            self.append_step(deepcopy(step))
            return ""

        def paragraph(self, text: str) -> Any:
            retval = super(Tmp, self).paragraph(text)
            self.append_comment(retval)
            return retval

        def table(self, header: str, body: str) -> Any:
            retval = super(Tmp, self).table(header, body)
            self.append_comment(retval)
            return retval
    return Tmp(initial_components)

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
    lexer = PcbDrawInlineLexer(renderer)
    processor = mistune.Markdown(renderer=renderer, inline=lexer)
    try:
        plugin_table(processor)
        plugin_footnotes(processor)
    except NameError:
        # Mistune v0.8.4 doesn't define the above functions
        pass
    processor(content)
    return renderer.output() # type: ignore

def read_template(filename: str) -> str:
    with codecs.open(filename, encoding="utf-8") as f:
        return f.read()

def generate_html(template: str, input: List[Dict[str, Any]]) -> bytes:
    input_dict = {
        "items": input
    }
    template_fn = pybars.Compiler().compile(template)
    return template_fn(input_dict).encode("utf-8") # type: ignore

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
    paths += [os.path.join(PKG_BASE, "resources", "templates")]
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

    if type == "html":
        renderer = Renderer(HTMLRenderer, header.get("initial_components", [])) # type: ignore
        outputfile = "index.html"
        try:
            assert template is not None
            template_file = find_data_file(template, '.handlebars', data_path)
            if template_file is None:
                raise RuntimeError(f"Cannot find template '{template}'")
            template = read_template(template_file)
        except IOError:
            sys.exit("Cannot open template file " + str(template))
    else:
        renderer = Renderer(pcbdraw.mdrenderer.MdRenderer, header.get("initial_components", [])) # type: ignore
        outputfile = "index.md"
    parsed_content = parse_content(renderer, content)
    if header is None:
        raise RuntimeError("Parameters were not specified in the template")
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
