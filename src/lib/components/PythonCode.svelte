<script lang="ts">
  import { highlightPython, type PythonTokenKind } from "#lib/python-highlighting.js";

  let { code }: { code: string } = $props();
  const tokens = $derived(highlightPython(code));

  const paletteClasses = [
    "[--python-keyword:var(--color-primary-deep)] dark:[--python-keyword:var(--color-primary-bright)]",
    "[--python-string:var(--color-secondary-deep)] dark:[--python-string:var(--color-secondary-bright)]",
    "[--python-constant:var(--color-accent-deep)] dark:[--python-constant:var(--color-accent-bright)]",
    "[--python-comment:var(--color-success-deep)] dark:[--python-comment:var(--color-success-bright)]",
    "[--python-function:var(--color-info-deep)] dark:[--python-function:var(--color-secondary-bright)]",
  ];
  const tokenClasses: Record<PythonTokenKind, string> = {
    plain: "text-text",
    keyword: "font-semibold text-(--python-keyword)",
    string: "text-(--python-string)",
    constant: "text-(--python-constant)",
    comment: "italic text-(--python-comment)",
    function: "text-(--python-function)",
  };
</script>

<code class={["block font-mono", paletteClasses]}
  >{#each tokens as token, index (index)}<span
      class={tokenClasses[token.kind]}
      data-token={token.kind}>{token.content}</span
    >{/each}</code
>
