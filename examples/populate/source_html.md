---
params:
    - --remap remap.json
    - --libs KiCAD-base
imgname: img/populating_{}.png
template: simple
type: html
board: ../resources/ArduinoLearningKitStarter.kicad_pcb
initial_components:
  - C1
  - R13
...

# Demo population manual

Lorem ipsum dolor sit amet, consectetuer adipiscing elit. Itaque earum rerum hic
tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias
consequatur aut perferendis doloribus asperiores repellat. Vestibulum fermentum
tortor id mi. Nulla turpis magna, cursus sit amet, suscipit a, interdum id,
felis.

- [[front | ]] This is the front side of the board we are populating
- [[back | ]] This is the back side of the board we are populating
- [[front | RV1, RV2 ]] First, populate RV1 and RV2. Basically, any description
  could be here.
- [[front | U2 ]] Let's populate U2!

You can put a paragraph of text between the population steps. Lorem ipsum dolor
sit amet, consectetuer adipiscing elit. Itaque earum rerum hic tenetur a
sapiente.

- [[back | R24 ]] We can also populate a component on the other side

## Conclusion

This is the end of the demo.
