# Project Field Mouse Dashboard Design System

## Design principles

Project Field Mouse is a nature journal first and a monitoring interface second.
Pages should lead with wildlife, use plain language, reveal technical detail only
when useful, and remain calm when the station has nothing new to report. The
visual character combines a field notebook, a small nature museum, and restrained
retro computing.

The implementation source of truth is `app/web/static/css/v3/tokens.css` plus the
shared V3 component and macro files. This document describes how to use them.

## Typography

Three system-safe families avoid network requests and keep Raspberry Pi serving
cost low:

- Display: Georgia for page titles, narrative headings, species names, and large values.
- Body: the operating-system UI stack for prose, labels, and controls.
- Mono: Courier New for timestamps, eyebrows, status, identifiers, and compact field metadata.

The type scale is `xs` 12 px, `sm` 14 px, `base` 16 px, and fluid `lg`, `xl`,
`2xl`, and `3xl` steps. Use one `h1` for the page purpose, `h2` for journeys or
major regions, and `h3` inside cards. Eyebrows identify editorial context but
must not replace headings. Body copy uses 1.55 line height; narrative ledes use
the relaxed 1.7 line height and a 44 rem reading measure.

## Color

Foundation colors are pine, moss, sage, bark, rust, gold, paper, cream, ink, and
sky. Prefer semantic roles in new components:

| Role | Token | Use |
| --- | --- | --- |
| Brand | `--pfm-color-brand` | Header, navigation, primary identity |
| Strong brand | `--pfm-color-brand-strong` | High-contrast borders and titles |
| Accent | `--pfm-color-accent` | Discovery, active navigation, focus-adjacent emphasis |
| Surface | `--pfm-color-surface` | Paper cards |
| Muted surface | `--pfm-color-surface-muted` | Notes, secondary panels, quiet states |
| Success | `--pfm-color-success` | Healthy or confirmed states |
| Warning | `--pfm-color-warning` | Attention without failure |
| Danger | `--pfm-color-danger` | Offline or failed states |
| Information | `--pfm-color-info` | Neutral system information |

Never use status color as the only signal; pair it with text. Body text must use
ink roles on paper roles. Gold is an accent, not a body-text color.

## Spacing and layout

The spacing scale is 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64 px. Major page
regions use `--pfm-section-gap` (40 px). Cards usually use 16–24 px internal
padding. Use CSS Grid with `minmax(0, 1fr)` to prevent overflow and switch to a
single column before content becomes cramped. The site maximum is 78 rem and
reading copy should generally stay within 44 rem.

All interactive controls must meet the 44 px `--pfm-touch-target`. Mobile starts
at 360 px; do not rely on horizontal scrolling for primary content.

## Corners, borders, and shadows

- Small radius (8 px): stamps, meters, and compact metadata.
- Medium radius (14 px): controls and nested panels.
- Large radius (20 px): cards and empty states.
- Extra-large radius (28 px): page and station heroes.
- Round: chips, status pills, and badges only.

Use 1 px borders for internal separation, 2 px borders for cards, and 3 px
borders for major identity containers. `shadow-sm` suits utility cards,
`shadow-md` suits interactive collection cards, and `shadow-lg` is reserved for
heroes or lifted interactive cards. Shadows should feel printed or stacked, not
glass-like.

## Components

### Cards

Use the shared `card` macro for ordinary titled content. Custom wildlife,
species, and service cards are appropriate only when their information structure
differs materially. Interactive cards lift by no more than 3 px and retain a
visible link or focus target; never make a non-interactive card appear clickable.

### Buttons and chips

Buttons initiate an action or pagination. Chips represent small filter and sort
choices and mark the selected choice with `aria-current="page"`. Both use shared
focus, border, hover, and touch-target rules. Link wording should describe the
destination rather than say “click here.”

### Tables and data lists

Use semantic tables for repeated comparable columns. Use `dl` for compact
label/value facts. On small screens, definition lists stack and long paths wrap.
Visual charts should include visible values, an accessible name, or an equivalent
screen-reader table.

### Status and confidence

Status combines a dot or badge, a plain-language label, and optional detail.
BirdNET confidence is always named as BirdNET confidence. Verification confidence
must remain absent or explicitly unavailable until independent evidence exists.

### Empty and loading states

Empty states explain what is quiet, what will appear, and—when relevant—what the
user can try next. They should not imply an error when nature is simply inactive.
Asynchronous lists set `aria-busy`, update an `aria-live` message, and show a
small progress cue. Loading animation must disappear under reduced motion.

### Icons and artwork

Use local pixel artwork from `static/assets/v3` for meaningful wildlife and field
objects. Unicode symbols are temporary fallbacks, not the final icon system.
Artwork needs useful alt text when informative and empty alt text or
`aria-hidden` when decorative. Approved Branding Team files can replace assets at
the same paths or through the asset macro without restructuring templates.

## Motion

Motion supports orientation: 120 ms for color feedback, 220 ms for small movement,
and 420 ms only for gentle contextual transitions. The listening pulse indicates
ongoing state; card lift confirms interactivity; the loading turn indicates an
active fetch. Avoid decorative looping motion elsewhere. The global
`prefers-reduced-motion` rule reduces animations and disables smooth scrolling.

## Brand placement

The product name and “Nature Connected” appear once in the global header and
again quietly in the footer. Station identity belongs in the page hero. The
favicon currently uses the local mouse artwork as a replaceable placeholder.
Approved logo, favicon, and icon assets should preserve accessible names and the
existing header proportions when substituted.

