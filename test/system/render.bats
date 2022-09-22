#!/usr/bin/env bats

load common

@test "Render with default PNG" {
    pcbdraw render \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb render_front.png
}

@test "Render back side" {
    pcbdraw render \
        --side back \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb render_front.png
}

@test "Render with transparent BG" {
    pcbdraw render \
        --transparent \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb render_front_t.png
}

@test "Render without components" {
    pcbdraw render \
        --no-components \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb render_front_no_comp.png
}
