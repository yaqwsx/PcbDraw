#!/usr/bin/env bats

load common

@test "Render with default PNG" {
    pcbdraw render \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.png
}
