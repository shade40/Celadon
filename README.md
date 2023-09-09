![Celadon](https://singlecolorimage.com/get/afe1af/1600x200)

## Celadon

A modern TUI library taking the right lessons from the web.

```
pip install sh40-celadon
```

![rule](https://singlecolorimage.com/get/afe1af/1600x3)

### Development Note

Since the project is in early stages a lot of optimization remains on
the table. It already runs well on most machines, but certain domains
(such as styling & layouts) might hog older computers.

This will be remedied in the future, once the related framework is in
place to allow for more generalized testing.

![rule](https://singlecolorimage.com/get/afe1af/1600x3)

### Purpose

`Celadon` is a _library_ for creating good looking and performant
UIs in the terminal. While it _is_ possible to use standalone,
you generally wanna use it through a _framework_ like [celx]().

### Feature highlights

#### YAML Styling

`Celadon` includes a powerful CSS-inspired engine for styling your
applications. It supports your basic `#id`, `.group` (`.class` in CSS
land) selector primitives, as well as direct (`Parent > Widget`) and
indirect hierarchal matching (`Parent *> Widget`, where `Widget` is a
part of `Parent` but not necessarily a first-degree descendant).

It replaces CSS' notion of a 'pseudoclass' with a more direct notion
of widget _state_, controlled by a state machine internal to all widgets.

```yaml
Button:
  fill_style: '@ui.primary'
  content_style: '' # Automatically use either white or black, based on the W3C contrast guidelines

  # On hover, become a bit brighter
  /hover: # Equivalent to 'Button/hover'
    fill_style: '@ui.primary+1'

  # Become a bit taller if in the 'big' group
  .big:
    height: 3

  # If part of a Row in the 'button-row' group, fill available width
  Row.button-row > &:
    width: null
```

#### A great layout system

Layouts are one of the biggest difficulties in any UI environment,
especially on the web. We try to solve most of these issues by stripping
down the amount of settings _you_ need to be aware of (no more "`align-items`
or `justify-items`?") and controlling almost all layout parameters within
widget dimension settings.

A dimension can be one of three types:

- `int`: Sets a static size, i.e. `button.width = 5` will make that button
    take up 5 cells of space horizontally, regardless of its parent's size.
- `float`: Sets a relative size to the parent's size of the same dimension,
    i.e. `button.width = 0.5` will make the button be half the width of the
    parent.
- `None`: Sets a so-called `fill` height, meaning the parent will divide
    its space remaining after sizing the widgets with the previous two
    dimension types, and divide it evenly amongst the `fill` sized.

**Exhibit A: Traditional 'web' Header-Body-Footer layout**

```py
page = Page(
  Tower(
    Row(Text("I mimick the web"), Text("For it cannot mimick me"), eid="header"),
    Tower(eid="body"),
    Row(Button("Ctrl-C : Quit"), Button("F12 : Screenshot"), eid="footer")
  ),
  rules="""
  Row#header, Tower#footer:
    height: 10
"""
)
```

Here, specifying a static dimension for both header and footer's height
allows the body to fill up the remaining space, and not specifying a width
for either (leaving it to the default `None`) makes them take up the entire
width.

**Exhibit B: N*K grid**

By making use of the `fill` dimension type, we can create responsive grids
that work regardless of the amount of widgets we have in each column / row.

```py
grid = Tower(eid="grid")

for _ in range(rows):
  grid += Row(*[Button("Grid Item") for _ in range(cols)])

page = Page(
  grid,
  rules="""
  Tower#grid *> Button:
    width: null
    height: null  
"""
)
```
    
