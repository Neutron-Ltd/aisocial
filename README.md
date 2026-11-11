# NEUTX — AI Social

**NEUTX (Neutron Text-to-X)** is a self-hosted AI social media studio. You
pick a template, write a prompt (optionally with a hero image), and your own
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) server renders a video
or image. NEUTX then schedules it and publishes it to **TikTok, Instagram,
YouTube and X** through their official APIs.

> **Status: working prototype.** The full loop of sign up, generate,
> review, schedule and publish works, and it's covered by automated tests.
> Publishing needs developer apps you create on each platform (see
> [docs/platform-setup.md](docs/platform-setup.md)). It's built for a single
> server and small teams, not yet for large multi-tenant deployments. See
> [Limitations](#limitations).

## Features

- **Accounts:** sign up and sign in with email and password, see and revoke
  active sessions, export your data, delete your account.
- **Generation Studio:** a four-step wizard (template, content, review,
  schedule) that submits real ComfyUI workflows and shows the result as it
  renders.
- **Templates:** save an engine, aspect ratio, style prompt and negative
  prompt, and reuse them.
- **Media Library:** browse, search, filter, preview, download, upload and
  bulk-delete generated and uploaded media.
- **Calendar:** month and week views, drag-and-drop rescheduling, editing,
  cancelling, and per-platform publish status with a retry for failed
  destinations.
- **Publishing:** a background scheduler publishes due posts. Platform
  tokens are encrypted at rest and refreshed automatically.
- **Connections:** OAuth connect and disconnect per platform, plus live
  ComfyUI status (VRAM, queue, and which workflows are missing models).

## Quick start

You need Python 3.10+ (tested on 3.11).

```bash
git clone https://github.com/Neutron-Ltd/aisocial.git
cd aisocial
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set NEUTX_SECRET_KEY in .env, e.g. from:
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'

python -m neutx            # http://127.0.0.1:8080/
```

Open <http://127.0.0.1:8080/>, create an account, and you're in the
dashboard.

### Try it without a GPU

`tests/fake_comfyui.py` speaks the same HTTP API as ComfyUI and returns
generated test images and videos, so you can try the whole flow on a
laptop:

```bash
pip install -r requirements-dev.txt
python tests/fake_comfyui.py --port 8188   # in a second terminal
```

### Real ComfyUI

```bash
scripts/setup_comfyui.sh                       # clones ComfyUI v0.19.3 into ./ComfyUI (git-ignored)
pip install -r ComfyUI/requirements.txt         # ideally in its own venv, with the right PyTorch for your GPU
python ComfyUI/main.py --listen 127.0.0.1 --port 8188
```

Point `COMFYUI_URL` at it. The Connections page lists any model files a
workflow needs that ComfyUI doesn't have yet. Download them into the
matching `ComfyUI/models/<folder>/`.

## Workflows

Bundled workflows live in [workflows/](workflows/). Each file is a ComfyUI
**API-format** prompt plus a `meta` block:

| File | Engine | Output | Models |
| --- | --- | --- | --- |
| `sd15_image.json` | Stable Diffusion 1.5 | Image | `checkpoints/v1-5-pruned-emaonly-fp16.safetensors` |
| `flux_dev_image.json` | Flux.1 [dev] | Image | `checkpoints/flux1-dev-fp8.safetensors` |
| `wan21_t2v.json` | Wan 2.1 1.3B | Video | `diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors`, `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `vae/wan_2.1_vae.safetensors` |
| `wan21_i2v.json` | Wan 2.1 14B | Video from image | as above, plus `diffusion_models/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors` and `clip_vision/clip_vision_h.safetensors` |

To add your own: export a workflow from ComfyUI with **Save (API)**, put it
in `{"meta": {...}, "prompt": <exported JSON>}`, and replace values with
placeholders such as `"{{prompt}}"`, `"{{negative_prompt}}"`, `"{{width}}"`,
`"{{height}}"`, `"{{seed}}"`, `"{{steps}}"`, `"{{cfg}}"`, `"{{length}}"`,
`"{{fps}}"`, `"{{image}}"` and `"{{filename_prefix}}"`. Use the bundled files
as a reference for the `meta` keys (`kind`, `image_input`, `sizes`,
`quality`, `lengths`, `defaults`, `models`).

## Configuration

All configuration comes from environment variables or a git-ignored `.env`
file. [.env.example](.env.example) documents every option. The important
ones:

| Variable | Purpose |
| --- | --- |
| `NEUTX_SECRET_KEY` | **Required.** Encrypts stored platform tokens and signs media links. |
| `PUBLIC_BASE_URL` | The URL users reach NEUTX at. Used for OAuth redirects and Instagram media links. |
| `COMFYUI_URL` | Your ComfyUI server. |
| `DATA_DIR` | SQLite database and media files (default `./data`). |
| `ALLOW_SIGNUP` | Set to `false` once your accounts exist. |
| `<PLATFORM>_CLIENT_ID` / `_CLIENT_SECRET` | Enables TikTok, Instagram, YouTube or X. See [docs/platform-setup.md](docs/platform-setup.md). |

## Deploying

- Run one NEUTX process (`python -m neutx`). The scheduler runs inside it,
  and several processes would each try to publish the same posts.
- Put it behind an HTTPS reverse proxy (Caddy, nginx, …) and set
  `PUBLIC_BASE_URL` to the public `https://` URL. Session cookies are then
  marked `Secure` automatically.
- Back up `DATA_DIR`. Keep `NEUTX_SECRET_KEY` safe and stable.
- ComfyUI has no authentication. Keep it on a private network or bound to
  localhost, and never expose it to the internet.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run the real app against the fake ComfyUI and mocked platform
APIs. They cover auth, CSRF protection, generation jobs, media isolation
between users, OAuth (including forged state), publishing to all four
platforms, token refresh, retries and time zones.

```
neutx/            FastAPI app: routes, worker/scheduler, ComfyUI client, platform adapters
WebUI/            Front end (static HTML + vanilla JS, served by the app)
workflows/        ComfyUI workflow templates
tests/            pytest suite and fake ComfyUI server
scripts/          setup_comfyui.sh
docs/             Platform setup, original product spec
```

## Security

- Passwords are hashed with scrypt, and sessions use HttpOnly SameSite
  cookies.
- State-changing API calls require a custom header, which acts as CSRF
  protection.
- OAuth uses a `state` parameter for every platform, plus PKCE for X.
- Platform tokens are encrypted with a key derived from `NEUTX_SECRET_KEY`.
- Uploads are type-checked by content, stored under random names, and only
  served to their owner.
- Pages are sent with a strict Content-Security-Policy.
- Sign-in and sign-up are rate-limited.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Limitations

- **Platform rules still apply.** Unaudited TikTok apps can only post
  privately, Instagram needs a public https `PUBLIC_BASE_URL`, and YouTube
  and X have quotas and access tiers.
- **No live progress.** Generation progress shows phases (queued, rendering,
  done), not per-step percentages.
- **Single process.** Rate limiting is in-memory, and the scheduler expects
  exactly one server process. Behind a proxy, rate limits are per proxy IP.
- **Unbuilt features.** There's no email verification or password-reset
  email, no team workspaces, and no billing.
- **Front end.** Tailwind CSS loads from its CDN at runtime, which is fine
  for a prototype. For production, precompile the CSS.

## License

[MIT](LICENSE) © 2026 Shamir Shakher, Neutron Ltd.

ComfyUI (GPL-3.0), model weights, Tailwind CSS, Lucide and Google Fonts are
third-party projects under their own licenses and aren't part of this
repository.
