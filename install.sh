#!/bin/bash
# Bell Sekolah - installer & updater (Ubuntu/Debian).
# Pasang : curl -fsSL https://raw.githubusercontent.com/fikrudzulfahmi/bell-sekolah/main/install.sh | sudo bash
# Update : jalankan perintah yang sama lagi (jadwal & suara tidak hilang).
set -e
[ "$EUID" -eq 0 ] || { echo "Jalankan dengan sudo"; exit 1; }
REPO="${BELL_REPO:-https://github.com/fikrudzulfahmi/bell-sekolah.git}"
APP=/opt/bell-sekolah; DATA=/var/lib/bell-sekolah; PORT="${BELL_PORT:-8099}"
RUNUSER="${SUDO_USER:-root}"; [ "$RUNUSER" = "root" ] && RUNUSER=bell && { id bell >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin bell; }

echo "==> Memasang paket (python3, git, pemutar suara)"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 git alsa-utils mpg123 ffmpeg >/dev/null

echo "==> Mengambil aplikasi"
if [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else rm -rf "$APP"; git clone --depth 1 "$REPO" "$APP"; fi
mkdir -p "$DATA"; chown -R "$RUNUSER" "$DATA"
usermod -aG audio "$RUNUSER"

echo "==> Membuat service"
[ -f /etc/default/bell-sekolah ] || cat > /etc/default/bell-sekolah <<EOT
BELL_PORT=$PORT
BELL_DATA=$DATA
# Isi untuk mengunci panel (login user: admin), lalu: sudo systemctl restart bell-sekolah
#BELL_PASSWORD=
EOT
cat > /etc/systemd/system/bell-sekolah.service <<EOT
[Unit]
Description=Bell Sekolah
After=network-online.target sound.target
[Service]
User=$RUNUSER
Group=audio
EnvironmentFile=/etc/default/bell-sekolah
ExecStart=/usr/bin/python3 $APP/bell.py
Restart=always
[Install]
WantedBy=multi-user.target
EOT
systemctl daemon-reload
systemctl enable bell-sekolah >/dev/null 2>&1
systemctl restart bell-sekolah

timedatectl set-timezone Asia/Jakarta 2>/dev/null && echo "==> Zona waktu: Asia/Jakarta (ubah dgn: sudo timedatectl set-timezone Asia/Makassar | Asia/Jayapura)"
sleep 1
systemctl is-active --quiet bell-sekolah && echo "✔ Berjalan" || { echo "✘ Gagal, cek: journalctl -u bell-sekolah -n 30"; exit 1; }
IP=$(hostname -I | awk '{print $1}')
echo; echo "Panel: http://$IP:$PORT"
echo "Langkah akhir: jalankan 'alsamixer', pastikan Master tidak mute & volume cukup."
