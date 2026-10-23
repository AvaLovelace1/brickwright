<script lang="ts">
  import { useThrelte } from "@threlte/core";

  // Views share a canvas, so scrolling changes their scissor rectangles even
  // when the camera and model are stationary.
  const { invalidate } = useThrelte();
</script>

<svelte:window onscroll={invalidate} onresize={invalidate} />
