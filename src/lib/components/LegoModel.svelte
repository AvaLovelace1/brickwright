<script lang="ts" module>
  import {Box3, EquirectangularReflectionMapping, Object3D, type Texture, Vector3} from "three";
  import {LDrawLoader} from "three/examples/jsm/loaders/LDrawLoader.js";
  import {HDRLoader} from "three/examples/jsm/loaders/HDRLoader.js";
  import {LDrawConditionalLineMaterial} from "three/addons/materials/LDrawConditionalLineMaterial.js";
  import envMapUrl from "$lib/assets/studio_kontrast_02_1k.hdr?url";

  // One LDrawLoader shared across all LegoModel instances.
  const loader = new LDrawLoader();
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  let envMap: Promise<Texture> | undefined;
  const models: Record<string, Promise<Object3D>> = {};
  // Parse run one at a time with a gap in between, so the browser can handle other events between models
  let queue: Promise<unknown> = Promise.resolve();
  const yieldToBrowser = () => new Promise((resolve) => setTimeout(resolve));

  function loadEnvMap() {
    envMap ??= new HDRLoader().loadAsync(envMapUrl).then((texture) => {
      texture.mapping = EquirectangularReflectionMapping;
      return texture;
    });
    return envMap;
  }

  // Load an LDraw model, parsing each URL once. Clones share geometry and materials with the cached model.
  async function loadModel(url: string) {
    if (!models[url]) {
      models[url] = queue.then(() => loader.loadAsync(url)).then(normalizeModel);
      queue = models[url].then(yieldToBrowser, yieldToBrowser);
    }
    return (await models[url]).clone();
  }

  // Normalize a model to the unit cube
  function normalizeModel(group: Object3D) {
    group.rotation.x = Math.PI;
    const box = new Box3().setFromObject(group);
    const scale = 2 / Math.max(...box.getSize(new Vector3()).toArray());
    group.scale.setScalar(scale);
    group.position.copy(box.getCenter(new Vector3())).multiplyScalar(-scale);
    return group;
  }
</script>

<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Environment, OrbitControls, HTML } from "@threlte/extras";
  import { onMount } from "svelte";
  const { invalidate } = useThrelte();

  interface Props {
    ldrPacked: string;
    bricksShown?: number;
    onload?: (maxBricks: number) => void;
  }
  let { ldrPacked, bricksShown = Infinity, onload }: Props = $props();
  let prevBricksShown = 0;
  let ldrawGroup = $state<Object3D>();
  let envMapTexture = $state<Texture>();

  function showBricks(group: Object3D) {
    const shown = Math.min(bricksShown, group.children.length);
    if (prevBricksShown < shown) {
      for (let i = prevBricksShown; i < shown; i++) {
        group.children[i].visible = true;
      }
    } else {
      for (let i = shown; i < prevBricksShown; i++) {
        group.children[i].visible = false;
      }
    }
    prevBricksShown = shown;
    invalidate();
  }

  $effect(() => {
    if (ldrawGroup) showBricks(ldrawGroup);
  });

  onMount(async () => {
    loadEnvMap().then((texture) => (envMapTexture = texture));
    const group = await loadModel(ldrPacked);
    const maxBricks = group.children.length;
    prevBricksShown = maxBricks;
    ldrawGroup = group;
    onload?.(maxBricks);
  });

  let autoRotate = $state(true);
</script>

<T.PerspectiveCamera makeDefault position={[3, 0, 3]} fov={35}>
  <OrbitControls enableDamping {autoRotate} onstart={() => (autoRotate = false)} />
</T.PerspectiveCamera>
<Environment texture={envMapTexture} />
{#if !ldrawGroup}
  <HTML center><div class="text-sm text-text italic">Loading model…</div></HTML>
{/if}
<T is={ldrawGroup} />
