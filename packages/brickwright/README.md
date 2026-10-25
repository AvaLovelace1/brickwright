# BrickWright

**BrickWright** is an agentic framework for creating LEGO® builds with
[BrickLayer](https://github.com/AvaLovelace1/brickwright/tree/main/packages/bricklayer). Using BrickWright,
you can direct your favorite AI agents (GPT, Claude, Gemini, etc.) to automatically create brick builds from text or
image prompts and export them to [LDraw](https://www.ldraw.org/).

## Usage

### 1. Install prerequisites

Install the BrickWright CLI. We recommend using [uv](https://docs.astral.sh/uv/):

```sh
uv tool install brickwright
```

#### LDraw parts library (optional but recommended)

BrickWright can render a build to a preview image, letting the agent visually check a build. To enable rendering,
you must download the [LDraw parts library](https://library.ldraw.org/updates?latest) and set the environment
variable `$LDRAW_LIBRARY_PATH` to its path. Without a library, the rendering tool is disabled.

### 2. Start creating!

#### Option 1: External Agent (e.g. Codex, Claude Code)

Simply prompt your favorite agent to create a brick build following the instructions
in [EXTERNAL_AGENT_INSTRUCTIONS.md](https://github.com/AvaLovelace1/brickwright/blob/main/packages/brickwright/EXTERNAL_AGENT_INSTRUCTIONS.md).

#### Option 2: API key (e.g. OpenAI Platform, Claude Console)

Ensure that the key for your favorite AI provider is set as an environment
variable (e.g., `$ANTHROPIC_API_KEY`, `$OPENAI_API_KEY`).

```
export OPENAI_API_KEY="sk-XXX"
# OR
export ANTHROPIC_API_KEY="XXX"
```

Then, run `brickwright generate`:

```zsh
brickwright generate "a detailed cruise ship" [--image ref.png] [--model M] [--effort E]
```

Specify the generation model (e.g. `claude-opus-4-8`, `gpt-5`) with `--model` or by setting the environment variable
`$BRICKWRIGHT_GENERATION_MODEL`.
You can run `litellm.get_valid_models()` for a list of available models based on your environment's set API keys.

Results are saved to `--records-dir` (default `./records`, or `$BRICKWRIGHT_RECORDS_DIR`
if set).

Run `brickwright generate --help` for more options.

---

*LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.*
