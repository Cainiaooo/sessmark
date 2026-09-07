# sessmark-herdr

Optional HerdR adapter for the independent `sessmark` session marking library.

[English](../../README.md) | [中文](../../README.zh.md)

From the sessmark repository root:

```powershell
python -m pip install -e ".[ui]" -e adapters/herdr
herdr plugin link "$PWD/plugins/herdr"
```

Marketplace install (public repo + GitHub topic `herdr-plugin`):

```powershell
herdr plugin install Cainiaooo/sessmark/plugins/herdr
```

The plugin manifest and Windows/macOS launchers live in `plugins/herdr` of the
source repository. Installation and keybindings: [HerdR integration](../../docs/herdr.en.md)
([中文](../../docs/herdr.md)). The TUI follows the OS language, or `SESSMARK_LANG=en` / `zh`.

`sessmark-herdr tag keep`, `note`, `mark`, `ui`, `sync`, and `resume` connect through
`HERDR_BIN_PATH`. The core CLI never imports this package. HerdR 0.8.2+ is required.
