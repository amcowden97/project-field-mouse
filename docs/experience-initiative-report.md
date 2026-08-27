# Project Field Mouse Experience Initiative Report

## Summary

Phase 1 builds on the wildlife-first Dashboard V2 foundation without changing
its APIs, storage model, detector, recorder, services, or deployment. The work
audited every live page, documented the existing visual language as a reusable
design system, refined first-time journeys, strengthened brand readiness, and
added restrained interaction feedback.

The detailed pre-change findings are in
`docs/experience-initiative-visual-audit.md`. Reusable standards are in
`docs/dashboard-design-system.md`.

## Visual Improvements

### Before

- Strong nature-journal styling existed, but its rules lived mostly in CSS and
  were not documented for future contributors.
- Page section spacing differed between Overview and the remaining pages.
- Browser tabs had no local favicon or descriptive application metadata.
- Species and visitor cards offered limited hover confirmation.
- Infinite loading depended on text alone.
- The long Species record offered no quick orientation.
- Unobserved related species could lead to a 404.

### After

- Semantic brand, accent, information, status, and section-gap tokens clarify
  future component choices while preserving the approved visual direction.
- All pages share a 40 px major-section cadence, fluid type scale, common focus
  treatment, 44 px controls, paper surfaces, and restrained field-journal depth.
- The local mouse artwork supplies a replaceable favicon; page metadata now
  communicates the product’s purpose before a user enters the interface.
- Interactive wildlife cards lift gently and strengthen their border on hover or
  keyboard focus. Non-interactive cards remain still.
- Activity loading now sets `aria-busy`, retains a live text update, and displays
  a compact progress turn that respects reduced-motion preferences.
- Species pages include an “Explore this record” trail for Rhythm, Field notes,
  History, and Clips. Unobserved related species are labeled rather than linked.
- Future destinations remain deliberately quiet on desktop and absent on mobile,
  where working journeys receive the available space.

## Design System

The design system defines:

- A three-family typography model and fluid seven-step type scale.
- Nature-derived foundation colors plus semantic brand, accent, surface, text,
  information, success, warning, and danger roles.
- A 4–64 px spacing scale and common 40 px page-region rhythm.
- Four radius levels, three border weights, and three restrained shadow levels.
- Standards for cards, buttons, chips, tables, data lists, charts, status,
  confidence, empty states, loading states, icons, artwork, and brand placement.
- Motion durations of 120, 220, and 420 ms, with reduced-motion behavior required.
- Mobile-first layout rules, 44 px touch targets, and accessible chart equivalents.

The design system intentionally treats Unicode icons as temporary fallbacks.
Approved Branding Team assets can replace local files or asset-macro inputs
without rewriting page structure.

## User Journey

### First impression and Overview

The global header names the project and station while the hero immediately
answers where the user is. The page then moves through today’s activity, the
day’s natural-language story, latest visitors, discoveries, seven-day rhythm,
hourly activity, recordings, and only then device health. Quiet periods use calm
field-note language rather than error language.

### Activity

Users now reach the chronological wildlife observations directly after filtering.
The explanation of detector and future verification confidence follows the
observations, keeping software education available without interrupting the
wildlife-first path. Audio, species links, filters, progressive loading, and
no-JavaScript pagination remain intact.

### Life List

The collection hero establishes progress, achievement cards tell the history of
the collection, and sorting helps users browse familiar or recent visitors.
Species cards now signal interactivity consistently while preserving keyboard
focus and meaningful artwork.

### Species

The record begins with identity, artwork, first and last observations, followed
by a compact in-page trail. Rhythm, field notes, seasonality, history, confidence,
audio, verification detail, and related visitors form a predictable reading
sequence. Related entries can no longer create an avoidable dead end.

### Device

The Device page remains a deliberately secondary, calm technical checkup. It
uses the same hero, card, status, meter, type, spacing, and responsive rules as
the wildlife pages without disguising technical information as nature content.

## Screenshots

Before references:

- `docs/screenshots/dashboard-v2-polish-desktop.png`
- `docs/screenshots/dashboard-v2-polish-mobile-390.png`
- `docs/screenshots/dashboard-v2-polish-species-desktop.png`

Updated evidence:

- `docs/screenshots/experience-overview-desktop.png`
- `docs/screenshots/experience-overview-mobile-390.png`
- `docs/screenshots/experience-activity-desktop.png`
- `docs/screenshots/experience-life-list-mobile-390.png`
- `docs/screenshots/experience-species-mobile-390.png`

## Validation and Performance

- Every live page—Overview, Activity, Life List, a valid Species record, and
  Device—rendered in headless Chrome at 1440 px and 390 px.
- All renders had exactly one `h1`, a semantic `main`, descriptive metadata, a
  favicon, and zero severe browser-console messages.
- Desktop content stayed within its viewport. At 390 px, every page had exactly
  390 px document width, no horizontal overflow, no future navigation items, and
  a minimum 44 px live navigation target.
- Flask routes `/`, `/activity`, `/life-list`, a valid `/species/<name>`,
  `/device`, `/api/dashboard`, and `/api/metrics` returned HTTP 200.
- `/health` returned HTTP 200 with Raspberry Pi host-sensor collection isolated
  for the Windows test environment.
- Fifty local Overview renders averaged **6.94 ms** with a **7.69 ms p95**. This
  is within normal local variation and improves on the previous 8.51 ms sample;
  the initiative introduced no client library or network request.
- Four focused Dashboard tests passed. Ruff, Python compilation, and
  `git diff --check` passed.
- Full-suite collection remains blocked on this Windows environment by the
  optional `birdnet` package, before Dashboard tests execute.

## Remaining Opportunities

Appropriate RC1.2 or later work includes approved logo and icon substitution,
real handheld VoiceOver/TalkBack review, contrast automation in CI, a curated
species-content workflow, weather integration, year-over-year seasonal stories,
rare-event scoring, calibrated Verification V2 evidence, and Raspberry Pi
profiling with a mature production-shaped database. None is required to preserve
the current RC1.1 journey.

