<script lang="ts">
  import { useTask, useThrelte } from "@threlte/core";

  // The canvas scrolls with the page, so its drawing stays on the viewers between redraws. It is
  // twice the large viewport's height, centred on the viewport, and recentres, redrawing every
  // view, once scrolling uses up half its margin. It never extends below the element it is
  // positioned within, so it never lengthens the page.
  const { dom, invalidate } = useThrelte();
  const container = dom.parentElement!;
  let top = 0;

  useTask(
    () => {
      const span = container.offsetHeight;
      const margin = (span - innerHeight) / 2;
      const bottom = container.offsetParent!.getBoundingClientRect().bottom;
      const current = container.getBoundingClientRect().top;
      const drift = Math.round(Math.min(-margin, bottom - span) - current);
      const overflowing = current + span > bottom + 1;
      if (!overflowing && Math.abs(drift) < margin / 2) return;
      top += drift;
      container.style.top = `${top}px`;
      invalidate();
    },
    { autoInvalidate: false },
  );
</script>
