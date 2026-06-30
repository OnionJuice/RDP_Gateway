# Agent Notes

- Keep `README.md` and `README.cn.md` in sync whenever user-facing behavior, setup, configuration, troubleshooting, or limitations change.
- Keep both README files updated when GUI behavior, LaunchAgent login-start behavior, macOS packaging, signing, or quarantine handling changes.
- Keep GUI language strings, `[app].language` behavior, and both README files in sync when adding or renaming user-visible GUI text.
- Use `uv` for Python environment management and dependency installation.
- Prefer China-accessible package mirrors in setup examples, with Tsinghua PyPI as the default and Aliyun as the documented fallback.
- Do not commit local runtime state: `.venv/`, `.uv-cache/`, generated certificates, private keys, local config files, caches, logs, or packet captures.
- Run `uv run pytest` after code or protocol changes when practical.
