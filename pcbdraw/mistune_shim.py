# type: ignore
import mistune

__all__ = [
    "BaseRenderer",
    "InlineParser",
    "HTMLRenderer",
    "plugin_table",
    "plugin_footnotes",
]


mistune_version = tuple(int(i) for i in mistune.__version__.split("."))
mistune_major_version = mistune_version[0]

if mistune_major_version == 3:
    from mistune.plugins.footnotes import footnotes as plugin_footnotes
    from mistune.plugins.table import table as plugin_table

    InlineParser = mistune.InlineParser
    HTMLRenderer = mistune.HTMLRenderer
    BaseRenderer = mistune.BaseRenderer
elif mistune_major_version == 2:
    from mistune.plugins.footnotes import plugin_footnotes
    from mistune.plugins.table import plugin_table

    InlineParser = mistune.inline_parser.InlineParser
    HTMLRenderer = mistune.renderers.HTMLRenderer
    BaseRenderer = mistune.renderers.BaseRenderer
elif mistune_major_version == 0:

    def _noop_processor(processor: mistune.Markdown) -> None:
        pass

    plugin_table = plugin_footnotes = _noop_processor
    InlineParser = mistune.InlineLexer
    HTMLRenderer = mistune.Renderer
    BaseRenderer = mistune.Renderer
else:
    raise Exception(f"Unsupported mistune version {mistune.__version__}")
