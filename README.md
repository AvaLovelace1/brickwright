# BrickWright Project Page

SvelteKit-based project website for BrickWright.

Preview with:

```bash
npm run dev
```

Run tests with:

```bash
npm run test
```

## Packing LDraw models for display

LDraw files must be [packed](https://github.com/mrdoob/three.js/blob/dev/utils/packLDrawModel.mjs) before being
displayed on the website. This embeds the parts into the model file, so it can be displayed without needing to load the
entire LDraw library.
