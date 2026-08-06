# Dashboard V2 — RC1.1 UX foundation

## Product question

Dashboard V2 answers **“What wildlife has visited today?”** before it answers
“How is the Raspberry Pi doing?” The overview therefore orders information as:

1. station identity and listening state;
2. today’s detection and species totals;
3. narrative wildlife highlights;
4. latest visitors;
5. discoveries, streak, and activity timeline;
6. recordings, weather placeholder, and compact station health.

The Device page retains full technical detail without promoting it into the
primary wildlife story.

## RC1.1 additions

- **Today’s Highlights** turns aggregate observations into three short stories:
  the most active visitor today, new Life List additions this week, and the
  current season’s last-30-day activity.
- Activity cards now label the existing detector value explicitly as
  **BirdNET**, avoiding the ambiguous single word “confidence.”
- Every full activity card contains an accessible disclosure for explainable
  verification. Until Verification V2 data is integrated it truthfully reports
  “BirdNET only.”
- The activity introduction explains the difference between detector and
  verification confidence without blocking on calibration.

All new overview data comes from bounded, read-only SQLite aggregate queries.
No API response, migration, recorder, detector, or deployment contract changed.

## Verification V2 presentation contract

The UI is deliberately duck-typed and has no import from `app.verification`.
When the approved integration layer attaches a `verification` mapping to a
detection, the presentation accepts:

```json
{
  "status": "verified",
  "score": 0.94,
  "explanation": "Independent evidence supports this observation.",
  "evidence": [
    {
      "source": "Seasonal occurrence",
      "verdict": "support",
      "reason": "This species is expected here in August."
    },
    {
      "source": "Audio quality",
      "verdict": "neutral",
      "reason": "The clip is usable but contains light wind."
    }
  ]
}
```

Supported evidence verdicts are `support`, `neutral`, and `oppose`. Missing
verification data uses the explicit BirdNET-only state. Representative values
must never be presented as real station evidence.

The future integration query should join `detections`, `verifications`, and
`verification_results` in the repository layer, then normalize rows into this
mapping. Templates must not query verification tables directly.

## Responsive and accessible behavior

- The new highlight grid is one column by default and becomes a two-column
  editorial arrangement at 672px.
- Verification disclosures use native `details`/`summary`, require no
  JavaScript, remain keyboard operable, and retain 44px touch targets.
- Supporting and contradicting evidence use both text and border color, never
  color alone.
- Existing reduced-motion, focus, semantic heading, audio, and progressive
  enhancement behavior remains intact.

## Performance expectations

Dashboard V2 adds three compact aggregate queries to the overview request and
no new browser dependency. New presentation CSS is under 5 KiB uncompressed;
the verification disclosure adds no work until opened. Queries operate on the
existing detection timestamp/species data and should be measured against the
production database before RC1.1 promotion.

## Prior dashboard branch

`feature/dashboard-american-robin` contains a useful visual-system experiment,
Woodland theme work, copied production candidates, a species index, and prior
screenshots. It was not reused or merged because RC1.1 requires a clean
Foundation Phase baseline. HQ can review it independently for later asset or
theme migration after the Design and Integration teams approve those sources.

## Validation evidence

Validation ran on Windows with Python 3.12.10 and a disposable SQLite database
outside both Git worktrees.

- Dashboard-specific tests: `2 passed in 0.05s`.
- `ruff check app tests scripts`: passed.
- `python -m compileall app tests scripts`: passed.
- `git diff --check`: passed.
- All 18 V3 templates compiled.
- `/`, `/activity`, `/life-list`, a valid species page, `/device`,
  `/api/dashboard`, and `/api/metrics` returned HTTP 200.
- `/health` returned HTTP 200 with only its Linux hardware collector mocked;
  the endpoint contract and implementation were not changed.
- Mean overview render time across 25 Flask test-client requests was 6.58 ms on
  the development machine.
- The full repository test command is blocked during collection because the
  workspace-local Windows environment does not include the heavyweight
  `birdnet` runtime dependency. No Dashboard test failed.

Screenshots:

- [Overview desktop](screenshots/dashboard-v2-overview-desktop.png)
- [Overview narrow layout](screenshots/dashboard-v2-overview-mobile.png)
- [Verification-ready Activity page](screenshots/dashboard-v2-verification-desktop.png)

The installed headless Chrome build enforces a 500px minimum layout viewport;
the narrow capture is therefore 500px. CSS remains mobile-first below that
width, but an exact 360px physical-device pass remains an integration task.
