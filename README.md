# python2appimage

python2appimage is a command-line tool that packages a Python project into a portable, self-contained AppImage. The result bundles its own Python runtime and dependencies, so it runs on most Linux distributions without installing anything. It works for both GUI and CLI applications.

## Requirements

- Linux (`x86_64` or `aarch64`)
- Python 3.8 or newer
- Internet access on the first build (the Python runtime and `appimagetool` are downloaded from GitHub and cached in `~/.cache/python2appimage`)

## Install

```
git clone https://github.com/hyunazmi/python2appimage
cd python2appimage
python -m venv .venv
source .venv/bin/activate
pip install .
```

## Usage

```
python2appimage --help
```

Common options:

| Option | Description |
|---|---|
| `-d, --directory=DIR` | project directory (default: current directory) |
| `-e, --entry=ENTRY` | what to run: `MODULE`, `MODULE:FUNCTION` or `SCRIPT.py` (default: auto-detected) |
| `-t, --type=TYPE` | application type: `gui` or `cli` (default: `gui`) |
| `-i, --icon=FILE` | application icon: `.png`, `.svg` or `.xpm` (default: auto-detected) |
| `-o, --output=FILE` | output file (default: `NAME-VERSION-ARCH.AppImage`) |
| `-p, --python-version=VER` | bundled Python version (default: `3.11`) |
| `-n, --no-compile` | do not precompile bytecode (`.pyc`); precompiling makes startup faster |
| `-q, --quiet` | suppress progress messages |

## Example

```
python2appimage -d ./my_project -t cli -o dist/
```

## Credits

- [python-appimage](https://github.com/niess/python-appimage) for the prebuilt Python runtimes
- [appimagetool](https://github.com/AppImage/appimagetool) for creating the AppImage

## License

MIT
