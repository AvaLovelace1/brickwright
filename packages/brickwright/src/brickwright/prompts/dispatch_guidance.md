Use `dispatch_subagents` to run independent subtasks in parallel. Each task you list is handled by its own subagent
working in an isolated build; each returns its answer to you as text, which you then integrate yourself (subagents do
not change your build). Reach for it when you can split the work into pieces describable on their own—e.g. designing
separate components, or investigating the catalog while you keep building. Per task, you may set `tier`: `fast`
(cheapest, for simple work), `balanced`, or `smart` (most capable). Omit `tier` to use your own model. Prefer using
`balanced` or `fast` unless the task is genuinely difficult.