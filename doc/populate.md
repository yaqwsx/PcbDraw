# Populate

Populate allows you to write a simple population guide for you board in markdown
and automatically convert to either a webpage with images or a markdown files
with images suitable for GitHub wiki.

It allows you to write text, incrementally add new components to the board and
highlight newly added components.


## Usage

Populate is invoked via `pcbdraw populate <specification> <output_directory>`.
It takes the following options to override some of the parameters specified
in the specification file:

- `-b, --board FILE` override input board
- `-t, --imgname TEXT` override image name template, should contain exactly one {}
- `-t, --template TEXT` override handlebars template for HTML output
- `-t, --type [md|html]` override output type: markdown or HTML


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
imgname: img/populating_{}.png
template: simple
type: html
board: ../ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
libs: KiCAD-6
initial_components:
    - C1
    - R13
...
```

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
