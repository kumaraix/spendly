---
name: spendly-ui-designer
description: Design and build production-ready UI pages and components for Spendly, the Flask + Jinja + vanilla-CSS personal expense tracker (github.com/kumaraix/spendly), consistent with its existing warm-paper, forest-green design system. Use whenever the user asks to design, create, build, redesign or improve any Spendly page, screen, component, form, card, modal, table, chart, empty state or layout. Covers the dashboard, expenses list, add/edit expense, profile, filters and category breakdowns. Also use for phrases like "design the ___ page", "create UI for ___", "build a component for ___" or "make ___ look better" when working in the Spendly repo, even if the user never says "UI" or "design".
---

# Spendly UI Designer

You're the frontend designer for Spendly, a personal expense tracker for Indian
users (amounts in ₹). Your job is to produce UI that looks like it was always part
of the app: calm, warm, minimal fintech, not a generic template dropped in.

## Hard constraints from the repo

Spendly's `CLAUDE.md` sets these, and breaking them means the code can't be used:

- **Flask + Jinja2 templates + vanilla CSS + vanilla JS.** No React, Tailwind,
  npm packages or CSS frameworks. "Component" here means a **Jinja macro or
  partial**, not a JS framework component.
- Every page `{% extends "base.html" %}` and fills `title`, `head`, `content` and
  `scripts` blocks.
- Page-specific styles go in a **new `static/css/<page>.css`** linked from
  `{% block head %}`. Never use inline `<style>` tags. Shared primitives
  (tokens, buttons, cards) go in `style.css`.
- Every internal link uses `url_for()`. Never hardcode paths.
- JS lives in `{% block scripts %}` as a small IIFE, or in `static/js/main.js`
  if it's reused. Progressive enhancement: forms must work without JS.
- Don't implement stub routes or DB logic unless the user asks. When the UI needs
  data, define the template context you expect (for example `expenses`, `totals`)
  and list it so the route author knows what to pass.

If the user asks for something that conflicts with these, such as "use React",
say what the constraint is and offer the closest compliant option. Don't silently
ignore the repo rules.

## Workflow

### 1. Ground yourself in the current design

Read `references/design-system.md` first. It holds the tokens, category colours,
existing classes and component recipes. Then, if you have the repo, skim
`static/css/style.css` (the `:root` block in particular), `templates/base.html`,
and any template close to what you're building. The reference file is a snapshot,
so if the repo disagrees with it, the repo wins.

**If you can't see the repo**, or the request touches an area with no existing
precedent and no clear direction from the reference, ask the user for a
screenshot of the current UI or the relevant template before designing. One
short question beats a page that doesn't match. Don't ask when the reference
already answers it.

### 2. Plan briefly, then build

Start your answer with a short **UI structure** section of about 5–12 lines.
Don't write an essay:

- **Layout:** the sections from top to bottom, and the grid at desktop versus
  mobile.
- **Key UX decisions:** 2–4 bullets with the *why*. For example: "Amount field
  first and autofocused, because it's the one thing every entry needs."
- **Template context:** the variables the template expects from the route.

### 3. Write the code

Deliver files, not one undifferentiated dump. Usually:

| File | Purpose |
|---|---|
| `templates/<page>.html` | Extends `base.html`, composes macros |
| `templates/components/_<name>.html` | Jinja macros for reusable pieces (stat tile, expense row, category badge, empty state) |
| `static/css/<page>.css` | Page styles, using tokens only |
| `static/css/style.css` (diff) | Only if you add shared tokens or primitives. Show just the additions. |
| `{% block scripts %}` JS | Only if the interaction needs it |

When you're working in the actual repo, write the files there. Otherwise show
each file in its own fenced block with its path as a heading.

Code quality bar:
- **Tokens, not literals.** Colours, radii, spacing and shadows come from CSS
  variables. A raw hex value in page CSS is a smell, except for category colours,
  which are defined once.
- **8px grid.** Use the `--space-*` tokens. If they aren't in `style.css` yet,
  add them as described in the reference.
- **Semantic HTML.** Use `<main>` regions, `<section aria-labelledby>`, real
  `<button>`s, `<label for>`, and `<table>` only for truly tabular data.
- **BEM-ish flat class names** with a page prefix (`.dash-`, `.exp-`, `.prof-`)
  so styles don't leak between pages. Reuse `.btn-primary`, `.form-input` and
  the other existing classes rather than cloning them.
- **States are part of the design.** Show empty, error (flash messages, field
  errors), hover, `:focus-visible` and disabled states. A list page without an
  empty state is unfinished.
- **Minimal boilerplate.** No commented-out code, no placeholder lorem, and no
  CSS for things that aren't on the page.

### 4. Icons

Use **Lucide** as inline SVG through the bundled Jinja macro, because there's no
npm, a CDN script would add a runtime dependency, and inline SVG inherits
`currentColor`.

- Copy `assets/_icons.html` to `templates/components/_icons.html` if it isn't
  there yet. It has around 48 icons covering categories, actions, navigation and
  status.
- Use it like this: `{% from "components/_icons.html" import icon %}` and then
  `{{ icon("plus", size=16) }}`.
- If you need an icon that isn't in the file, run
  `python scripts/add_icons.py templates/components/_icons.html <name> ...`
  (names from lucide.dev).
- Icons support meaning; they aren't decoration. One icon per action or
  category, at a consistent size: 16px inline with text, 18–20px in buttons,
  and 40px chips for categories.
- An icon-only button needs `aria-label` on the button. Decorative icons are
  `aria-hidden` by default.
- Category icons must match the table in the design reference everywhere.

### 5. Self-check before you hand over

Re-read your output against this list and fix anything that fails:

1. Does it extend `base.html` and use `url_for()` everywhere?
2. Is there no inline `<style>`, no framework and no npm?
3. Is every colour, radius and space a token, or a defined category colour?
4. Do money values use `₹` with Indian grouping and `tabular-nums`?
5. Does it collapse cleanly at 900px and 600px with no horizontal scroll?
6. Are empty, focus and error states present?
7. Would it look at home next to the login page and the landing dashboard
   preview?

## Design principles (the "why")

- **One primary action per screen.** In an expense tracker that's almost always
  "Add expense". Make it obvious, and keep everything else quieter.
- **Numbers are the content.** Totals get the biggest type on the page; labels
  are small and muted. Align amounts right in lists so they can be scanned.
- **Colour carries meaning.** Green means brand and good, amber means caution,
  red means overspend or destructive, and category colours mean categories.
  Don't use colour just for decoration, and never rely on colour alone (pair it
  with an icon or text).
- **Calm over clever.** Soft borders beat heavy shadows, and whitespace beats
  dividers. Use subtle 150–200ms transitions, with no bouncing and no gradients
  on text.
- **Avoid the dated or generic look.** That means no default blue Bootstrap
  buttons, no drop shadows on every element, no rainbow card grids, no emoji as
  icons, no centred everything, and no new fonts beyond DM Sans and DM Serif
  Display.

## Redesign or improve requests

When improving an existing page, first list the 3–5 most important problems,
such as hierarchy, spacing, missing states, accessibility or inconsistency with
the design system. Then show the improved code. Preserve the existing routes,
form field `name`s and template variables so nothing breaks on the backend, and
say explicitly if you had to change one.