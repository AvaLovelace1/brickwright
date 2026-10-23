<script lang="ts" module>
  import {
    EquirectangularReflectionMapping,
    type Object3D,
    type Texture,
    type Vector3Tuple,
  } from "three";
  import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
  import envMapUrl from "#lib/assets/studio_kontrast_02_1k.hdr?url";
  import { loadModel } from "#lib/ldraw.js";
  export const CAMERA = { position: [3, 0, 3] as Vector3Tuple, fov: 35 };
  let envMap: Promise<Texture> | undefined;

  export function loadEnvMap() {
    envMap ??= new HDRLoader()
      .loadAsync(envMapUrl)
      .then((texture) => {
        texture.mapping = EquirectangularReflectionMapping;
        return texture;
      })
      .catch((error) => {
        envMap = undefined;
        throw error;
      });
    return envMap;
  }
</script>

<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Environment, OrbitControls } from "@threlte/extras";
  import { onMount } from "svelte";
  import { on } from "svelte/events";
  import { viewerSettings } from "#lib/settings.svelte.js";
  import type { OrbitControls as OrbitControlsImpl } from "three/examples/jsm/controls/OrbitControls.js";
  import { createDiagnosticView, type DiagnosticView } from "#lib/model-diagnostic-view.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";
  import { activeView, type ModelView } from "#lib/models.js";
  const { invalidate, dom } = useThrelte();

  interface Props extends Partial<DiagnosticDisplay> {
    model: ModelView;
    expanded?: boolean;
  }
  let {
    model = $bindable(),
    highlightCollisions = false,
    showIntersections = false,
    expanded = false,
  }: Props = $props();
  let prevStepsShown = 0;
  let ldrawGroup = $state<Object3D>();
  let envMapTexture = $state<Texture>();
  let diagnosticView = $state<DiagnosticView>();
  let controls = $state<OrbitControlsImpl>();
  let interacting = $state(false);
  let focused = $state(false);
  const active = $derived(activeView(model) === (expanded ? "expanded" : "inline"));
  const autoRotate = $derived(active && viewerSettings.rotateModels && !interacting && !focused);

  function showSteps(group: Object3D) {
    const shown = Math.min(model.stepsShown, group.children.length);
    if (prevStepsShown < shown) {
      for (let i = prevStepsShown; i < shown; i++) {
        group.children[i].visible = true;
      }
    } else {
      for (let i = shown; i < prevStepsShown; i++) {
        group.children[i].visible = false;
      }
    }
    prevStepsShown = shown;
    invalidate();
  }

  $effect(() => {
    if (ldrawGroup) showSteps(ldrawGroup);
  });

  $effect(() => {
    if (!ldrawGroup || !model.diagnostics) return;
    const view = createDiagnosticView(ldrawGroup, model.diagnostics);
    diagnosticView = view;
    return () => {
      diagnosticView = undefined;
      view.dispose();
    };
  });

  $effect(() => {
    if (!diagnosticView || !ldrawGroup) return;
    diagnosticView.update({
      highlightCollisions,
      // The exported lines describe the complete assembly, not individual build steps.
      showIntersections: showIntersections && model.stepsShown >= model.maxSteps,
    });
    invalidate();
  });

  $effect(() => {
    // Retry sets the status back to loading.
    if (ldrawGroup || model.status === "error") return;
    let disposed = false;
    loadModel(model.ldrPacked).then(
      (group) => {
        if (disposed) return;
        // A step reveals one top-level object: a part or an entire submodel.
        prevStepsShown = group.children.length;
        ldrawGroup = group;
        model.maxSteps = group.children.length;
        model.status = "loaded";
      },
      () => {
        if (!disposed) model.status = "error";
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
