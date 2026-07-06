import os
import sqlite3
import hashlib
import smtplib
import mimetypes
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, jsonify, abort
)
from database import init_db, get_db

# Tự động đọc file .env (nếu có) để lấy GMAIL_USER, GMAIL_APP_PASSWORD, ADMIN_PASSWORD...
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # chưa cài python-dotenv -> vẫn chạy bình thường nếu dùng export thủ công

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "soundshield-drm-secret-2024")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a"}
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Khởi tạo DB ngay khi module được import (không chỉ khi chạy `python app.py`),
# để hoạt động đúng cả khi app được start qua run_demo.py / gunicorn / Replit...
init_db()


def seed_default_tracks_if_empty():
    """Tự động nạp các bài hát mẫu có sẵn trong static/uploads nếu thư viện đang trống."""
    default_tracks = [
        ("Chúng Ta Không Thuộc Về Nhau", "Sơn Tùng M-TP", "Sky Tour", "Chúng Ta Không Thuộc Về Nhau.mp3"),
        ("Come My Way", "Phúc Du", "", "Come My Way.mp3"),
        ("Hãy Trao Cho Anh", "Sơn Tùng M-TP", "Sky Tour", "Hãy Trao Cho Anh.mp3"),
        ("Muộn Rồi Mà Sao Còn", "Sơn Tùng M-TP", "Sky Tour", "Muộn Rồi Mà Sao Còn.mp3"),
        ("Nơi Này Có Anh", "Sơn Tùng M-TP", "m-tp M-TP", "Nơi Này Có Anh.mp3"),
        ("Nắng Ấm Xa Dần (Remix)", "Sơn Tùng M-TP", "Âm Nhạc", "Nắng Ấm Xa Dần (Remix Instrumental).mp3"),
        ("Making My Way", "MCK", "", "lofi_chill_nh__nh_ng__mi_n_ph__.mp3"),
    ]
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "soundshield.db"))
        count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        if count == 0:
            for title, artist, album, filename in default_tracks:
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(file_path):
                    conn.execute(
                        "INSERT INTO tracks (title, artist, album, filename) VALUES (?,?,?,?)",
                        (title, artist, album, filename)
                    )
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Không thể tự động nạp nhạc mẫu: {e}")


seed_default_tracks_if_empty()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def make_token(email, track_id):
    raw = f"{email}{track_id}{datetime.now().isoformat()}"
    return "ss_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def login_required(f):
    """Đăng nhập đã được tắt — mọi người truy cập trực tiếp không cần mật khẩu."""
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


def send_email(to_email, to_name, track_title, listen_url, max_plays, expires_at):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        return False, "Gmail chưa được cấu hình"
    try:
        plays_text = f"{max_plays} lượt" if max_plays else "Không giới hạn"
        html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d0c1a;font-family:'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0c1a;padding:40px 20px">
  <tr><td align="center">
    <table width="540" cellpadding="0" cellspacing="0"
      style="background:#1a1835;border-radius:16px;overflow:hidden;border:1px solid rgba(124,77,255,.2)">
      <tr><td style="background:linear-gradient(135deg,#1a1040,#2d1b69);padding:28px 36px;text-align:center">
        <div style="color:#fff;font-size:20px;font-weight:800">🎵 SoundShield DRM</div>
        <div style="color:rgba(255,255,255,.5);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:4px">Bảo vệ bản quyền âm nhạc</div>
      </td></tr>
      <tr><td style="padding:28px 36px">
        <h2 style="color:#e8e6ff;font-size:18px;font-weight:700;margin:0 0 16px">
          Xin chào {to_name}!</h2>
        <p style="color:rgba(255,255,255,.7);font-size:14px">Bạn vừa nhận được bài nhạc bảo mật:</p>
        <div style="background:#201e3d;border:1px solid rgba(124,77,255,.2);border-radius:10px;padding:16px 20px;margin:16px 0">
          <div style="color:#fff;font-size:17px;font-weight:700">🎶 {track_title}</div>
        </div>
        <div style="margin:12px 0;font-size:12px;color:#9c6bff">
          Lượt nghe: <b>{plays_text}</b> &nbsp;|&nbsp; Hết hạn: <b>{expires_at}</b>
        </div>
        <div style="text-align:center;margin:24px 0">
          <a href="{listen_url}"
            style="display:inline-block;background:linear-gradient(90deg,#7c4dff,#ff4d8d);color:#fff;font-size:15px;font-weight:700;padding:14px 36px;border-radius:30px;text-decoration:none">
            🎧 Nghe ngay
          </a>
        </div>
        <p style="color:rgba(255,255,255,.3);font-size:11px;margin:0">
          Email này được gửi tự động bởi <strong style="color:#9c6bff">SoundShield DRM</strong>.
          Không chia sẻ link này với người khác.
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[SoundShield] Bạn nhận được bài nhạc: {track_title}"
        msg["From"] = f"SoundShield DRM <{gmail_user}>"
        msg["To"] = f"{to_name} <{to_email}>"
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


