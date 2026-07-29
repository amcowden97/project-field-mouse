# Dashboard V3 pixel-art library

These raster assets were generated with the built-in image-generation tool
for Project Field Mouse and post-processed locally.

## Shared art direction

- Hand-crafted 16-bit pixel-art appearance
- Visible square pixels and dark ink outlines
- Quiet indie nature-game and field-guide character
- No text, logos, watermarks, cast shadows, or reflections
- Generous transparent padding for reuse at several card sizes

## Palette

- Pine: `#244A35`
- Moss: `#5F7855`
- Sage: `#AFC2A2`
- Bark: `#76563D`
- Rust: `#A65F3F`
- Gold: `#D4A94F`
- Cream: `#F2E7CC`
- Ink: `#28362D`

## Production

Each distinct subject was generated separately on a flat magenta chroma-key
background. The source was resized with nearest-neighbor sampling, converted
to a transparent PNG, and checked for square dimensions and transparent
corners.

- Weather icons and the streak badge: 64 × 64
- Wildlife, flora, and field-kit objects: 128 × 128
- Station and hero station scene: 256 × 256

The CSS uses `image-rendering: pixelated` when these images are scaled.
