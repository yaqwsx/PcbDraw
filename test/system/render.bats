#!/usr/bin/env bats

load common

@test "Render with default PNG" {
    run pcbdraw render \
        $EXAMPLES/resources/ArduinoLearningKitStarter.kicad_pcb front.png
    [ "$status" -eq 0 ]
}
