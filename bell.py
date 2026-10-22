#!/usr/bin/env python3
"""Bell Sekolah - server. Hanya butuh Python 3 (stdlib). Memutar suara di server, web = panel kontrol.
Env: BELL_PORT (8099), BELL_DATA (./data), BELL_PLAYER (perintah pemutar kustom, mis. "mpg123 -q"),
     BELL_PASSWORD (opsional, login HTTP Basic user 'admin')."""
import base64, json, math, os, re, shutil, struct, subprocess, threading, time, uuid, wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("BELL_DATA", os.path.join(HERE, "data"))
SOUNDS = os.path.join(DATA, "sounds")
CFG = os.path.join(DATA, "config.json")
PORT = int(os.environ.get("BELL_PORT", "8099"))
PASSWORD = os.environ.get("BELL_PASSWORD", "")
MAX_UPLOAD = 50 * 1024 * 1024
EXT_OK = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
lock = threading.RLock()
LOGS = []
proc = None
fired = set()


def log(m):
    LOGS.insert(0, datetime.now().strftime("%d/%m %H:%M:%S ") + m)
    del LOGS[100:]
    print(m, flush=True)


def uid():
    return uuid.uuid4().hex[:7]


def make_default_bell(path):
    sr = 22050
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        fr = []
        for f in (880, 660, 880, 660):
            n = int(sr * .5)
            for i in range(n):
                fr.append(int(14000 * math.exp(-5 * i / n) * math.sin(2 * math.pi * f * i / sr)))
        w.writeframes(b"".join(struct.pack("<h", x) for x in fr))


def default_config():
    j1, j2, j3, ju, pr = uid(), uid(), uid(), uid(), uid()
    it = lambda t, l: {"id": uid(), "time": t, "sound": "default", "label": l}
    return {
        "schedules": [
            {"id": j1, "name": "Jadwal 1 (Senin)", "items": [it("07:00", "Masuk"), it("12:00", "Istirahat"), it("15:00", "Pulang")]},
            {"id": j2, "name": "Jadwal 2 (Selasa-Kamis)", "items": [it("07:00", "Masuk"), it("12:00", "Istirahat"), it("15:00", "Pulang")]},
            {"id": j3, "name": "Jadwal 3 (Jumat)", "items": [it("07:00", "Masuk"), it("11:00", "Istirahat"), it("13:00", "Pulang")]},
            {"id": ju, "name": "Jadwal Upacara", "items": [it("06:45", "Persiapan upacara"), it("07:00", "Upacara mulai"), it("08:00", "Upacara selesai")]},
        ],
        "presets": [{"id": pr, "name": "Harian", "map": {"0": None, "1": j1, "2": j2, "3": j2, "4": j2, "5": j3, "6": None}, "upacara": ju}],
        "active": pr, "upacaraDates": [], "sounds": [], "enabled": False,
    }


def load():
    os.makedirs(SOUNDS, exist_ok=True)
    d = os.path.join(SOUNDS, "default.wav")
    if not os.path.exists(d):
        make_default_bell(d)
    if os.path.exists(CFG):
        with open(CFG) as f:
            return json.load(f)
    c = default_config(); save(c); return c


def save(c=None):
    c = c if c is not None else C
    tmp = CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CFG)


C = load()


def sound_path(sid):
    if not sid or sid == "default":
        return os.path.join(SOUNDS, "default.wav")
    for s in C["sounds"]:
        if s["id"] == sid:
            p = os.path.join(SOUNDS, s["file"])
            if os.path.exists(p):
                return p
    return os.path.join(SOUNDS, "default.wav")


def player_cmd(path):
    custom = os.environ.get("BELL_PLAYER")
    if custom:
        return custom.split() + [path]
    ext = os.path.splitext(path)[1].lower()
    if shutil.which("mpv"): return ["mpv", "--no-video", "--really-quiet", path]
    if shutil.which("ffplay"): return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
    if ext == ".mp3" and shutil.which("mpg123"): return ["mpg123", "-q", path]
    if ext == ".wav" and shutil.which("aplay"): return ["aplay", "-q", path]
    if shutil.which("paplay"): return ["paplay", path]
    if shutil.which("play"): return ["play", "-q", path]
    if shutil.which("mpg123"): return ["mpg123", "-q", path]
    return None


def stop():
    global proc
    with lock:
        if proc and proc.poll() is None:
            proc.terminate()
        proc = None


def play(sid, why=""):
    global proc
    stop()
    p = sound_path(sid)
    cmd = player_cmd(p)
    if not cmd:
        log(f"[TIDAK ADA PEMUTAR] {why} - pasang mpg123/alsa-utils/ffmpeg")
        return False
    try:
        with lock:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"🔔 {why} -> {os.path.basename(p)} [{cmd[0]}]")
        return True
    except Exception as e:
        log(f"Gagal memutar: {e}")
        return False


