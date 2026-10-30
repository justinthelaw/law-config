# Develop skills

- Keep frontmatter descriptions specific to invocation intent; folder names must match skill names.
- Put shared defaults and handoffs in `develop/references/contract.md`, and domain mechanics in their owning skills.
- Repository entry points reuse the shared invocation and adversarial gates. Standalone Kaizen, adversarial reviews and audit-only `upgrade-codex` follow their entrypoint's completion policy; requested implementation uses the shared gates. Avoid recursive reviews.
- Preserve original/steering user intent, fresh non-forked review, and original model/effort matching. Never turn review into permission to bypass host controls.
- Clean, Deep Clean, Upgrade and Upgrade Codex require explicit selection, including across handoffs. Set `policy.allow_implicit_invocation: false` on each. Update `agents/openai.yaml` with each skill's behavior; keep references relative and packaged. Test changed behavior in a fresh context.
- Keep each `assets/icon.png` square and transparent. Match existing Roux icons' chocolate/cream palette, character proportions and crisp pixel edges; vary only the clear task prop. Declare the asset in both `icon_small` and `icon_large` in `agents/openai.yaml`. Preserve approved pixels and verify the whole set together at 48 px and smaller.
