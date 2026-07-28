#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "Project Field Mouse"
echo "Dashboard V3 - Milestone 3"
echo "========================================"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p app/web/templates/v3/components
mkdir -p app/web/static/css
mkdir -p app/web/static/js

cat > app/web/templates/v3/components/hero.html <<'HERO'
<section class="pfm-hero">

    <div class="pfm-hero-image">

        <img
            src="{{ url_for('static', filename='img/branding/project-field-mouse-cohesive-banner.png') }}"
            alt="Project Field Mouse">

    </div>

    <div class="pfm-hero-content">

        <h1>Project Field Mouse</h1>

        <p>Nature Connected</p>

    </div>

</section>
HERO

cat > app/web/templates/v3/components/field_station.html <<'FIELD'
<section class="pfm-card">

    <header class="pfm-card-header">

        <h2>Field Station</h2>

    </header>

    <div class="pfm-card-body">

        <p><strong>Backyard Sanctuary</strong></p>

        <p>Status: Listening</p>

        <p>Today's Species: --</p>

        <p>Today's Detections: --</p>

        <p>Last Detection: --</p>

    </div>

</section>
FIELD

echo
echo "✓ Hero component created"
echo "✓ Field Station component created"
echo
echo "Milestone 3 scaffold complete."
