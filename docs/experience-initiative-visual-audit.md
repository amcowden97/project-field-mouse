# Experience Initiative Visual Audit

Audit date: 2026-08-16  
Branch: `feature/dashboard-v2`  
Scope: live Dashboard V2 presentation templates and shared V3 presentation CSS

This audit was recorded before Phase 1 implementation changes.

## Cross-application findings

### What is already cohesive

- The paper, pine, moss, bark, and gold palette communicates a warm field-journal identity.
- Georgia display type, system body type, and monospace metadata establish a useful editorial hierarchy.
- Shared spacing, radius, shadow, type, motion, and color variables already cover most page needs.
- Every live page uses the same header, navigation, footer, skip link, focus treatment, and responsive shell.
- Semantic headings, native controls, visible focus, reduced-motion support, and 44 px touch targets provide a sound accessibility baseline.

### Inconsistencies and friction

- Component standards exist in code but are not documented, making ad hoc variants likely as the project grows.
- Hero backgrounds, status treatments, and several card families use local declarations instead of named semantic tokens.
- Unicode symbols mix music, geometric, and computer metaphors. They work as fallbacks, but approved brand icons need a stable replacement contract.
- The browser has no dashboard favicon or descriptive metadata, weakening the first impression outside the page itself.
- Interactive cards and text links do not always provide equally clear hover feedback.
- Loading feedback is textual only and visually easy to miss during infinite activity loading.
- Future destinations occupy nearly half the desktop navigation, competing with the four journeys that work today.
- Spacing cadence varies slightly: overview uses a 3 rem section rhythm while the other page stacks use 2.5 rem.

## Page review

### Overview

The wildlife-first hierarchy is strong: station identity, today, narrative highlights, visitors, discoveries, trends, recordings, then health. The daily and weekly charts are clear and values are available without color. The main remaining issue is density: multiple consecutive card grids can feel uniform, and empty fixture data causes several quiet-state messages to repeat. The seasonal note is useful but visually detached from the story it qualifies.

### Activity

Filtering, chronological reading, confidence, audio, species links, pagination fallback, and verification disclosure are all understandable. The Verification explanation currently appears before the observations, causing software language to interrupt the wildlife journey. Loading status lacks a recognizable visual cue. Detection rows have good structure but need a slightly clearer interactive species affordance.

### Life List

The collection metaphor, achievement strip, sort controls, numbered cards, and discovery details make the page rewarding. Card markup and styling are separate from general cards, which should be explicitly documented. Hover feedback is limited even though each species identity is a primary journey. Empty-state text is strong.

### Species

The species hero, first/last observations, rhythm, seasonality, history, confidence, clips, and related entries form a convincing living record. The page is long, so an introductory contents cue would improve discoverability. Related-species placeholders may link to species that are not yet observed, which can produce a dead-end 404 depending on curated content.

### Device

The page appropriately changes tone to a calm technical checkup and keeps control actions out of scope. Service, storage, memory, database, model, and freshness sections are readable. Technical paths can be long but already wrap safely. The four service cards create high visual density on desktop, although this is acceptable on the explicitly technical page.

## Priority changes for Phase 1

1. Document and expose semantic design-system roles without replacing the existing palette.
2. Add browser-level brand readiness: metadata and a replaceable local favicon.
3. Move Verification education below the wildlife activity list.
4. Add a compact species-page contents trail and guard related-species links from dead ends.
5. Improve loading, hover, and interactive-card feedback while honoring reduced motion.
6. Normalize page spacing and document intentional page-specific exceptions.
7. Retain future desktop navigation for roadmap visibility, but reduce its contrast and keep it absent on mobile.

## Deferred findings

Approved logo/icon substitution, real weather, calibrated verification, seasonal comparisons requiring a longer history, and content-managed species facts depend on other teams or future data. They should not delay RC1.1.

