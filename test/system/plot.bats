#!/usr/bin/env bats

load common

@test "Plot with default SVG" {
    pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
}

@test "Plot with default PNG" {
    pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.png
}

@test "Plot with default JPG" {
    pcbdraw plot \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.jpg
}

@test "Plot with remap" {
    pcbdraw plot \
        --remap $EXAMPLES/resources/remap.json \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
}

@test "Plot with built-in style" {
    pcbdraw plot \
        --style oshpark-purple \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.svg
}
