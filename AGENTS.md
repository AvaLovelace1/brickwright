# Website conventions

- Use Tailwind utility classes for styling; do not add custom `<style>` blocks to components.
- Prefer maintained library components (especially Bits UI) and existing project components over custom implementations
  of interactive behavior.
- Make sure check, lint, and tests pass after making a change.
- Use test-driven development. Minor styling changes don't need to be tested (brittle!), but behavioral contracts do.
- Use the official LDraw library for packing, rather than Studio's bundled parts library.
- Private comparison servers are ephemeral; do not commit their addresses or links in this repo.
