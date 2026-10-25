<script lang="ts">
  import { onDestroy } from "svelte";
  import copy from "copy-to-clipboard";
  import Container from "#lib/components/Container.svelte";
  import Button from "#lib/components/Button.svelte";
  import Prose from "#lib/components/Prose.svelte";

  const CITATION_TEXT = `@misc{pun2026brickwright,
  title = {BrickWright: Agentic Creation of Physically Feasible Brick Builds},
  author = {Pun, Ava and Dai, Kevin and Chen, Sally and Jones, Maxwell and Liu, Ruixuan and Deng, Kangle and Liu, Changliu and Agrawala, Maneesh and Ramanan, Deva and Zhu, Jun-Yan},
  year = {2026},
  eprint = {2610.31651},
  archivePrefix = {arXiv},
}`;
  const COPY_STATES = {
    idle: { text: "Copy", icon: "tdesign--task", class: "" },
    success: { text: "Copied!", icon: "tdesign--check", class: "bb-btn-success" },
    error: { text: "Copy failed", icon: "tdesign--error", class: "bb-btn-danger" },
  };
  let copyStatus = $state<keyof typeof COPY_STATES>("idle");
  let flashTimer: ReturnType<typeof setTimeout>;

  async function handleCopy() {
    copyStatus = (await copy(CITATION_TEXT)) ? "success" : "error";
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => {
      copyStatus = "idle";
    }, 2000);
  }

  onDestroy(() => clearTimeout(flashTimer));
</script>

<section id="citation" aria-labelledby="citation-heading" class="flex justify-center pt-12 pb-24">
  <Container>
    <Prose>
      <h2 id="citation-heading">Citation</h2>
      <p>If you’ve used BrickWright in your work, please cite us!</p>
      <div class="relative">
        <pre
          class="not-prose bb-card text-sm text-wrap"
          data-testid="citation">{CITATION_TEXT}</pre>
        <div class="absolute -top-2 -right-3 left-auto z-10 sm:-right-4">
          <Button {...COPY_STATES[copyStatus]} action={handleCopy} />
        </div>
      </div>
    </Prose>
  </Container>
</section>
