#!/bin/bash
# Installer for prime-gpu-availability.
# - Symlinks the plugin into SwiftBar's standard plugin folder
# - Copies the icon asset to ~/.config/prime-gpu/assets/
# - Seeds a watch.conf example and a placeholder API-key file
# - Refreshes SwiftBar if it's running

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/prime-gpu"
PLUGIN_DIR="${HOME}/Library/Application Support/SwiftBar/Plugins"
PLUGIN_SCRIPT="prime-gpu.30s.py"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: this plugin is macOS only (uname is $(uname -s))." >&2
  exit 1
fi

if [[ ! -f "${REPO_DIR}/${PLUGIN_SCRIPT}" ]]; then
  echo "error: ${PLUGIN_SCRIPT} not found in ${REPO_DIR}." >&2
  exit 1
fi

if [[ ! -d /Applications/SwiftBar.app ]]; then
  echo "note: SwiftBar.app not found in /Applications."
  echo "      Install it first: brew install --cask swiftbar"
  echo "      (continuing anyway so the file layout is ready)"
fi

# --- 1. Asset -----------------------------------------------------------------
mkdir -p "${CONFIG_DIR}/assets"
cp "${REPO_DIR}/assets/prime-logo-template.png" "${CONFIG_DIR}/assets/"
chmod 644 "${CONFIG_DIR}/assets/prime-logo-template.png"
echo "✓ icon  → ${CONFIG_DIR}/assets/prime-logo-template.png"

# --- 2. API key stub ---------------------------------------------------------
if [[ ! -f "${CONFIG_DIR}/key" ]]; then
  if [[ -r "${HOME}/.config/prime-balance/key" ]] \
     && ! grep -q '^PASTE_' "${HOME}/.config/prime-balance/key"; then
    echo "✓ key   → reusing ${HOME}/.config/prime-balance/key (auto-detected)"
  else
    umask 077
    printf '%s' 'PASTE_YOUR_PRIME_INTELLECT_API_KEY_HERE' > "${CONFIG_DIR}/key"
    chmod 600 "${CONFIG_DIR}/key"
    echo "✓ key   → ${CONFIG_DIR}/key  (placeholder — edit me)"
  fi
else
  echo "✓ key   → ${CONFIG_DIR}/key  (already exists, left untouched)"
fi

# --- 3. Watch list seed ------------------------------------------------------
if [[ ! -f "${CONFIG_DIR}/watch.conf" ]]; then
  cp "${REPO_DIR}/watch.conf.example" "${CONFIG_DIR}/watch.conf"
  chmod 644 "${CONFIG_DIR}/watch.conf"
  echo "✓ watch → ${CONFIG_DIR}/watch.conf  (seeded — edit to your needs)"
else
  echo "✓ watch → ${CONFIG_DIR}/watch.conf  (already exists, left untouched)"
fi

# --- 4. Plugin symlink -------------------------------------------------------
chmod +x "${REPO_DIR}/${PLUGIN_SCRIPT}"
chmod +x "${REPO_DIR}/bin/prime-deploy.py" "${REPO_DIR}/bin/prime-auth-check.py"
mkdir -p "${PLUGIN_DIR}"
ln -sfn "${REPO_DIR}/${PLUGIN_SCRIPT}" "${PLUGIN_DIR}/${PLUGIN_SCRIPT}"
echo "✓ plug  → ${PLUGIN_DIR}/${PLUGIN_SCRIPT} → ${REPO_DIR}/${PLUGIN_SCRIPT}"

# --- 5. SwiftBar plugin folder pref + refresh -------------------------------
defaults write com.ameba.SwiftBar PluginDirectory "${PLUGIN_DIR}" >/dev/null
defaults write com.ameba.SwiftBar PluginDirectoryResolvedPath "${PLUGIN_DIR}" >/dev/null

if pgrep -x SwiftBar >/dev/null; then
  open "swiftbar://refreshallplugins" >/dev/null 2>&1 || true
  echo "✓ refresh signal sent to SwiftBar"
else
  echo "note: SwiftBar isn't running. Launch it with: open -a SwiftBar"
fi

echo
echo "Next:"
echo "  1. Paste your Prime Intellect API key into ${CONFIG_DIR}/key"
echo "     (skip if it was auto-detected from prime-balance above)."
echo "     The key needs both 'availability:read' and (optional) 'billing:read'"
echo "     scopes. If you have two keys with different scopes, you can keep"
echo "     them in ${CONFIG_DIR}/key and ${HOME}/.config/prime-balance/key —"
echo "     the plugin will try each per endpoint."
echo "  2. Edit ${CONFIG_DIR}/watch.conf to list the GPU configs you want."
echo "  3. Refresh SwiftBar (right-click menu item → Refresh, or run:"
echo "     open 'swiftbar://refreshallplugins')."
