<script lang="ts">
  import type { ClassValue } from "svelte/elements";
  import { highlightPython } from "#lib/python-highlighting.js";

  let { code, class: className = "" }: { code: string; class?: ClassValue } = $props();
  const tokens = $derived(highlightPython(code));

  const paletteClasses = [
    "[--python-keyword:var(--color-primary-deep)] dark:[--python-keyword:var(--color-primary-bright)]",
    "[--python-string:var(--color-secondary-deep)] dark:[--python-string:var(--color-secondary-bright)]",
    "[--python-constant:var(--color-accent-deep)] dark:[--python-constant:var(--color-accent-bright)]",
    "[--python-comment:var(--color-success-deep)] dark:[--python-comment:var(--color-success-bright)]",
    "[--python-function:var(--color-info-deep)] dark:[--python-function:var(--color-secondary-bright)]",
  ];
</script>

<code data-language="python" class={["block font-mono", paletteClasses, className]}
  >{#each tokens as token, index (index)}<span class={token.className} data-token={token.kind}
      >{token.content}</span
    >{/each}</code
>
