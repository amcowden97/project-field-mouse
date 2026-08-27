# v1.1.0 screenshot package

The staged images use public-safe data from the approved RC1.1 Dashboard/Experience
validation captures. They demonstrate the exact integrated visual system without
publishing production coordinates, configuration, or private audio.

| Requested view | Asset | Status |
|---|---|---|
| Overview | [Overview desktop](../../screenshots/v1.1.0/overview-desktop.png) | Ready for HQ review |
| Activity | [Activity desktop](../../screenshots/v1.1.0/activity-desktop.png) | Ready for HQ review |
| Species | [Species desktop](../../screenshots/v1.1.0/species-desktop.png) | Ready for HQ review |
| Life List | [Life List mobile](../../screenshots/v1.1.0/life-list-mobile-390.png) | Ready for HQ review |
| Mobile dashboard | [Overview 390 px](../../screenshots/v1.1.0/overview-mobile-390.png) | Ready for HQ review |
| Device | — | Pending normal-browser capture |

## Capture requirements for Device

- Use candidate `fb9b131` through the trusted local station network.
- Capture at 1440 × 1100 or a comparable desktop viewport.
- Do not expose exact coordinates, webhook values, tokens, private paths, or browser UI.
- Confirm the cleanup timer is shown as available and the storage/forecast presentation
  matches the accepted candidate.
- Save as `docs/screenshots/v1.1.0/device-desktop.png`, update the table above, and obtain
  HQ visual approval before publishing.

Automated capture was attempted with local Edge and the Pi's Chromium. Both headless
renderers failed before producing an image; production services and soak state were not
changed. A normal browser screenshot is the lowest-risk remaining path.

