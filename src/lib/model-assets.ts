// Import URLs only: the viewer fetches geometry and diagnostics when it becomes visible.
// Keep provenance (source.json) outside this allowlist. Components import images separately.
const urls = import.meta.glob<string>(
  [
    "./assets/models/**/*.ldr",
    "./assets/models/**/*.packed.mpd",
    "./assets/models/**/*.diagnostics.json",
  ],
  { eager: true, query: "?url&no-inline", import: "default" },
);

export function modelAssets(name: string) {
  const path = `./assets/models/${name}`;
  const ldr = urls[`${path}.ldr`];
  const ldrPacked = urls[`${path}.packed.mpd`];
  if (!ldr || !ldrPacked) throw new Error(`Missing model assets: ${name}`);
  return { ldr, ldrPacked, diagnosticsUrl: urls[`${path}.diagnostics.json`] };
}
