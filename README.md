# prime-gpu-availability

A [SwiftBar](https://swiftbar.app) plugin that watches
[PrimeIntellect](https://www.primeintellect.ai) GPU availability against a
list of `{gpu_type, min, max}` configurations you care about — and shows
a glance-able badge in the macOS menu bar, next to your wallet balance.

When a watched configuration transitions from "none" to "available", you
get both a native macOS notification **and** an optional push to your
iPhone via [ntfy.sh](https://ntfy.sh).

![Menu-bar screenshot](assets/screenshot.png)

```
$2471.96   H100 ·   H200 ·   A100 ×8   B300 ·
└─ balance └─────── per-watched-row badge ──────┘
                ×N = N matching offers right now (red)
                 ·  = none (default menu-bar color)
```

Tokens with matches render in red; everything else uses the default
menu-bar text color. Click for a dropdown that lists the cheapest
offers per config (count, socket, price/hr, provider, region, stock
status).

## Why

GPU supply on Prime Intellect's marketplace moves in seconds. If you're
hunting a specific shape — say `8×H100` or `4..8×H200_SXM` — you don't
want to refresh the dashboard every few minutes. This plugin does it for
you, in your menu bar, and pokes your phone the moment something matches.

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
- *(Optional, for iPhone push)* The free [ntfy](https://ntfy.sh) iOS app.

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
| `ntfy.url`                   | *(Optional)* Full ntfy topic URL for iPhone push.          |
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

### iPhone push (ntfy)

The plugin can mirror its macOS notifications to your phone over
[ntfy.sh](https://ntfy.sh) — a free, open-source HTTP pub/sub bus with
an excellent iOS client.

1. Install the **ntfy** app from the App Store
   ([link](https://apps.apple.com/us/app/ntfy/id1625396347)).
2. Pick a long, hard-to-guess topic name — anyone who knows the topic
   can publish to it. A UUID works:
   ```bash
   echo "https://ntfy.sh/prime-gpu-$(uuidgen | tr A-Z a-z)" \
     > ~/.config/prime-gpu/ntfy.url
   chmod 600 ~/.config/prime-gpu/ntfy.url
   ```
3. Open the iOS app, tap **+**, and subscribe to the same topic
   (just the part after `ntfy.sh/`).

Test it:

```bash
curl -H 'Title: Hello from your menu bar' \
     -d 'iPhone push channel is live!' \
     "$(cat ~/.config/prime-gpu/ntfy.url)"
```

You should get a notification on your iPhone within a second or two.
The plugin uses `Priority: high` and the `rocket` tag, so alerts cut
through quiet hours if you let them.

If you'd rather self-host or use a different push service, you can
swap ntfy.sh for any service that accepts a `POST <url>` with an
arbitrary text body and `Title:` header — see `push_ntfy()` in the
plugin source.

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

## What it looks like

Menu-bar title:

```
$2471.96   H100 ·   H200 ×1   A100 ×6   B300 ×2
```

Dropdown:

```
Balance: $2471.96
Updated: 21:14:38
Watching 4 config(s), 9 match(es)
iPhone push: on
─────────────────────────────────────────────────
H100_80GB [8-8]: none in range (2 outside)
─────────────────────────────────────────────────
H200_141GB [4-8]: 1 match
  8× H200_141GB SXM5 · $27.12/hr · datacrunch · eu_north · Available
─────────────────────────────────────────────────
A100_80GB [1-8]: 6 matches
  1× A100_80GB SXM4 · $1.23/hr · massedcompute · united_states · Available
  1× A100_80GB SXM4 · $1.23/hr · massedcompute · united_states · Available
  1× A100_80GB PCIe · $1.65/hr · crusoecloud · united_states · Available
  2× A100_80GB PCIe · $2.40/hr · massedcompute · united_states · Available
  2× A100_80GB PCIe · $3.30/hr · crusoecloud · united_states · Available
  8× A100_80GB SXM4 · $22.40/hr · vultr · united_states · Available
─────────────────────────────────────────────────
B300_262GB [1-8]: 2 matches
  2× B300_262GB SXM6 · $4.89/hr · datacrunch · eu_north · Available
  2× B300_262GB SXM6 · $13.98/hr · datacrunch · eu_north · Available
─────────────────────────────────────────────────
Open dashboard
Open billing dashboard
Edit watch list
Refresh now
```

## FAQ

**Why no auto-deploy?**

Tempting, but a runaway loop spinning up `8×H200`s the moment they
appear is a great way to vaporize your wallet by accident. The plugin
sticks to *passive* signal (menu-bar badge + Mac notification + iPhone
push). The notification body includes the cheapest match's price so you
can act on it manually within a few seconds.

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

**Does this need an Anthropic / Pushover / Pushbullet account?**

No. ntfy.sh is free, anonymous, and FOSS. You can self-host it too
([docs](https://docs.ntfy.sh/install/)) — just put your own server's
URL in `ntfy.url`.

## License

MIT — see [LICENSE](LICENSE).
