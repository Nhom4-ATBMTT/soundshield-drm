# -*- coding: utf-8 -*-
"""
Bộ kiểm thử bắt buộc cho SoundShield DRM (Đề tài 12).

Chạy:
    pip install -r requirements.txt
    pip install pytest
    pytest -v

Mỗi hàm test tương ứng đúng 1 kịch bản bắt buộc trong đề bài:
    1. test_valid_user_can_open_track        -> "Người dùng hợp lệ mở file nhạc"
    2. test_expired_license_is_denied        -> "License hết hạn"
    3. test_tampered_metadata_is_detected    -> "Sửa metadata bản quyền"
    4. test_tampered_ciphertext_is_detected  -> "Sửa ciphertext"

Ngoài ra có thêm vài test phụ trợ (thu hồi, hết lượt nghe, license giả mạo
chữ ký) để tăng độ phủ, không bắt buộc nhưng nên có cho báo cáo.
"""
import io
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ORIGINAL_AUDIO = b"FAKE_MP3_BYTES_ORIGINAL_CONTENT_FOR_TESTING_1234567890"


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """Mỗi test chạy trên 1 DB + thư mục uploads + bộ khóa RSA/AES riêng biệt,
    hoàn toàn cô lập với dữ liệu thật trong static/uploads/soundshield.db."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.chdir(tmp_path)

    # Trỏ DATABASE / UPLOAD_FOLDER / KEYS_DIR sang thư mục tạm cho từng test
    import importlib
    import database as db_module
    import crypto_drm as crypto_module

    db_module.DATABASE = str(tmp_path / "soundshield_test.db")
    crypto_module.KEYS_DIR = str(tmp_path / "keys")
    crypto_module.PRIVATE_KEY_PATH = os.path.join(crypto_module.KEYS_DIR, "drm_private.pem")
    crypto_module.PUBLIC_KEY_PATH = os.path.join(crypto_module.KEYS_DIR, "drm_public.pem")
    crypto_module.MASTER_KEY_PATH = os.path.join(crypto_module.KEYS_DIR, "master.key")

    os.makedirs(tmp_path / "static" / "uploads", exist_ok=True)

    import app as app_module
    importlib.reload(app_module)  # đảm bảo app dùng lại module database/crypto_drm đã patch
    app_module.UPLOAD_FOLDER = str(tmp_path / "static" / "uploads")
    os.makedirs(app_module.UPLOAD_FOLDER, exist_ok=True)

    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    yield client, app_module


def _upload_track(client):
    r = client.post(
        "/upload",
        data={
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "copyright_info": "© 2026 Test Label. All rights reserved.",
            "file": (io.BytesIO(ORIGINAL_AUDIO), "song.mp3"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200


def _db_path(app_module):
    import database
    return database.DATABASE


def _fetch_track(app_module):
    conn = sqlite3.connect(_db_path(app_module))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tracks WHERE title='Test Song'").fetchone()
    conn.close()
    return row


def _fetch_transfer(app_module, track_id):
    conn = sqlite3.connect(_db_path(app_module))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM transfers WHERE track_id=? ORDER BY id DESC LIMIT 1", (track_id,)
    ).fetchone()
    conn.close()
    return row


def _create_transfer(client, track_id, max_plays=3, days=7):
    client.post(
        "/transfers/send",
        data={"track_id": track_id, "name": "Nguoi Nhan", "email": "nguoinhan@example.com",
              "max_plays": str(max_plays), "days": str(days)},
        follow_redirects=True,
    )


# ─────────────────────────────────────────────────────────────────────────
# 1) Người dùng hợp lệ mở file nhạc
# ─────────────────────────────────────────────────────────────────────────

def test_valid_user_can_open_track(app_client):
    client, app_module = app_client
    _upload_track(client)
    track = _fetch_track(app_module)
    assert track["is_encrypted"] == 1

    _create_transfer(client, track["id"])
    transfer = _fetch_transfer(app_module, track["id"])
    license_token = transfer["token"]

    r_listen = client.get(f"/listen/{license_token}")
    assert r_listen.status_code == 200

    r_stream = client.get(f"/stream/{license_token}")
    assert r_stream.status_code == 200
    assert r_stream.data == ORIGINAL_AUDIO  # giải mã ra đúng nội dung gốc


# ─────────────────────────────────────────────────────────────────────────
# 2) License hết hạn
# ─────────────────────────────────────────────────────────────────────────

def test_expired_license_is_denied(app_client):
    client, app_module = app_client
    import crypto_drm

    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"])
    transfer = _fetch_transfer(app_module, track["id"])

    expired_license = crypto_drm.issue_license(
        transfer_id=transfer["id"], track_id=track["id"], recipient_email="x@example.com",
        expires_at_iso="2000-01-01", max_plays=None, trial=False,
    )
    r = client.get(f"/listen/{expired_license}")
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# 3) Sửa metadata bản quyền
# ─────────────────────────────────────────────────────────────────────────

def test_tampered_metadata_is_detected(app_client):
    client, app_module = app_client
    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"])
    transfer = _fetch_transfer(app_module, track["id"])
    license_token = transfer["token"]

    # Giả lập kẻ tấn công (hoặc admin) sửa thẳng metadata trong DB, không có khóa
    # riêng để ký lại -> chữ ký cũ không còn khớp với nội dung mới.
    conn = sqlite3.connect(_db_path(app_module))
    conn.execute(
        "UPDATE tracks SET copyright_metadata = REPLACE(copyright_metadata, 'Test Artist', 'HACKED') "
        "WHERE id=?", (track["id"],),
    )
    conn.commit()
    conn.close()

    r_listen = client.get(f"/listen/{license_token}")
    r_stream = client.get(f"/stream/{license_token}")
    assert r_listen.status_code == 403
    assert r_stream.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# 4) Sửa ciphertext
# ─────────────────────────────────────────────────────────────────────────

def test_tampered_ciphertext_is_detected(app_client):
    client, app_module = app_client
    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"])
    transfer = _fetch_transfer(app_module, track["id"])
    license_token = transfer["token"]

    enc_path = os.path.join(app_module.UPLOAD_FOLDER, track["filename"])
    with open(enc_path, "r+b") as f:
        f.seek(20)
        byte = f.read(1)
        f.seek(20)
        f.write(bytes([byte[0] ^ 0xFF]))  # lật 1 bit trong ciphertext

    r_stream = client.get(f"/stream/{license_token}")
    assert r_stream.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# Test phụ trợ (khuyến khích, không bắt buộc)
# ─────────────────────────────────────────────────────────────────────────

def test_revoked_license_is_denied(app_client):
    client, app_module = app_client
    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"])
    transfer = _fetch_transfer(app_module, track["id"])

    client.post(f"/transfers/revoke/{transfer['id']}", follow_redirects=True)
    r = client.get(f"/listen/{transfer['token']}")
    assert r.status_code == 403


def test_out_of_plays_is_denied(app_client):
    client, app_module = app_client
    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"], max_plays=1)
    transfer = _fetch_transfer(app_module, track["id"])

    r1 = client.get(f"/listen/{transfer['token']}")
    assert r1.status_code == 200
    r2 = client.get(f"/listen/{transfer['token']}")
    assert r2.status_code == 403  # đã dùng hết lượt nghe được cấp


def test_forged_license_signature_is_rejected(app_client):
    """Giả mạo license bằng cách tự đổi payload (vd max_plays) mà không có
    khóa riêng để ký lại -> chữ ký không khớp -> bị từ chối."""
    client, app_module = app_client
    import base64
    import crypto_drm

    _upload_track(client)
    track = _fetch_track(app_module)
    _create_transfer(client, track["id"], max_plays=1)
    transfer = _fetch_transfer(app_module, track["id"])

    payload_b64, sig_b64 = transfer["token"].split(".", 1)
    payload = json.loads(crypto_drm._b64d(payload_b64))
    payload["max_plays"] = None  # kẻ tấn công cố gỡ giới hạn lượt nghe
    forged_payload_b64 = crypto_drm._b64e(crypto_drm._canonical_json(payload))
    forged_token = f"{forged_payload_b64}.{sig_b64}"  # chữ ký cũ, payload mới

    r = client.get(f"/listen/{forged_token}")
    assert r.status_code == 403