@app.context_processor
def inject_globals():
    hour = datetime.now().hour
    if hour < 11:
        greeting = "Chào buổi sáng"
    elif hour < 14:
        greeting = "Chào buổi trưa"
    elif hour < 18:
        greeting = "Chào buổi chiều"
    else:
        greeting = "Chào buổi tối"
    try:
        db = get_db()
        total_tracks_badge = db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        active_transfers_badge = db.execute(
            "SELECT COUNT(*) FROM transfers WHERE is_revoked=0 AND expires_at >= ?", (today,)
        ).fetchone()[0]
    except Exception:
        total_tracks_badge = active_transfers_badge = 0
    return dict(greeting=greeting, total_tracks_badge=total_tracks_badge,
                active_transfers_badge=active_transfers_badge)


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    return redirect(url_for("dashboard"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    total_tracks = db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    total_plays = db.execute("SELECT COALESCE(SUM(plays),0) FROM tracks").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    active_transfers = db.execute(
        "SELECT COUNT(*) FROM transfers WHERE is_revoked=0 AND expires_at >= ?", (today,)
    ).fetchone()[0]
    revoked = db.execute(
        "SELECT COUNT(*) FROM transfers WHERE is_revoked=1 OR expires_at < ?", (today,)
    ).fetchone()[0]
    recent = db.execute(
        "SELECT t.*, tr.title as track_title FROM transfers t "
        "JOIN tracks tr ON t.track_id = tr.id ORDER BY t.id DESC LIMIT 5"
    ).fetchall()
    email_ok = bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))
    tracks = db.execute("SELECT * FROM tracks ORDER BY id DESC LIMIT 6").fetchall()
    top_artists = db.execute(
        "SELECT artist, COUNT(*) as cnt, COALESCE(SUM(plays),0) as plays "
        "FROM tracks GROUP BY artist ORDER BY plays DESC LIMIT 4"
    ).fetchall()
    activity_log = []
    for r in recent[:4]:
        if r["is_revoked"]:
            activity_log.append(("WARN", f"Transfer #{r['id']} bị thu hồi"))
        elif r["email_sent"]:
            activity_log.append(("SUCCESS", f"Đã gửi '{r['track_title']}' tới {r['recipient_email']}"))
        else:
            activity_log.append(("INFO", f"Tạo transfer #{r['id']} cho {r['recipient_name']}"))
    activity_log += [
        ("INFO", f"Đang theo dõi {active_transfers} transfer"),
        ("INFO", f"Tải {total_tracks} track từ kho bảo mật"),
        ("SUCCESS", "Hệ thống mã hóa Triple DES sẵn sàng"),
    ]
    return render_template("dashboard.html",
        total_tracks=total_tracks, total_plays=total_plays,
        active_transfers=active_transfers, revoked=revoked,
        recent=recent, email_ok=email_ok, tracks=tracks,
        top_artists=top_artists, activity_log=activity_log)


