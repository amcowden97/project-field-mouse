#!/usr/bin/env bash
set -euo pipefail

echo
echo "=================================="
echo "Dashboard V3 Milestone 4"
echo "=================================="
echo

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

cat > app/web/templates/v3/components/section_header.html <<'HEADER'
<div class="pfm-section-header">

    <h2>{{ title }}</h2>

    {% if subtitle %}
    <p>{{ subtitle }}</p>
    {% endif %}

</div>
HEADER

cat >> app/web/static/css/dashboard-v3.css <<'CSS'

/* =====================================================
   SECTION HEADERS
   ===================================================== */

.pfm-section-header {

    display:flex;

    justify-content:space-between;

    align-items:center;

    margin-bottom:16px;

}

.pfm-section-header h2 {

    margin:0;

    font-size:1.1rem;

}

.pfm-section-header p {

    margin:0;

    color:#777;

    font-size:.9rem;

}

CSS

echo
echo "✓ Section header component installed."
echo
echo "Milestone 4 complete."
