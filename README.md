# python2appimage

`python2appimage` adalah program python3 berbasis CLI untuk mengemas proyek Python menjadi [AppImage](https://appimage.org/) yang portabel dan mandiri. Hasilnya sudah membawa runtime Python dan dependensinya sendiri, sehingga bisa dijalankan di sebagian besar distribusi Linux tanpa perlu menginstal apa pun.

## Persyaratan

- Linux (`x86_64` atau `aarch64`)
- Python 3.8 atau lebih baru
- Koneksi internet saat build pertama (runtime Python dan `appimagetool` diunduh dari GitHub lalu disimpan di `~/.cache/python2appimage`)

## Instalasi

```
git clone https://github.com/hyunazmi/python2appimage
cd python2appimage
python -m venv .venv
source .venv/bin/activate
pip install .
```

## Penggunaan

```
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

```
python2appimage -d ./my_project -t cli -o dist/
```

## Kredit

- [python-appimage](https://github.com/niess/python-appimage) untuk runtime Python siap pakai
- [appimagetool](https://github.com/AppImage/appimagetool) untuk membuat AppImage

## Lisensi

[MIT](LICENSE)
