<script lang="ts">
  import { page } from "$app/state";
  import Container from "$lib/components/Container.svelte";
</script>

<svelte:head><title>BrickWright ▪ Error</title></svelte:head>

<div class="flex justify-center py-12">
  <Container class="prose">
    <h1>Error {page.status}: {page.error?.message}</h1>
  </Container>
</div>
