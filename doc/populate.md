# Populate

Populate allows you to write a simple population guide for you board in markdown
and automatically convert to either a webpage with images or a markdown files
with images suitable for GitHub wiki.

It allows you to write text, incrementally add new components to the board and
highlight newly added components.

## Dependencies

Populate requires PcbDraw and also modules `mistune` and `py3bar`. If you
also want to use feature to convert images from vector to bitmap, you need Caira
and Rsvg.

## Usage

Usage of Populate is simple, just run:

```.{bash}
./populate.py <source_file> <output_directory>
```
- `source_file` is a markdown source code with a yaml header defining the guide
- `output_directory` is the directory for generated files. It will generate a
  single `index.{md|html}` file and bunch of images (possible in a nested
  directory).

Additionally you can pass following arguments:

- `--params <parameters>` any command line parameters for PcbDraw (e.g. remap
  file, style, etc.)
- `--board <board>` KiCad board used for images
- `--libs <libraries>` libraries for PcbDraw. Comma separated list of paths
- `--type (md|html)` specify output format - HTML or markdown
- `--img_name <teamplate>` name for generated images. It should contain one
  python formatting section. E.g. `img/pupulate_img_{}.svg`. Possible formats
  are SVG and PNG.
- `--template` handlebars file with a HTML web page template. Required only for
  HTML output.

All of these parameters are required, however you can specify them inside the
source file. See the following section.

## Source file format

The source file format is a simple markdown file with two specialties -- each
list item is considered as a single step in populating and will generate an
image. The content of the item is the step description. See
[example](../examples/populate/source_html.md).

To specify which side of the board and which components to add and highlight start the item with a clause in form:

```
- [[<front|back> | <comma separated list of components to add> ]]
```

For example:

- `[[front | R1,R2 ]]` will render front side of the board and adds R1 and R2.
- `[[back | ]]` will render the back side and no components will be added

The source file can feature a header, where you can specify all the other options like which board to use. The header can look like this:

```{.yaml}
---
params:
    - --style mystyle.json
    - --remap remapping.json
img_name: img/populating_{}.png
template: ../../templates/simple.handlebars
type: html
board: ../ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
libs: ../PcbDraw-Lib/KiCAD-base
...
```

All the options are specified without leading `-- ` and use the full argument
name. All paths except img_name are either absolute or relative to the source
file.

## Handlebars template

To specify HTML output you can use a [Handlebar](https://handlebarsjs.com/)
template. The template is fed with a data structure like this:

```{.json}
{
    "items": [
        {
            "type": "comment",
            "is_comment": true,
            "content": "Generated HTML from markdown of the comment"
        },
        {
            "type": "step",
            "is_step": true,
            "steps": [
                {
                    "img": "path to generated image",
                    "comment": "Generated HTML from markdown of the comment"
                }
            ]
        }
    ]
}
```

There can be multiple `step` and `comment` sections.