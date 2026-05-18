# Publication Checklist

Use this checklist before making the repository public or copying it into a public repository.

## Source tree

- [ ] No real `.pptx`, `.ppt`, `.key`, voice recordings, generated MP4/WAV/M4A/MP3 files, rendered slide images, or cache directories are tracked.
- [ ] No real `manifest.json`, `report.json`, `notes.json`, pipeline logs, or QC outputs from private presentations are tracked.
- [ ] No `.env`, API keys, cloud tunnel URLs, personal hostnames, private IPs, GitHub tokens, Hugging Face tokens, or messaging identifiers are tracked.
- [ ] Example paths are generic (`local_inputs/`, `local_outputs/`, `/path/to/...`) and not tied to a private machine.
- [ ] Example text is generic and not copied from a private presentation.

## Git history

The current working tree can be clean while old commits still contain private data. Before flipping a private repository to public, inspect history or publish from a clean export.

Recommended safe-publication approaches:

1. **Clean export into a new repository**

   ```bash
   git archive --format=tar HEAD | tar -x -C /tmp/pptx-voice-video
   cd /tmp/pptx-voice-video
   git init
   git add .
   git commit -m "initial public release"
   ```

2. **History rewrite if you must preserve history**

   Use a tool such as `git filter-repo` and re-scan before publishing.

## Automated checks

Run these from the repository root:

```bash
git status --short
git ls-files | grep -Ei '\.(pptx|ppt|key|mp4|wav|m4a|mp3|png|jpg|jpeg)$' && echo "review tracked media"
git grep -n -Ei 'token|secret|password|api[_-]?key|BEGIN (RSA|OPENSSH|PRIVATE)|cloudflare|ngrok|tailscale|@[A-Za-z0-9._%+-]+\.[A-Za-z]{2,}|/home/|/root/|/workspace/' -- . ':!PUBLICATION_CHECKLIST.md'
python -m pytest -q
```

Treat grep findings as review prompts. Some words such as `token` may appear in security code or documentation without being secrets.

## License and model notes

- Add a project license before public release.
- Document that users are responsible for complying with the licenses of any TTS models they download or configure.
- Do not bundle model weights unless the model license and hosting policy allow redistribution.

## Runtime privacy notice

Document that the application is local-first, but model downloads may contact the configured model registry. Users who need offline operation should pre-download models and point `model_id` to a local path.
