#!/usr/bin/env python3
import sys
import os
import click
PKG_BASE = os.path.dirname(__file__)
# Give more priority to local modules than installed versions
sys.path.insert(0, os.path.dirname(os.path.abspath(PKG_BASE)))

import mistune
import pcbdraw.mdrenderer
import re
import codecs
import pybars
import yaml
import argparse
import subprocess
import sysconfig
import shlex
from copy import deepcopy
from typing import List, Optional
from itertools import chain

from .plot import get_global_datapaths, find_data_file
from .common import fakeKiCADGui

PKG_BASE = os.path.dirname(__file__)

class PcbDrawInlineLexer(mistune.InlineLexer):
    def __init__(self, renderer, rules=None, **kwargs):
        super(PcbDrawInlineLexer, self).__init__(renderer, rules=None, **kwargs)
        self.enable_pcbdraw()

    def enable_pcbdraw(self):
        self.rules.pcbdraw = re.compile(
            r"\[\["                   # [[
            r"([\s\S]+?\|[\s\S]+?)"   # side| component
            r"\]\](?!\])"             # ]]
        )
        self.default_rules.insert(3, "pcbdraw")

    def output_pcbdraw(self, m):
        text = m.group(1)
        side, components = text.split("|")
        components = list(map(lambda x: x.strip(), components.split(",")))
        return self.renderer.pcbdraw(side, components)

def Renderer(BaseRenderer):
    class Tmp(BaseRenderer):
        def __init__(self):
            super(Tmp, self).__init__(escape=False)
            self.items = []
            self.current_item = None
            self.active_side = "front"
            self.visited_components = []
            self.active_components = []

        def append_comment(self, html):
            if self.current_item is not None and self.current_item["type"] == "steps":
                self.items.append(self.current_item)
            if self.current_item is None or self.current_item["type"] == "steps":
                self.current_item = {
                    "is_comment": True,
                    "type": "comment",
                    "content": ""
                }
            self.current_item["content"] += html

        def append_step(self, step):
            if self.current_item is not None and self.current_item["type"] == "comment":
                self.items.append(self.current_item)
            if self.current_item is None or self.current_item["type"] == "comment":
                self.current_item = {
                    "is_step": True,
                    "type": "steps",
                    "steps": []
                }
            self.current_item["steps"].append(step)

        def output(self):
            items = self.items
            items.append(self.current_item)
            return items

        def pcbdraw(self, side, components):
            self.active_side = side
            self.visited_components += components
            self.active_components = components
            return ""

        def block_code(self, code, lang):
            retval = super(Tmp, self).block_code(code, lang)
            self.append_comment(retval)
            return retval

        def block_quote(self, text):
            retval = super(Tmp, self).block_quote(text)
            self.append_comment(retval)
            return retval

        def block_html(self, html):
            retval = super(Tmp, self).block_html(html)
            self.append_comment(retval)
            return retval

        def header(self, text, level, raw=None):
            retval = super(Tmp, self).header(text, level, raw)
            self.append_comment(retval)
            return retval

        def hrule(self):
            retval = super(Tmp, self).hrule()
            self.append_comment(retval)
            return retval

        def list(self, body, ordered=True):
            return ""

        def list_item(self, text):
            step = {
                "side": self.active_side,
                "components": self.visited_components,
                "active_components": self.active_components,
                "comment": text
            }
            self.append_step(deepcopy(step))
            return ""

        def paragraph(self, text):
            retval = super(Tmp, self).paragraph(text)
            self.append_comment(retval)
            return retval

        def table(self, header, body):
            retval = super(Tmp, self).table(header, body)
            self.append_comment(retval)
            return retval
    return Tmp()

def load_content(filename):
    header = None
    with codecs.open(filename, encoding="utf-8") as f:
        content = f.read()
        if content.startswith("---"):
            end = content.find("...")
            if end != -1:
                header = yaml.safe_load(content[3:end])
                content = content[end+3:]
    return header, content

def parse_content(renderer, content):
    lexer = PcbDrawInlineLexer(renderer)
    processor = mistune.Markdown(renderer=renderer, inline=lexer)
    processor(content)
    return renderer.output()

def read_template(filename):
    with codecs.open(filename, encoding="utf-8") as f:
        return f.read()

def generate_html(template, input):
    input = {
        "items": input
    }
    template = pybars.Compiler().compile(template)
    return template(input).encode("utf-8")

def generate_markdown(input):
    output = ""
    for item in input:
        if item["type"] == "comment":
            output += item["content"] + "\n"
        else:
            for x in item["steps"]:
                output += "#### " + x["comment"] + "\n\n"
                output += "![step](" + x["img"] + ")\n\n"
    return output.encode("utf-8")


def generate_images(content, boardfilename, plot_args, name, outdir):
    dir = os.path.dirname(os.path.join(outdir, name))
    if not os.path.exists(dir):
        os.makedirs(dir)
    counter = 0
    for item in content:
        if item["type"] == "comment":
            continue
        for x in item["steps"]:
            counter += 1
            filename = name.format(counter)
            generate_image(boardfilename, x["side"], x["components"],
                x["active_components"], plot_args, os.path.join(outdir, filename))
            x["img"] = filename
    return content

def generate_image(boardfilename, side, components, active, plot_args, outputfile):
    from .ui import plot
    from copy import deepcopy

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
    paths = []
    paths += filter(lambda x: len(x) > 0, os.environ.get("PCBDRAW_LIB_PATH", "").split(":"))
    paths += [os.path.join(PKG_BASE, "templates")]
    paths += get_global_datapaths()
    return paths

def prepare_params(params: List[str]) -> List[str]:
    params = [shlex.split(x) for x in params]
    return list(chain(*params))

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
def populate(input, output, board, imgname, template, type):
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
    os.chdir(os.path.dirname(input))

    # If no overriding is specified, load it from the template
    try:
        if board is None:
            board = header["board"]
        if imgname is None:
            imgname = header["imgname"]
        if template is None:
            template = header["template"]
        if type is None:
            type = header["type"]
    except KeyError as e:
        sys.exit(f"Missing parameter {e} either in template file of source header")

    if type == "html":
        renderer = Renderer(mistune.Renderer)
        outputfile = "index.html"
        try:
            template = read_template(find_data_file(template, '.handlebars', data_path))
        except IOError:
            sys.exit("Cannot open template file " + template)
    else:
        renderer = Renderer(pcbdraw.mdrenderer.MdRenderer)
        outputfile = "index.md"
    content = parse_content(renderer, content)
    content = generate_images(content, board, prepare_params(header["params"]),
                              imgname, output)
    if type == "html":
        output = generate_html(template, content)
    else:
        output = generate_markdown(content)

    with open(os.path.join(outputpath, outputfile), "wb") as f:
        f.write(output)

if __name__ == '__main__':
    populate()
