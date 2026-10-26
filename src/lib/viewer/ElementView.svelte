<script lang="ts">
  import {
    createCacheContext,
    createCameraContext,
    createDOMContext,
    createParentContext,
    createParentObject3DContext,
    createSceneContext,
    createUserContext,
    useTask,
    useThrelte,
  } from "@threlte/core";
  import type { Snippet } from "svelte";
  import { Scene, Vector4 } from "three";

  // Draws a scene where its element lies on the page canvas. Ancestors that hide overflow, such
  // as the carousel, clip the drawing as they clip the element, and the view redraws whenever
  // the element or canvas moves.
  let { dom, children }: { dom: HTMLElement; children: Snippet } = $props();

  const { renderer, renderStage, canvas, invalidate } = useThrelte();
  const scene = new Scene();
  createDOMContext(() => ({ dom, canvas }));
  createCacheContext();
  createSceneContext(scene);
  createParentContext(() => scene);
  createParentObject3DContext(() => scene);
  const { camera } = createCameraContext();
  createUserContext();

  const clips = $derived.by(() => {
    const clips: Element[] = [];
    for (let element = dom.parentElement; element; element = element.parentElement) {
      const { overflowX, overflowY } = getComputedStyle(element);
      if (overflowX !== "visible" || overflowY !== "visible") clips.push(element);
    }
    return clips;
  });

  // Rectangles from the canvas's bottom-left corner, where WebGL measures from. The canvas
  // scrolls with the page, so scrolling alone leaves them unchanged.
  function measure() {
    const bounds = canvas.getBoundingClientRect();
    const element = dom.getBoundingClientRect();
    let { left, top, right, bottom } = element;
    for (const box of [bounds, ...clips.map((clip) => clip.getBoundingClientRect())]) {
      left = Math.max(left, box.left);
      top = Math.max(top, box.top);
      right = Math.min(right, box.right);
      bottom = Math.min(bottom, box.bottom);
    }
    const visible = new DOMRect(left, top, right - left, bottom - top);
    const onCanvas = (rect: DOMRect) =>
      [rect.left - bounds.left, bounds.bottom - rect.bottom, rect.width, rect.height] as const;
    const area = { viewport: onCanvas(element), scissor: onCanvas(visible) };
    const shown = visible.width > 0 && visible.height > 0;
    return { ...area, shown, key: shown ? JSON.stringify(area) : "" };
  }

  let drawn = "";
  useTask(
    () => {
      if (measure().key !== drawn) invalidate();
    },
    { autoInvalidate: false },
  );

  const savedViewport = new Vector4();
  const savedScissor = new Vector4();
  useTask(
    () => {
      const { viewport, scissor, shown, key } = measure();
      drawn = key;
      if (!shown) return;
      renderer.getViewport(savedViewport);
      renderer.getScissor(savedScissor);
      const scissorTest = renderer.getScissorTest();
      renderer.setViewport(...viewport);
      renderer.setScissor(...scissor);
      renderer.setScissorTest(true);
      renderer.render(scene, camera.current);
      renderer.setViewport(savedViewport);
      renderer.setScissor(savedScissor);
      renderer.setScissorTest(scissorTest);
    },
    { stage: renderStage },
  );
</script>

{@render children()}
