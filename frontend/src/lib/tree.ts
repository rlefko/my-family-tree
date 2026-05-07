// Single-user app: every domain row carries a `tree_id`, and the column will
// drive multi-user scoping later. Keeping the literal in one place means the
// eventual transition swaps one import for a context lookup, not four.
export const DEFAULT_TREE_ID = "00000000-0000-0000-0000-000000000000";
