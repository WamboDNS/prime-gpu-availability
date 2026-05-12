# prime-gpu-availability

A [SwiftBar](https://swiftbar.app) plugin that watches
[PrimeIntellect](https://www.primeintellect.ai) GPU availability against a
list of `{gpu_type, min, max}` configurations you care about — and shows
a glance-able badge in the macOS menu bar, next to your wallet balance.

When a watched configuration transitions from "none" to "available", you
get a native macOS notification.

![Menu-bar screenshot](assets/screenshot.png)

A filled `●N` flags configs that currently have matching offers; `·`
means none. (We keep the prime-intellect template-image icon up front
and let the glyph carry the signal — SwiftBar can't render
`templateImage=` together with `color=` or `ansi=true` on the title.)

Click the menu-bar item and the dropdown lists every matching offer
under its watched config — providers, sockets, prices, regions and
stock status. The match-header is red; each offer row underneath is
clickable to confirm-and-deploy a pod.

![Dropdown screenshot](assets/dropdown.png)

## Why

GPU supply on Prime Intellect's marketplace moves in seconds. If you're
hunting a specific shape — say `8×H100` or `4..8×H200_SXM` — you don't
want to refresh the dashboard every few minutes. This plugin does it for
you, in your menu bar, and lets you deploy a matching offer with one
click + a confirm dialog.

A sibling project, [`prime-billing-statusbar`][sibling], shows just the
wallet balance. If you already use it, this plugin shares its API-key
file automatically and supersedes it (it shows the balance too).

[sibling]: https://github.com/WamboDNS/prime-billing-statusbar

## Requirements

- macOS (Darwin)
- [SwiftBar](https://swiftbar.app) — `brew install --cask swiftbar`
- `/usr/bin/python3` (Apple's system Python — no extra packages needed)
- A PrimeIntellect API key with `availability:read` scope. Optional:
  `billing:read` scope if you want the wallet balance shown too.

## Install

```bash
git clone https://github.com/WamboDNS/prime-gpu-availability.git
cd prime-gpu-availability
./install.sh
```

The installer:

1. Copies the icon to `~/.config/prime-gpu/assets/`.
2. Seeds `~/.config/prime-gpu/watch.conf` from `watch.conf.example`.
3. Creates a placeholder API-key file at `~/.config/prime-gpu/key`
   (or reuses `~/.config/prime-balance/key` if it already has a real key).
4. Symlinks the plugin into `~/Library/Application Support/SwiftBar/Plugins/`.
5. Points SwiftBar's plugin folder at that directory and refreshes it.

Then paste your key (if it wasn't auto-detected) and edit the watch list:

```bash
$EDITOR ~/.config/prime-gpu/key          # paste your API token, one line
$EDITOR ~/.config/prime-gpu/watch.conf   # edit the configs you want to watch
open 'swiftbar://refreshallplugins'
```

## Configuration

Everything lives in `~/.config/prime-gpu/`:

| Path                         | What it is                                                 |
| ---------------------------- | ---------------------------------------------------------- |
| `key`                        | Your API token (one line, no trailing newline). `chmod 600`. |
| `watch.conf`                 | The list of GPU configurations to watch (format below).    |
| `assets/prime-logo-template.png` | The menu-bar icon (alpha-only template, 144 DPI).      |
| `state.json`                 | Auto-managed: last-seen match counts, for transition detection. |

`PRIME_CONFIG_DIR` in the environment relocates the whole directory.
`PRIME_API_KEY` overrides the key file. The plugin also falls back to
`~/.config/prime-balance/key`, so [`prime-billing-statusbar`][sibling]
users don't have to duplicate their token.

### Watch list

`watch.conf` is line-based, whitespace-separated:

```
# gpu_type           min  max  [socket]
H100_80GB            8    8
H200_141GB           4    8
A100_80GB            1    8
B300_262GB           4    8    SXM
```

- `gpu_type` matches the API's `gpuType` value exactly, case-sensitive.
- `min` and `max` are inclusive bounds on the offer's `gpuCount` (e.g.
  `4 8` matches offers that bundle 4 to 8 GPUs). Use `min == max` for
  an exact count.
- The optional 4th column filters by socket: `PCIe` or `SXM`.
- Blank lines and anything after `#` are ignored.

Real `gpuType` values seen so far:

| Family   | Token                                                             |
| -------- | ----------------------------------------------------------------- |
| Hopper   | `H100_80GB`, `H200_141GB`                                         |
| Blackwell| `B300_262GB`                                                      |
| Ampere   | `A100_80GB`, `A100_40GB`, `A6000_48GB`, `A40_48GB`, `A10_24GB`    |
| Ada      | `L4_24GB`, `RTX_PRO_6000B_96GB`                                   |
| Consumer | `RTX4090_24GB`, `RTX3090_24GB`                                    |
| CPU-only | `CPU_NODE`                                                        |

### Deploy on click

Each offer row in the dropdown is wired to a small helper at
`bin/prime-deploy.py`:

1. **Click** an offer in the dropdown.
2. A confirm dialog summarises the offer (count, GPU type, socket,
   provider, region, datacenter, price, stock) and asks *Deploy* or
   *Cancel*.
3. *Deploy* → a second dialog prompts for a **pod name** (default:
   `prime-gpu-<timestamp>`).
4. The script POSTs to `https://api.primeintellect.ai/api/v1/pods/`
   with the offer fields mapped 1:1, plus your chosen name.
5. A macOS notification reports `Pod provisioning` on success, or the
   API's error `detail` on failure.

Set `PRIME_DRY_RUN=1` in the plugin's environment to skip the actual
POST while still exercising the dialogs end-to-end (useful for testing
or before you trust the wiring).

The plugin's pod request body is intentionally minimal:

```json
{
  "pod": {
    "name": "prime-gpu-20260512-153012",
    "cloudId": "1A100.22V_SPOT",
    "gpuType": "A100_80GB",
    "socket": "PCIe",
    "gpuCount": 1,
    "dataCenterId": "FIN-03",
    "country": "FI",
    "maxPrice": 0.4515
  },
  "provider": {"type": "datacrunch"}
}
```

Optional things the API supports but the click flow doesn't set yet —
`sshKeyId`, `image`, `vcpus`, `memory`, `diskSize`, `envVars`,
`autoRestart`. If you want any of those, either edit
`bin/prime-deploy.py` or finish the pod in the dashboard.

### Refresh interval

The interval is encoded in the filename: `prime-gpu.30s.py` runs every
30 seconds. Supported suffixes: `Ns`, `Nm`, `Nh`, `Nd`. To change:

```bash
mv prime-gpu.30s.py prime-gpu.1m.py
mv ~/Library/Application\ Support/SwiftBar/Plugins/prime-gpu.{30s,1m}.py
```

The plugin issues one HTTP request per watched config (plus one for the
wallet), in parallel — so 4 watched configs at 30 s ≈ 14 k requests/day.
Bump to `1m` or `2m` if you'd rather be gentler.

### Multiple keys / split scopes

If you already have separate tokens — e.g. one with `availability:read`
and another with `billing:read` — keep them in `~/.config/prime-gpu/key`
and `~/.config/prime-balance/key` respectively. The plugin tries every
candidate per endpoint and uses whichever one is authorized.

## FAQ

**Why no auto-deploy?**

Tempting, but a fully-automatic loop spinning up `8×H200`s the moment
they appear is a great way to vaporize your wallet by accident. The
plugin sticks to a *click-to-deploy* flow: the menu-bar badge and the
macOS notification on transitions tell you something's available, and
clicking an offer in the dropdown opens a confirm dialog before any pod
is actually created.

**Why isn't my balance showing?**

Your token is probably missing the `billing:read` scope — the dropdown
will say so. Either grant it in the PrimeIntellect dashboard, or keep
using a `prime-billing-statusbar`-style billing token in
`~/.config/prime-balance/key` (the plugin will pick it up automatically).

**Why isn't my `H100_80GB` ever matching?**

Most likely there's just no `H100_80GB` supply right now — H100s in
particular sell out within seconds of appearing. The dropdown's
`none in range (N outside)` count tells you whether the type exists at
all (e.g. only 1× and 2× offers, with your range requiring 8×).

**Can I get notified when supply *disappears*, not just appears?**

Not out of the box — the plugin only fires on `0 → ≥1` transitions
right now. If you want both directions, edit the transition condition
in `prime-gpu.30s.py` (`main()`, search for `transitions.append`).

## License

MIT — see [LICENSE](LICENSE).
