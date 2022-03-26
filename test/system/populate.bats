#!/usr/bin/env bats

load common

@test "Populate markdown" {
    run pcbdraw populate \
        $EXAMPLES/populate/source_md.md markdown_demo
    [ "$status" -eq 0 ]
}

@test "Populate HTML" {
    run pcbdraw populate \
        $EXAMPLES/populate/source_html.md html_demo
    [ "$status" -eq 0 ]
}
