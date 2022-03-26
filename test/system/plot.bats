#!/usr/bin/env bats

load common

@test "Plot with default SVG" {
    run pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
    [ "$status" -eq 0 ]
}

@test "Plot with default PNG" {
    run pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.png
    [ "$status" -eq 0 ]
}

@test "Plot with default JPG" {
    run pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.jpg
    [ "$status" -eq 0 ]
}

@test "Plot with remap" {
    run pcbdraw plot \
        --remap $EXAMPLES/resources/remap.json \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
    [ "$status" -eq 0 ]
}

@test "Plot with built-in style" {
    run pcbdraw plot \
        --style oshpark-purple \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
    [ "$status" -eq 0 ]
}