def set_volume(v):
    v = max(0, min(100, int(v)))
    for cmd in (["amixer", "-q", "sset", "Master", f"{v}%"], ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"]):
        if shutil.which(cmd[0]):
            if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                return True
    return False


def find(lst, i):
    return next((x for x in lst if x["id"] == i), None)


def is_up(d):
    return d.strftime("%Y-%m-%d") in C["upacaraDates"]


def today_schedule(d):
    p = find(C["presets"], C["active"]) or (C["presets"][0] if C["presets"] else None)
    if not p:
        return None
    sid = (p.get("upacara") or p["map"].get(str(d.isoweekday() % 7))) if is_up(d) else p["map"].get(str(d.isoweekday() % 7))
    return find(C["schedules"], sid)


def scheduler():
    global fired
    while True:
        try:
            d = datetime.now()
            day = d.strftime("%Y-%m-%d")
            fired = {k for k in fired if k.startswith(day)}
            if C.get("enabled"):
                s = today_schedule(d)
                hm = d.strftime("%H:%M")
                if s:
                    for i in s["items"]:
                        k = f"{day}|{i['id']}|{i['time']}"
                        if i["time"] == hm and k not in fired:
                            fired.add(k)
                            threading.Thread(target=play, args=(i["sound"], f"{hm} {i['label']} ({s['name']})"), daemon=True).start()
        except Exception as e:
            log(f"scheduler error: {e}")
        time.sleep(1)


def state():
    d = datetime.now()
    s = today_schedule(d)
    return {"time": d.strftime("%H:%M:%S"), "date": d.strftime("%Y-%m-%d"), "dow": d.isoweekday() % 7,
            "tz": time.strftime("%Z"), "todayUpacara": is_up(d), "todaySchedule": s["id"] if s else None,
            "playing": bool(proc and proc.poll() is None), "player": (player_cmd("x.mp3") or [None])[0],
            "config": C, "logs": LOGS[:50]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def auth(self):
        if not PASSWORD: return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[1] == PASSWORD: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="Bell"'); self.end_headers()
        return False

    def out(self, obj, code=200, ctype="application/json", raw=None):
        b = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        if not self.auth(): return
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.out(None, ctype="text/html; charset=utf-8", raw=open(os.path.join(HERE, "index.html"), "rb").read())
        if u.path == "/api/state":
            with lock: return self.out(state())
        m = re.fullmatch(r"/api/sound/([\w-]+)", u.path)
        if m:
            p = sound_path(m.group(1))
            return self.out(None, ctype="application/octet-stream", raw=open(p, "rb").read())
        self.out({"error": "not found"}, 404)

    def do_PUT(self):
        if not self.auth(): return
        if self.path == "/api/config":
            try:
                n = json.loads(self.body())
                with lock:
                    for k in ("schedules", "presets", "active", "upacaraDates"):
                        C[k] = n[k]
                    for s in n.get("sounds", []):
                        e = find(C["sounds"], s["id"])
                        if e: e["name"] = str(s["name"])[:100]
                    save()
                return self.out({"ok": True})
            except Exception as e:
                return self.out({"error": str(e)}, 400)
        self.out({"error": "not found"}, 404)

    def do_POST(self):
        if not self.auth(): return
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/api/upload":
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_UPLOAD: return self.out({"error": "file terlalu besar (maks 50MB)"}, 413)
            name = q.get("name", ["suara"])[0]
            ext = os.path.splitext(name)[1].lower()
            if ext not in EXT_OK: return self.out({"error": "format tidak didukung"}, 400)
            sid = uid(); fn = sid + ext
            with open(os.path.join(SOUNDS, fn), "wb") as f:
                f.write(self.rfile.read(n))
            with lock:
                C["sounds"].append({"id": sid, "name": os.path.splitext(name)[0][:100], "file": fn}); save()
            return self.out({"ok": True, "id": sid})
        data = {}
        try: data = json.loads(self.body() or b"{}")
        except Exception: pass
        if u.path == "/api/play":
            return self.out({"ok": play(data.get("sound", "default"), "Tes manual")})
        if u.path == "/api/stop":
            stop(); log("Dihentikan manual"); return self.out({"ok": True})
        if u.path == "/api/enable":
            with lock:
                C["enabled"] = bool(data.get("enabled")); save()
            log("Bel otomatis " + ("AKTIF" if C["enabled"] else "MATI"))
            return self.out({"ok": True})
        if u.path == "/api/volume":
            return self.out({"ok": set_volume(data.get("volume", 80))})
        self.out({"error": "not found"}, 404)

    def do_DELETE(self):
        if not self.auth(): return
        m = re.fullmatch(r"/api/sound/([\w-]+)", urlparse(self.path).path)
        if m:
            sid = m.group(1)
            with lock:
                s = find(C["sounds"], sid)
                if s:
                    try: os.remove(os.path.join(SOUNDS, s["file"]))
                    except OSError: pass
                    C["sounds"].remove(s)
                    for sc in C["schedules"]:
                        for i in sc["items"]:
                            if i["sound"] == sid: i["sound"] = "default"
                    save()
            return self.out({"ok": True})
        self.out({"error": "not found"}, 404)


if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    log(f"Bell server di port {PORT}, data: {DATA}, waktu server: {datetime.now():%Y-%m-%d %H:%M} {time.strftime('%Z')}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
