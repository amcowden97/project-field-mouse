# Dashboard V3 activation

Dashboard V3 is active in `3.0.0-rc1`.

## Route wiring

The existing URLs are retained:

- `/` → `v3/overview.html`
- `/activity` → `v3/activity.html`
- `/life-list` → `v3/life_list.html`
- `/species/<common_name>` → `v3/species.html`
- `/device` → `v3/device.html`

The routes use the read-only helpers in `app/web/v3.py`:

- `build_overview_context`
- `enrich_life_list`
- `get_species_content`
- `get_confidence_distribution`

The Activity page uses the existing paginated route for its no-JavaScript
fallback and progressively loads subsequent HTML pages. No new API route is
required.

## Release validation

1. Compile every Jinja template.
2. Run Flask route tests against a temporary SQLite fixture.
3. Confirm all V3 static assets return HTTP 200.
4. Review 320, 375, 768, 1024, and 1440 pixel layouts.
5. Test keyboard-only navigation and reduced motion.
6. Test Activity with JavaScript enabled and disabled.
7. Test empty, sparse, and populated station data.
8. Confirm no station database writes and no service-control calls occur.

V2 templates and `dashboard-v2.css` remain as a rollback aid until browser and
Raspberry Pi acceptance testing is complete.
