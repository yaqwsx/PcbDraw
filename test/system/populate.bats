#!/usr/bin/env bats

load common

@test "Populate markdown" {
    pcbdraw populate \
        $EXAMPLES/populate/source_md.md markdown_demo
}

@test "Populate HTML" {
    pcbdraw populate \
        $EXAMPLES/populate/source_html.md html_demo
}
