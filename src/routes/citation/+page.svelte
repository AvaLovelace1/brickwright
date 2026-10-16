<script lang="ts">
  import copy from "copy-to-clipboard";
  import Container from "#lib/components/Container.svelte";
  import Button from "#lib/components/Button.svelte";

  const CITATION_TEXT = `@misc{pun2026brickwright,
  title = {BrickWright: Agentic Creation of Physically Feasible Brick Builds},
  author = {Pun, Ava and Dai, Kevin and Chen, Sally and Jones, Maxwell and Liu, Ruixuan and Deng, Kangle and Liu, Changliu and Agrawala, Maneesh and Ramanan, Deva and Zhu, Jun-Yan},
  year = {2026},
  archivePrefix = {arXiv},
}`;
  const COPY_TEXT = "Copy";
  const COPY_ICON = "tdesign--task";

  let copyButtonText = $state(COPY_TEXT);
  let copyButtonIcon = $state(COPY_ICON);
  let copyButtonClass = $state("");
  let flashTimer: NodeJS.Timeout | null = null;

  function showFlash(text: string, icon: string, className: string) {
    copyButtonText = text;
    copyButtonIcon = icon;
    copyButtonClass = className;
    if (flashTimer) clearTimeout(flashTimer);
    flashTimer = setTimeout(() => {
      copyButtonText = COPY_TEXT;
      copyButtonIcon = COPY_ICON;
      copyButtonClass = "";
      flashTimer = null;
    }, 2000);
  }

  async function handleCopy() {
    if (await copy(CITATION_TEXT)) showFlash("Copied!", "tdesign--check", "bb-btn-success");
    else showFlash("Copy failed", "tdesign--error", "bb-btn-danger");
  }
</script>

<svelte:head><title>BrickWright ▪ Citation</title></svelte:head>

<div class="flex justify-center py-12">
  <Container class="prose">
    <h1>Citation</h1>
    <p>If you’ve used BrickWright in your work, please cite us!</p>
    <div class="relative">
      <pre class="not-prose bb-card text-sm text-wrap" data-testid="citation">{CITATION_TEXT}</pre>
      <div class="absolute -top-2 -right-3 left-auto z-10 sm:-right-4" data-testid="copy-button">
        <Button
          text={copyButtonText}
          icon={copyButtonIcon}
          action={handleCopy}
          class={copyButtonClass}
        />
      </div>
    </div>
  </Container>
</div>
