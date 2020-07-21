# Examples

To use any of the examples, simply run `./init.sh` in the examples directory.
The script will download a simple demo board by RoboticsBrno.


# Example usages of PcbDraw

All the examples assumes the current directory is the root of the repository.

To render the board invoke:

```
pcbdraw examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```

To render board, but e.g. change colors of LEDs:

```
pcbdraw --remap examples/pcbdraw/remap.json examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```

To render the back side:

```
pcbdraw -b examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb back.svg
```

To use different style:

```
pcbdraw --style oshpark-purple examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```

To render only the board without components:

```
pcbdraw --filter "" examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```

To render board with only `L_R1` and `L_Y1`:

```
pcbdraw --filter L_R1,L_Y1 examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```

To render board and highlight `L_R1` and `L_Y1`:

```
pcbdraw --highlight L_R1,L_Y1 examples/ArduinoLearningKitStarter/ArduinoLearningKitStarter.kicad_pcb front.svg
```


## Populate

There are two example for the populate - HTML one and a Mardown one. They are
the same and are located in files `source_md.md` and `source_html.md`. To see
the result, run

```
populate examples/populate/source_md.md markdown_demo
```
or
```
populate examples/populate/source_html.md html_demo
```

You can find results
in the directories `markdown_demo` and `html_demo` respectively.

