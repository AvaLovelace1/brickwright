# Privacy Policy

_Last updated: 27 October 2026_

This policy covers the **BrickWright** skill/plugin distributed for Claude and ChatGPT. It does not
cover the BrickWright research project's other components.

## What the plugin collects

**Nothing.** The plugin has no server, no account, no analytics, and no telemetry. Its authors
receive no data from your use of it.

The plugin is a set of instructions and Python files that run inside your AI assistant's own
code-execution sandbox. Your prompts, any reference images you provide, the code the assistant
writes, and the `.ldr` files it produces stay within that sandbox and your conversation with the
assistant. They are never transmitted to the plugin's authors.

## Network access the plugin causes

The plugin performs one network operation: on first use it runs
`pip install bricklayer-sdk` to install its SDK from the Python Package Index (PyPI). That request
goes to PyPI, which may log it as it does any package download, under
[PyPI's privacy policy](https://policies.python.org/pypi.org/Privacy-Notice/). No information
about your prompt or your build is included in that request.

The plugin makes no other outbound requests. It does not call the authors' servers, because there
are none.

## Data handled by your AI assistant

Your conversation with Claude or ChatGPT — including anything you send the plugin — is governed by
the privacy policy of whichever assistant you are using
([Anthropic](https://www.anthropic.com/legal/privacy), [OpenAI](https://openai.com/policies/privacy-policy/)),
not by this one. The plugin's authors have no access to it.

## Children

The plugin is not directed at children under 13 and collects no personal information from anyone.

## Changes

Material changes will be reflected in this file with an updated date above.

## Contact

Questions: open an issue at
<https://github.com/AvaLovelace1/brickwright/issues>.
