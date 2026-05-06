---
name: mft-add-shadcn
description: Add a shadcn/ui primitive correctly into the frontend.
---

Use when the user asks to add a shadcn primitive.

1. `cd frontend && npx shadcn@latest add <component>` (e.g. `dialog`,
   `dropdown-menu`, `input`, `select`).
2. The command writes to `src/components/ui/`. Don't hand-edit those files;
   they are regenerated when shadcn ships updates.
3. Import via `@/components/ui/<component>` and use the `cn()` helper from
   `@/lib/utils` for any conditional class names.
4. If the primitive needs a new Radix peer, the shadcn CLI adds it to
   `package.json` automatically; commit `package.json` and `yarn.lock`
   together.
5. Re-run `yarn lint && yarn typecheck` to make sure the addition didn't
   break anything.
