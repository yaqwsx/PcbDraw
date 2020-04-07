# Example usages of PcbDraw

To render the board invoke:

```
./pcbdraw
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```

To render board, but e.g. change colors of LEDs:

```
./pcbdraw --remap remap.json
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```

To render the back side:

```
./pcbdraw -b
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    back.svg
```

To use different style:

```
./pcbdraw --style styles/oshpark-purple.json
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```

To render only the board without components:

```
./pcbdraw --filter ""
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```

To render board with only `L_R1` and `L_Y1`:

```
./pcbdraw --filter L_R1,L_Y1
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```

To render board and highlight `L_R1` and `L_Y1`:

```
./pcbdraw --highlight L_R1,L_Y1
    examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb
    front.svg
```


