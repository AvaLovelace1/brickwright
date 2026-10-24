<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ClassValue, HTMLAttributes } from "svelte/elements";

  interface Props extends HTMLAttributes<HTMLDivElement> {
    speaker: "user" | "robot";
    /** Sizes the avatar and its icon. */
    avatarClass?: ClassValue;
    /** Sizes and offsets the bubble's tail (its `before:` pseudo-element). */
    tailClass?: ClassValue;
    children: Snippet;
  }
  let { speaker, class: className, avatarClass, tailClass, children, ...rest }: Props = $props();
</script>

<!-- The robot's avatar and tail align at --speaker-anchor; the user's are vertically centered. -->
<div class={["flex", speaker === "user" ? "items-center" : "items-start", className]} {...rest}>
  <span
    class={[
      "flex shrink-0 items-center justify-center bb-border bg-(--bb-ink-bright)",
      speaker === "user"
        ? "border-primary text-primary"
        : "relative top-(--speaker-anchor) -translate-y-1/2 border-secondary text-secondary",
      avatarClass,
    ]}
    aria-hidden="true"
  >
    <span class={["iconify", speaker === "user" ? "tdesign--user" : "tdesign--robot"]}></span>
  </span>
  <div
    class={[
      "relative min-w-0 flex-1 self-stretch rounded-(--bb-border-radius) bg-bg p-3 text-text",
      "before:absolute before:-translate-y-1/2 before:rotate-45 before:bg-bg before:content-['']",
      speaker === "user" ? "before:top-1/2" : "before:top-(--speaker-anchor)",
      tailClass,
    ]}
  >
    {@render children()}
  </div>
</div>
