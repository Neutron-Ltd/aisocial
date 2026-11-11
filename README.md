# NEUTX — AI Social

A clickable UI prototype for **NEUTX (Neutron Text-to-X)**, an AI-powered
social media tool that turns simple inputs into platform-ready posts. You
pick a template, add a prompt or image, review the AI-generated video or
image, and schedule it to TikTok, Instagram, YouTube or X.

> **Status: prototype.** The pages are static HTML with mock data and
> simulated interactions. There is no backend, no real authentication and no
> real social-media integration yet. The design targets
> [ComfyUI](https://github.com/comfyanonymous/ComfyUI) as the render engine.

## Pages

| Page | File | What it shows |
| --- | --- | --- |
| Landing | `WebUI/index.html` | Hero, product demo teaser, feature grid |
| Sign up / onboarding | `WebUI/auth.html` | Account form and mock social OAuth step |
| Dashboard | `WebUI/dashboard.html` | Stats, upcoming queue, recent renders |
| Generation Studio | `WebUI/studio.html` | Four-step wizard: template, content, review, schedule |
| Calendar | `WebUI/calendar.html` | Monthly schedule with drag-and-drop posts |
| Template Builder | `WebUI/template.html` | Default prompts and resolution, JSON payload preview |
| Media Library | `WebUI/media.html` | Generated asset browser |
| Connections | `WebUI/connections.html` | Social accounts, render endpoints, API key, webhooks |
| Settings | `WebUI/settings.html` | Profile, posting defaults, notifications, billing |

The original product spec is in [docs/product-spec.md](docs/product-spec.md).

## Quick start

You need Python 3.8 or newer. There are no third-party Python dependencies.

```bash
git clone https://github.com/Neutron-Ltd/aisocial.git
cd aisocial
cp .env.example .env          # optional: adjust COMFYUI_URL, port
python3 scripts/serve.py      # then open http://127.0.0.1:8080/
```

You can also open `WebUI/index.html` directly in a browser; the pages then
fall back to the default ComfyUI URL (`http://localhost:8188`).

The pages load Tailwind CSS, Lucide icons and Google Fonts from public CDNs,
so an internet connection is required.

## Configuration

All site-specific values come from environment variables (or a local `.env`
file, which is git-ignored). See [.env.example](.env.example).

| Variable | Default | Used by |
| --- | --- | --- |
| `COMFYUI_URL` | `http://localhost:8188` | Studio and Connections pages (via generated `config.js`) |
| `WEBUI_HOST` | `127.0.0.1` | `scripts/serve.py` |
| `WEBUI_PORT` | `8080` | `scripts/serve.py` |
| `COMFYUI_REPO` / `COMFYUI_REF` / `COMFYUI_DIR` | upstream, v0.19.3, `./ComfyUI` | `scripts/setup_comfyui.sh` |

If you host `WebUI/` as plain static files instead of using `serve.py`, copy
`WebUI/config.example.js` to `WebUI/config.js` and edit it.

## Optional: ComfyUI

ComfyUI is **not** included in this repository. It's a separate project
licensed under GPL-3.0. To fetch the version this prototype was designed
against into `./ComfyUI` (git-ignored):

```bash
scripts/setup_comfyui.sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r ComfyUI/requirements.txt
python ComfyUI/main.py --listen 127.0.0.1 --port 8188
```

Model weights are not distributed here. Download them separately under the
terms of their own licenses.

## Project layout

```
WebUI/          Static HTML pages, shared bridge.css / bridge.js
scripts/        serve.py (local preview server), setup_comfyui.sh
docs/           Product spec
```

## Security

The preview server is for local development only. To report a
vulnerability, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Shamir Shakher, Neutron Ltd.

Third-party projects referenced here (ComfyUI, Tailwind CSS, Lucide, Google
Fonts) are distributed under their own licenses.
