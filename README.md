# python2appimage

[![Linux](https://img.shields.io/badge/Platform-Linux-FCC624?style=flat&logo=linux&logoColor=black)](https://www.linux.org/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![AppImage](https://img.shields.io/badge/Output-AppImage-4CAF50?style=flat)](https://appimage.org/)
[![License](https://img.shields.io/github/license/hyunazmi/python2appimage?style=flat&color=blue)](https://github.com/hyunazmi/python2appimage/blob/main/LICENSE)

`python2appimage` adalah program python3 berbasis CLI untuk mengemas proyek Python menjadi [AppImage](https://appimage.org/) yang portabel dan mandiri. Hasilnya sudah membawa runtime Python dan dependensinya sendiri, sehingga bisa dijalankan di sebagian besar distribusi Linux tanpa perlu menginstal apa pun.

## Persyaratan

- Linux (`x86_64` atau `aarch64`)
- Python 3.8 atau lebih baru

## Instalasi

```bash
# clone repositori dari github
git clone https://github.com/hyunazmi/python2appimage

# masuk ke folder project
cd python2appimage

# buat virtual environment
python3 -m venv .venv

# aktifkan virtual environment
source .venv/bin/activate

# install python2appimage
pip install .
```

## Penggunaan

```bash
python2appimage --help
```

Opsi umum:

| Opsi | Keterangan |
|---|---|
| `-d, --directory=DIR` | direktori proyek (default: direktori saat ini) |
| `-e, --entry=ENTRY` | yang dijalankan: `MODULE`, `MODULE:FUNCTION` atau `SCRIPT.py` (default: terdeteksi otomatis) |
| `-t, --type=TYPE` | tipe aplikasi: `gui` atau `cli` (default: `gui`) |
| `-i, --icon=FILE` | ikon aplikasi: `.png`, `.svg` atau `.xpm` (default: terdeteksi otomatis) |
| `-o, --output=FILE` | file keluaran (default: `NAME-VERSION-ARCH.AppImage`) |
| `-p, --python-version=VER` | versi Python yang dibundel (default: `3.11`) |
| `-n, --no-compile` | jangan precompile bytecode (`.pyc`) |
| `-q, --quiet` | sembunyikan pesan progres |

## Contoh

```bash
python2appimage -d ./my_project -t cli -o dist/
```

## Kredit

- [python-appimage](https://github.com/niess/python-appimage) untuk runtime Python siap pakai
- [appimagetool](https://github.com/AppImage/appimagetool) untuk membuat AppImage

## Lisensi

[MIT](LICENSE)
