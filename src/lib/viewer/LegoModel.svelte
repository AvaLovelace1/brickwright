<script lang="ts" module>
  import {
    EquirectangularReflectionMapping,
    type Object3D,
    type Texture,
    type Vector3Tuple,
  } from "three";
  import { HDRLoader } from "three/addons/loaders/HDRLoader.js";
  import envMapUrl from "#lib/assets/studio_kontrast_02_1k.hdr?url";
  import { cached } from "#lib/viewer/cached.js";
  import { buildSteps, loadModel } from "#lib/viewer/ldraw.js";

  export const CAMERA = { position: [3, 0, 3] as Vector3Tuple, fov: 35 };

  const loadTexture = cached(async (url) => {
    const texture = await new HDRLoader().loadAsync(url);
    texture.mapping = EquirectangularReflectionMapping;
    return texture;
  });
  export const loadEnvMap = () => loadTexture(envMapUrl);
</script>

<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Environment, OrbitControls } from "@threlte/extras";
  import { onMount } from "svelte";
  import { on } from "svelte/events";
  import { viewerSettings } from "#lib/settings.svelte.js";
  import type { OrbitControls as OrbitControlsImpl } from "three/addons/controls/OrbitControls.js";
  import { createDiagnosticView, type DiagnosticView } from "#lib/viewer/model-diagnostic-view.js";
  import { activeView } from "#lib/viewer/models.js";
  import type { Viewer } from "#lib/viewer/viewers.svelte.js";
  const { invalidate, dom } = useThrelte();

  let { viewer, view = "inline" }: { viewer: Viewer; view?: "inline" | "expanded" } = $props();
  const model = $derived(viewer.model);
  let ldrawGroup = $state<Object3D>();
  const steps = $derived(ldrawGroup ? buildSteps(ldrawGroup) : []);
  let envMapTexture = $state<Texture>();
  let diagnosticView = $state<DiagnosticView>();
  let controls = $state<OrbitControlsImpl>();
  let interacting = $state(false);
  let focused = $state(false);
  const active = $derived(activeView(model) === view);
  const autoRotate = $derived(active && viewerSettings.rotateModels && !interacting && !focused);

  $effect(() => {
    if (!ldrawGroup) return;
    for (const [i, step] of steps.entries()) step.visible = i < model.stepsShown;
    invalidate();
  });

  $effect(() => {
    if (!ldrawGroup || !model.diagnostics) return;
    const current = createDiagnosticView(ldrawGroup, model.diagnostics);
    diagnosticView = current;
    return () => {
      diagnosticView = undefined;
      current.dispose();
    };
  });

  $effect(() => {
    if (!diagnosticView) return;
    diagnosticView.update({
      highlightCollisions: viewer.highlightCollisions,
      // Intersection lines describe the finished assembly, so they appear once every step is shown.
      showIntersections: viewer.showIntersections && model.stepsShown >= model.maxSteps,
    });
    invalidate();
  });

  $effect(() => {
    let disposed = false;
    loadModel(model.ldrPacked).then(
      (group) => {
        if (disposed) return;
        ldrawGroup = group;
        viewer.loaded(steps.length);
      },
      () => {
        if (!disposed) viewer.failed();
      },
    );
    return () => {
      disposed = true;
    };
  });

  onMount(() => {
    // Without an environment map the model keeps its direct lights.
    loadEnvMap().then(
      (texture) => (envMapTexture = texture),
      () => {},
    );
  });

  $effect(() => {
    if (!controls) return;
    const orbit = controls;
    dom.tabIndex = 0;
    dom.setAttribute("role", "group");
    dom.setAttribute("aria-label", `${model.caption}: interactive 3D view`);
    dom.setAttribute(
      "aria-description",
      "Arrow keys pan. Shift and arrow keys rotate. Plus and minus zoom. Home resets the view.",
    );
    dom.classList.add(
      "focus-visible:outline-2",
      "focus-visible:-outline-offset-4",
      "focus-visible:outline-link",
    );
    // OrbitControls handles the arrow keys.
    orbit.listenToKeyEvents(dom);
    const keyActions: Record<string, () => void> = {
      "+": () => orbit.dollyIn(0.9),
      "=": () => orbit.dollyIn(0.9),
      "-": () => orbit.dollyOut(0.9),
      Home: () => orbit.reset(),
    };
    const offs = [
      on(dom, "focus", () => (focused = true)),
      on(dom, "blur", () => (focused = false)),
      on(dom, "keydown", (event) => {
        const action = keyActions[event.key];
        if (event.target !== dom || !action) return;
        event.preventDefault();
        action();
      }),
    ];
    return () => {
      orbit.stopListenToKeyEvents();
      for (const off of offs) off();
    };
  });
</script>

<T.PerspectiveCamera makeDefault position={CAMERA.position} fov={CAMERA.fov}>
  <OrbitControls
    bind:ref={controls}
    enableDamping={active}
    {autoRotate}
    onstart={() => (interacting = true)}
    onend={() => (interacting = false)}
  />
</T.PerspectiveCamera>
<Environment texture={envMapTexture} />
{#if !envMapTexture}
  <T.AmbientLight intensity={2} />
  <T.DirectionalLight position={[3, 5, 3]} intensity={3} />
{/if}
<T is={ldrawGroup} dispose={false} />
{#if diagnosticView}<T is={diagnosticView.intersections} />{/if}
