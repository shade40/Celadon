![celadon](https://singlecolorimage.com/get/afe1af/1600x200)

## celadon

A state-driven UI library for the terminal.

```
pip install sh40-celadon
```

![rule](https://singlecolorimage.com/get/afe1af/1600x5)

### Purpose

Terminals are cool, but the tools to work with them often aren't. Celadon aims to:

- Reduce boilerplate
- Provide clean, easy to understand APIs with minimal abstraction
- Easy, UX-optimized color palette generation
- Minimize runtime errors and unhandled edgecases

The way this is achieved is primarily through our state-based widgets, which ensure _every state_ your widget can be in is handled declaratively up-front. We also provide all the standard TUI stuff, like mouse support, an incredibly performant drawing algorithm and full-color support.

![rule](https://singlecolorimage.com/get/afe1af/1600x5)

### Examples

All of that _sounds_ good, but is it actually? Here are some examples so you can decide. Click on the images to see the code!

Lens - Project manager     |  Turd Polisher 2000
:-------------------------:|:-------------------------:
![lens](https://github.com/shade40/celadon/blob/main/assets/placeholder.png?raw=true)  |  ![turd](https://github.com/shade40/celadon/blob/main/assets/placeholder.png?raw=true)

![rule](https://singlecolorimage.com/get/afe1af/1600x5)

### Technologies

Celadon aims to be as self-sufficient as reasonable. This means everything we _can_ write, we **will** write. It is built on top of 2 of [shade40](https://github.com/shade40/)'s projects:

- [gunmetal](https://github.com/shade40/gunmetal) for terminal interactions, including the `Screen` API that allows us to have char-by-char redraw
- [zenith](https://github.com/shade40/zenith) for its markup language & palette generation, which are used as the primary method of styling within widgets
