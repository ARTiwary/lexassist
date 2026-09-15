#!/bin/sh
# Run by Netlify at build time. Substitutes the API_BASE environment
# variable (set in the Netlify dashboard, not committed to source
# control) into config.js, so the deployed site knows where the backend
# lives without the URL ever appearing in the repository.
#
# If API_BASE isn't set (e.g. a local run of this script), config.js is
# left with no override, and app.js falls back to auto-detecting
# localhost -- see config.js for details.
set -e

if [ -z "$API_BASE" ]; then
  echo "API_BASE is not set -- leaving config.js as the local-dev default."
  exit 0
fi

sed "s|__API_BASE__|$API_BASE|g" config.template.js > config.js
echo "Wrote config.js with API_BASE=$API_BASE"
