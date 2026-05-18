# Browser Download Helper

This optional FastAPI helper lets a browser-only device download files from a local workstation or server through short-lived tokenized links. It can also receive files through `magic-wormhole` when the `wormhole` CLI is installed.

The helper is not required for the main PPTX-to-video pipeline.

## What it does

1. Accepts a magic-wormhole code from a browser.
2. Runs `wormhole receive ...` on the server.
3. Stores the received file under `downloads/`.
4. Creates a random `/download/<token>` link.
5. Optionally creates tokenized links for files that already exist under explicitly allowed roots.

Expose this app only on a trusted network or behind your own authentication/tunnel. Download tokens are random but are not a replacement for network access control.

## Install

```bash
cd tools/wormhole_web_recv
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The `wormhole` command must be on `PATH` if you want receive-by-code support:

```bash
command -v wormhole
```

## Run

```bash
uvicorn app:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

If accessing from another device, bind to the appropriate private-network interface and use your own secure network or tunnel.

## Share an already generated file

By default, only files inside `downloads/` can be shared. To allow an output directory, set `WORMHOLE_WEB_ALLOWED_ROOTS`:

```bash
WORMHOLE_WEB_ALLOWED_ROOTS=/path/to/pptx-voice-video/local_outputs:/path/to/pptx-voice-video/tools/wormhole_web_recv/downloads   uvicorn app:app --host 127.0.0.1 --port 8765
```

Then enter a file path that is inside one of the allowed roots, for example:

```text
/path/to/pptx-voice-video/local_outputs/demo/final.mp4
```

The UI returns a `/download/<token>` link for that file.

## Receive by wormhole code

Example command equivalent:

```bash
wormhole receive 7-example-code --accept-file --output-file downloads/ --hide-progress
```

In the UI, enter the code and optionally a safe output filename.

## Environment variables

- `WORMHOLE_WEB_ALLOWED_ROOTS`: colon-separated roots allowed for existing-file links.
- `WORMHOLE_WEB_TOKEN_TTL_SECONDS`: token lifetime; default 24 hours.
- `WORMHOLE_WEB_TIMEOUT_SECONDS`: wormhole receive timeout; default 2 hours.

## Security notes

- Download links use random URL-safe tokens.
- Token entries are in-memory and expire after the configured TTL.
- Existing-file links are restricted to `WORMHOLE_WEB_ALLOWED_ROOTS`.
- Path traversal such as `../` is rejected.
- Do not expose this helper directly to the public internet without additional access control.

## Tests

```bash
cd tools/wormhole_web_recv
pytest -q
```
