# BrickWright: External Agent Guidelines

You are an external agent authoring LEGO builds in this repository. You create a build by editing **one Python file**,
`build.py`, inside a **record** directory, then validating it through the BrickWright CLI. All record files other than
`build.py` are read-only; do not edit them.

## Step 0: Read the instructions

Generate the authoring instructions and API reference once per session, saving the file outside any record directory:

```bash
brickwright external instructions > INSTRUCTIONS.md
```

Then, read the file. As it is quite long, you may have to read it in several segments.

## Step 1: Create a record

After reading the instructions, initialize a new record with the following command:

```bash
brickwright external init <text_prompt>
```

where `<text_prompt>` is the prompt provided by the user (or a summary thereof).

Options:

- `--model <id>` / `--effort none|minimal|low|medium|high|xhigh|max`—recorded in metadata. If you know your model (e.g.
  `"claude-sonnet-4-5"`) and/or reasoning effort, please fill these in.
- `--image <path>`—attach a reference image when the user's prompt includes one.
- `--from <record_id>`—start from an existing record. Use this if the user asks you to modify an existing build.

`init` prints two lines:

```
record_id=[...]
build_path=[...]/build.py
```

**Edit only the printed `build.py`.**

To modify an existing build, fork it rather than copying directories:

```bash
brickwright external init --from <record_id> <text_prompt>
```

## Step 2. Validate the build

When you have finished editing `build.py`, run checks on it with:

```bash
brickwright external validate <record_id>
```

This creates the build and runs `run_tests()` in a fresh process, then independently checks the same build for floating
parts and collisions. It prints the JSON report and exits 0 only when every check passes. Each failing check names the
problem in its `detail`, e.g.:

```json
{
  "ok": false,
  "checks": [
    {
      "name": "no_floating",
      "passed": false,
      "detail": "1 floating: Brick  2 x  4 @ Position(2, 1, 3)"
    },
    {
      "name": "no_collisions",
      "passed": true,
      "detail": null
    }
  ]
}
```

Edit `build.py` to fix any issues and re-run validation until `ok` is true.

## Step 3: Preview the build

Validation checks structure but does not show you what the build *looks* like. To see the current build, render it to an
image:

```bash
brickwright external render <record_id>
```

This creates the build and writes `out/build.png`—a single contact sheet with front, side, top, and isometric
views—then prints its path. Open that file to visually inspect the build. Use `render` to confirm that the shape,
colors, and proportions match the prompt. If the build does not satisfy the prompt or looks unappealing, revise
`build.py` and go back to Step 2.

You may also render the build from a specific camera angle:

```bash
brickwright external render-angle <record_id> --azimuth A --elevation E
```

By default, this writes `out/viewpoint.png`.

For an image prompt, compare the build against the reference by running
`brickwright external critique-instructions <record_id>` and following the playbook it prints.

> [!note]
> Rendering requires an LDraw parts library. If no library is found, `brickwright external render` reports it—skip this
> step and rely on `validate` instead.

## Step 4: Finalize

Once `validate` reports `ok: true` and the build is aesthetically appealing and satisfies the user's request, finalize
the finished build:

```bash
brickwright external finalize <record_id>
```

This creates the build one last time and writes `out/build.ldr` (the LDraw file) for human inspection. Run it when you
are done—it is the last step.

## Rules

You must:

- use `brickwright external init` to create a new record (and `--from` to modify an existing one)—never hand-create or
  copy record directories
- edit only the `build.py` path printed by the CLI
- validate with `brickwright external validate` and get `ok: true`, then run `brickwright external finalize` to compile
  the build before finishing

You may:

- run `brickwright external render <record_id>` or
  `brickwright external render-angle <record_id> --azimuth A --elevation E` at any point to preview the build as an
  image
  and check it against the prompt

You must not:

- manually create record directories
- manually copy parent record folders for edits
- edit unrelated records while authoring one build
