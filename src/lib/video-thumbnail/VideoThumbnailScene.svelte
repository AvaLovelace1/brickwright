<script lang="ts" module>
  import { CAMERA, loadEnvMap } from "#lib/viewer/LegoModel.svelte";
  import { listParts, loadModel } from "#lib/viewer/ldraw.js";
  import { modelFiles } from "#lib/viewer/models.js";
  import { SCENES, type Frame } from "#lib/video-thumbnail/timeline.js";

  export const loaded = Promise.all([
    Promise.all(SCENES.map(({ model }) => loadModel(modelFiles(model).ldrPacked))),
    loadEnvMap(),
  ]);
</script>

<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Environment } from "@threlte/extras";
  import { onMount } from "svelte";
  import { MathUtils, type Group, type PerspectiveCamera, type Texture } from "three";

  let { frame }: { frame: Frame } = $props();
  const { renderer, scene } = useThrelte();
  const cameraDistance = Math.hypot(...CAMERA.position);

  let camera = $state<PerspectiveCamera>();
  let models = $state.raw<Group[]>();
  let envMap = $state.raw<Texture>();
  const parts = $derived(models?.map(listParts));

  onMount(async () => {
    [models, envMap] = await loaded;
  });

  $effect(() => {
    if (!parts || !camera) return;
    const shown = Math.round(frame.build * parts[frame.scene].length);
    parts[frame.scene].forEach((part, i) => (part.visible = i < shown));
    const angle = MathUtils.degToRad(frame.cameraAngle);
    camera.position.setFromSphericalCoords(cameraDistance, Math.PI / 2, angle);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  });
</script>

<T.PerspectiveCamera makeDefault fov={CAMERA.fov} bind:ref={camera} />
<Environment texture={envMap} />
{#if models}<T is={models[frame.scene]} dispose={false} />{/if}
