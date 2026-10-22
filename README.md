# 🔔 Bell Sekolah

Bel sekolah otomatis yang berjalan di server (Linux) dan terhubung ke speaker lewat jack audio.
Halaman web hanya untuk **mengontrol** — bel tetap bunyi walau browser ditutup. Tampilan modern & ramah HP.

## Fitur
- Banyak **jadwal** (mis. Senin, Selasa–Kamis, Jumat) dengan jam & suara custom per bel
- **Preset** (Harian, Ujian, dst.) — tiap hari bisa diarahkan ke jadwal berbeda
- **Mode upacara**: centang di hari apa pun (atau pilih tanggal) → pakai jadwal upacara
- Unggah suara sendiri (mp3/wav/ogg/m4a), tombol tes, volume
- Otomatis jalan saat server menyala, tanpa library tambahan (hanya Python 3)

## Instalasi (Ubuntu/Debian)
```bash
curl -fsSL https://raw.githubusercontent.com/fikrudzulfahmi/bell-sekolah/main/install.sh | sudo bash
```
Lalu buka `http://IP-SERVER:8099` dari HP/komputer di jaringan yang sama.

1. Colok speaker/amplifier ke jack audio server
2. Jalankan `alsamixer` sekali → pastikan **Master** tidak mute
3. Di panel: tes suara → **Aktifkan bel otomatis**

## Update
Jalankan perintah instalasi yang sama. Jadwal & suara tersimpan di `/var/lib/bell-sekolah` dan tidak terhapus.

## Pengaturan
`/etc/default/bell-sekolah`
- `BELL_PORT` port web (default 8099)
- `BELL_PASSWORD` kunci panel (user `admin`)
- `BELL_PLAYER` perintah pemutar kustom (opsional), mis. `mpg123 -q`

Setelah mengubah: `sudo systemctl restart bell-sekolah`. Zona waktu: `sudo timedatectl set-timezone Asia/Jakarta`.

## Catatan
- Bel yang jamnya terlewat saat server mati tidak dibunyikan susulan
- Log: `journalctl -u bell-sekolah -f`
- Uji tanpa speaker: `BELL_PLAYER=/bin/true python3 bell.py`
