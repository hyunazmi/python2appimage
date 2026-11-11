# python2appimage

Build an AppImage from a Python project.

## Install

```
pip install .
```

## Usage

```
python2appimage --help
python2appimage -d ./my_project -t cli -o dist/
```

Equivalent: `python -m python2appimage ...`

## Development

```
pip install -e ".[dev]"
ruff check .
```

## Layout

| File | Responsibility |
|---|---|
| `constants.py` | constants, regexes, shell templates |
| `errors.py` | `Error`, `UsageError` |
| `logger.py` | stderr logger |
| `fsutils.py` | filesystem helpers |
| `options.py` | option table, help/version text, argparse parser |
| `config.py` | `Config` and argument validation |
| `project.py` | project / entry point / output path detection |
| `icons.py` | icon detection and placeholder |
| `download.py` | download and cache of Python runtime and appimagetool |
| `templates.py` | `.desktop` and `AppRun` generation |
| `builder.py` | AppImage build pipeline and `run()` |
| `cli.py` | `main()` and exit codes |

## License

MIT
