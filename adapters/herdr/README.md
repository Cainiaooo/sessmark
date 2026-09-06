# sessmark-herdr

Optional HerdR adapter for the independent `sessmark` session marking library.

From the sessmark repository root:

```powershell
python -m pip install -e ".[ui]" -e adapters/herdr
herdr plugin link "$PWD/plugins/herdr"
```

The plugin manifest and Windows/macOS launchers live in `plugins/herdr` of the
source repository. Installation and keybindings are documented in `docs/herdr.md`.

`sessmark-herdr tag keep`, `note`, `mark`, `ui`, `sync`, and `resume` connect through
`HERDR_BIN_PATH`. The core CLI never imports this package. HerdR 0.8.2+ is required.