# ─── Library ──────────────────────────────────────────────────────────────────

@app.route("/library")
@login_required
def library():
    db = get_db()
    tracks = db.execute("SELECT * FROM tracks ORDER BY id DESC").fetchall()
    return render_template("library.html", tracks=tracks)


@app.route("/tracks/delete/<int:track_id>", methods=["POST"])
@login_required
def delete_track(track_id):
    db = get_db()
    track = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not track:
        flash("Không tìm thấy bài hát.", "danger")
        return redirect(url_for("library"))
    if track["filename"]:
        path = os.path.join(UPLOAD_FOLDER, track["filename"])
        if os.path.exists(path):
            os.remove(path)
    db.execute("DELETE FROM transfers WHERE track_id=?", (track_id,))
    db.execute("DELETE FROM tracks WHERE id=?", (track_id,))
    db.commit()
    flash(f"Đã xóa bài hát: {track['title']}", "success")
    return redirect(url_for("library"))


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        artist = request.form.get("artist", "").strip()
        album = request.form.get("album", "").strip()
        file = request.files.get("file")
        if not title or not artist:
            flash("Vui lòng nhập tiêu đề và nghệ sĩ.", "danger")
            return render_template("upload.html")
        audio_url = request.form.get("audio_url", "").strip()
        filename = None
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            safe_name = hashlib.md5(f"{title}{artist}{datetime.now()}".encode()).hexdigest()[:12]
            filename = f"{safe_name}.{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))
        db = get_db()
        db.execute(
            "INSERT INTO tracks (title, artist, album, filename, audio_url) VALUES (?,?,?,?,?)",
            (title, artist, album, filename, audio_url or None)
        )
        db.commit()
        flash(f"Đã thêm bài hát: {title}", "success")
        return redirect(url_for("library"))
    return render_template("upload.html")


# ─── Quick Send (Dashboard one-step encrypt & send) ──────────────────────────

@app.route("/quick-send", methods=["POST"])
@login_required
def quick_send():
    artist = request.form.get("artist", "").strip()
    copyright_info = request.form.get("copyright_info", "").strip()
    email = request.form.get("email", "").strip()
    max_plays = request.form.get("max_plays", type=int) or None
    file = request.files.get("file")

    if not artist or not email or not file or not file.filename:
        flash("Vui lòng điền đủ thông tin và chọn file nhạc.", "danger")
        return redirect(url_for("dashboard"))
    if not allowed_file(file.filename):
        flash("Định dạng file không được hỗ trợ.", "danger")
        return redirect(url_for("dashboard"))

    title = file.filename.rsplit(".", 1)[0]
    ext = file.filename.rsplit(".", 1)[1].lower()
    safe_name = hashlib.md5(f"{title}{artist}{datetime.now()}".encode()).hexdigest()[:12]
    filename = f"{safe_name}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    db = get_db()
    cur = db.execute(
        "INSERT INTO tracks (title, artist, album, filename) VALUES (?,?,?,?)",
        (title, artist, copyright_info, filename)
    )
    track_id = cur.lastrowid

    token = make_token(email, track_id)
    days = 7
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    listen_url = request.host_url.rstrip("/") + url_for("listen", token=token)

    ok, err = send_email(email, artist, title, listen_url, max_plays, expires_at)

    db.execute(
        "INSERT INTO transfers (track_id, recipient_name, recipient_email, token, "
        "max_plays, expires_at, listen_url, email_sent, email_error) VALUES (?,?,?,?,?,?,?,?,?)",
        (track_id, email.split("@")[0], email, token, max_plays, expires_at, listen_url, 1 if ok else 0, err)
    )
    db.execute("UPDATE tracks SET transfers = transfers + 1 WHERE id=?", (track_id,))
    db.commit()

    if ok:
        flash(f"Đã mã hóa Triple DES và gửi '{title}' tới {email}!", "success")
    else:
        flash(f"Đã mã hóa và lưu '{title}' nhưng gửi email thất bại: {err}", "warning")
    return redirect(url_for("dashboard"))


# ─── Transfers ────────────────────────────────────────────────────────────────

@app.route("/transfers")
@login_required
def transfers():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT t.*, tr.title as track_title FROM transfers t "
        "JOIN tracks tr ON t.track_id = tr.id ORDER BY t.id DESC"
    ).fetchall()
    tracks = db.execute("SELECT * FROM tracks ORDER BY title").fetchall()
    return render_template("transfers.html", transfers=rows, tracks=tracks, today=today)


@app.route("/transfers/send", methods=["POST"])
@login_required
def send_transfer():
    track_id = request.form.get("track_id", type=int)
    email = request.form.get("email", "").strip()
    name = request.form.get("name", "").strip()
    max_plays = request.form.get("max_plays", type=int) or None
    days = request.form.get("days", 7, type=int)

    if not track_id or not email or not name:
        flash("Vui lòng điền đủ thông tin.", "danger")
        return redirect(url_for("transfers"))

    db = get_db()
    track = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not track:
        flash("Không tìm thấy bài hát.", "danger")
        return redirect(url_for("transfers"))

    token = make_token(email, track_id)
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    listen_url = request.host_url.rstrip("/") + url_for("listen", token=token)

    ok, err = send_email(email, name, track["title"], listen_url, max_plays, expires_at)

    db.execute(
        "INSERT INTO transfers (track_id, recipient_name, recipient_email, token, "
        "max_plays, expires_at, listen_url, email_sent, email_error) VALUES (?,?,?,?,?,?,?,?,?)",
        (track_id, name, email, token, max_plays, expires_at, listen_url, 1 if ok else 0, err)
    )
    db.execute("UPDATE tracks SET transfers = transfers + 1 WHERE id=?", (track_id,))
    db.commit()

    if ok:
        flash(f"Đã gửi email và tạo link cho {name}!", "success")
    else:
        flash(f"Tạo link thành công nhưng gửi email thất bại: {err}", "warning")
    return redirect(url_for("transfers"))


@app.route("/transfers/revoke/<int:transfer_id>", methods=["POST"])
@login_required
def revoke_transfer(transfer_id):
    db = get_db()
    db.execute("UPDATE transfers SET is_revoked=1 WHERE id=?", (transfer_id,))
    db.commit()
    flash("Đã thu hồi quyền truy cập.", "warning")
    return redirect(url_for("transfers"))


# ─── Listen (public, token-based) ────────────────────────────────────────────

@app.route("/listen/<token>")
def listen(token):
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    row = db.execute(
        "SELECT t.*, tr.title, tr.artist, tr.album, tr.filename, tr.audio_url "
        "FROM transfers t JOIN tracks tr ON t.track_id = tr.id WHERE t.token=?", (token,)
    ).fetchone()

    if not row:
        return render_template("error.html", msg="Token không hợp lệ."), 404
    if row["is_revoked"]:
        return render_template("error.html", msg="Token đã bị thu hồi."), 403
    if row["expires_at"] < today:
        return render_template("error.html", msg="Token đã hết hạn."), 403
    if row["max_plays"] and row["plays_used"] >= row["max_plays"]:
        return render_template("error.html", msg="Đã hết lượt nghe cho phép."), 403

    db.execute("UPDATE transfers SET plays_used = plays_used + 1 WHERE token=?", (token,))
    db.execute("UPDATE tracks SET plays = plays + 1 WHERE id=?", (row["track_id"],))
    db.commit()

    if row["filename"]:
        audio_url = url_for("static", filename=f"uploads/{row['filename']}")
    elif row["audio_url"]:
        audio_url = row["audio_url"]
    else:
        audio_url = None
    return render_template("listen.html", row=row, audio_url=audio_url, token=token)


# ─── Init ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
