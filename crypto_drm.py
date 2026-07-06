"""
crypto_drm.py — Lõi mật mã cho SoundShield DRM
================================================


1. KÝ SỐ METADATA BẢN QUYỀN (RSA-PSS / SHA-256)
   - Mỗi track có một khối metadata bản quyền (tiêu đề, nghệ sĩ, album,
     thông tin bản quyền, hash file gốc...).
   - Khối metadata được ký bằng khóa riêng RSA của hệ thống (Content
     Authority). Chữ ký được lưu kèm trong DB.
   - Bất kỳ ai sửa metadata (kể cả admin sửa thẳng trong DB) mà không có
     khóa riêng sẽ khiến việc xác thực chữ ký thất bại -> phát hiện giả mạo.

2. MÃ HÓA FILE NHẠC CÓ XÁC THỰC (AES-256-GCM, AEAD)
   - Mỗi track được mã hóa bằng một khóa riêng (derive từ khóa gốc bằng
     HKDF theo track_id) -> không dùng chung 1 khóa cho mọi file.
   - AES-GCM là "authenticated encryption": mọi thay đổi 1 bit trên
     ciphertext (hoặc trên AAD) sẽ khiến giải mã thất bại (InvalidTag)
     thay vì âm thầm trả về dữ liệu rác.
   - AAD (Additional Authenticated Data) gắn chữ ký/hash metadata vào
     ciphertext -> tráo file giữa 2 bài hát khác nhau cũng bị phát hiện.

3. LICENSE TOKEN (giấy phép nghe) — RSA-PSS ký số + có hạn dùng
   - License là 1 JSON tự chứa: transfer_id, track_id, người nhận,
     issued_at, expires_at, max_plays, trial...
   - License được ký số bằng khóa riêng hệ thống. Server luôn xác minh:
       a) chữ ký license hợp lệ (không bị sửa payload)
       b) license chưa hết hạn (expires_at)
       c) license chưa bị thu hồi / còn lượt nghe (tra DB theo transfer_id)
   - Chỉ khi (a)+(b)+(c) đều hợp lệ, server mới tiến hành giải mã file
     nhạc để phát cho người nghe.
"""

import os
import json
import base64
import hashlib
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidSignature, InvalidTag

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_DIR = os.path.join(BASE_DIR, "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "drm_private.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "drm_public.pem")
MASTER_KEY_PATH = os.path.join(KEYS_DIR, "master.key")


# ─────────────────────────────────────────────────────────────────────────
# 0. Khởi tạo khóa (chạy 1 lần, tự sinh nếu chưa có — giống 1 "Content
#    Authority" nội bộ cấp chứng thực cho hệ thống demo)
# ─────────────────────────────────────────────────────────────────────────

def _ensure_keys():
    os.makedirs(KEYS_DIR, exist_ok=True)

    if not (os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH)):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(PUBLIC_KEY_PATH, "wb") as f:
            f.write(private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ))
        try:
            os.chmod(PRIVATE_KEY_PATH, 0o600)
        except OSError:
            pass

    if not os.path.exists(MASTER_KEY_PATH):
        with open(MASTER_KEY_PATH, "wb") as f:
            f.write(os.urandom(32))  # AES-256 master key gốc để derive khóa từng file
        try:
            os.chmod(MASTER_KEY_PATH, 0o600)
        except OSError:
            pass


def _load_private_key():
    _ensure_keys()
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _load_public_key():
    _ensure_keys()
    with open(PUBLIC_KEY_PATH, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def _load_master_key():
    _ensure_keys()
    with open(MASTER_KEY_PATH, "rb") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────
# Helper: base64url không padding (gọn cho URL / JSON)
# ─────────────────────────────────────────────────────────────────────────

def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    padding_needed = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding_needed)


def _canonical_json(obj: dict) -> bytes:
    """Chuẩn hóa JSON (sort_keys, không khoảng trắng thừa) để chữ ký ổn định."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────
# 1. KÝ SỐ METADATA BẢN QUYỀN
# ─────────────────────────────────────────────────────────────────────────

def sign_data(payload: dict) -> str:
    """Ký số (RSA-PSS/SHA-256) 1 dict bất kỳ, trả về chữ ký base64url."""
    private_key = _load_private_key()
    message = _canonical_json(payload)
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return _b64e(signature)


def verify_signature(payload: dict, signature_b64: str) -> bool:
    """Xác minh chữ ký số trên 1 dict. Trả về False nếu payload đã bị sửa
    hoặc chữ ký không khớp — KHÔNG raise exception để caller dễ xử lý."""
    if not signature_b64:
        return False
    try:
        public_key = _load_public_key()
        message = _canonical_json(payload)
        signature = _b64d(signature_b64)
        public_key.verify(
            signature,
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def build_copyright_metadata(title, artist, album, copyright_info, uploader, plaintext_sha256):
    """Tạo khối metadata bản quyền + ký số. Trả về (metadata_dict, signature_b64)."""
    metadata = {
        "title": title,
        "artist": artist,
        "album": album or "",
        "copyright_info": copyright_info or f"© {artist}. Bảo lưu mọi quyền.",
        "uploader": uploader or "system",
        "created_at": now_utc_iso(),
        "sha256": plaintext_sha256,  # hash SHA-256 của file nhạc GỐC (trước khi mã hóa)
    }
    signature = sign_data(metadata)
    return metadata, signature


# ─────────────────────────────────────────────────────────────────────────
# 2. MÃ HÓA FILE NHẠC — AES-256-GCM (Authenticated Encryption)
# ─────────────────────────────────────────────────────────────────────────

def _derive_track_key(track_key_id: str) -> bytes:
    """Derive khóa AES-256 riêng cho từng track từ master key bằng HKDF,
    để lộ 1 khóa file không ảnh hưởng tới các file khác."""
    master_key = _load_master_key()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"soundshield-track-{track_key_id}".encode(),
    )
    return hkdf.derive(master_key)


def encrypt_audio_bytes(plaintext: bytes, track_key_id: str, aad: bytes) -> bytes:
    """
    Mã hóa nội dung file nhạc.
    aad (Additional Authenticated Data) = hash của (metadata + chữ ký metadata),
    giúp ràng buộc ciphertext này chỉ hợp lệ với ĐÚNG bộ metadata đã ký kèm theo
    -> tráo ciphertext giữa 2 bài / sửa metadata đều làm auth-tag sai.
    Định dạng file .drm đầu ra: [12 byte nonce] + [ciphertext||tag (AESGCM gộp sẵn)]
    """
    key = _derive_track_key(track_key_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ciphertext


def decrypt_audio_bytes(blob: bytes, track_key_id: str, aad: bytes) -> bytes:
    """
    Giải mã + xác thực toàn vẹn (auth tag). Nếu ciphertext (hoặc aad) bị sửa
    dù chỉ 1 byte -> raise cryptography.exceptions.InvalidTag.
    """
    key = _derive_track_key(track_key_id)
    aesgcm = AESGCM(key)
    nonce, ciphertext = blob[:12], blob[12:]
    return aesgcm.decrypt(nonce, ciphertext, aad)  # raises InvalidTag nếu bị giả mạo


def metadata_aad(metadata: dict, signature_b64: str) -> bytes:
    """AAD gắn ciphertext với đúng bản metadata + chữ ký của nó."""
    h = hashlib.sha256()
    h.update(_canonical_json(metadata))
    h.update((signature_b64 or "").encode())
    return h.digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# 3. LICENSE TOKEN — giấy phép nghe (ký số + có hạn + có thể là "nghe thử")
# ─────────────────────────────────────────────────────────────────────────

class LicenseError(Exception):
    """Lỗi license nói chung (không phân biệt lý do) — dùng khi caller chỉ
    cần biết là license invalid, còn muốn phân loại chi tiết thì bắt các
    subclass bên dưới."""


class LicenseTampered(LicenseError):
    pass


class LicenseExpired(LicenseError):
    pass


class LicenseMalformed(LicenseError):
    pass


def issue_license(transfer_id: int, track_id: int, recipient_email: str,
                   expires_at_iso: str, max_plays, trial: bool = False) -> str:
    """
    Phát hành license token: JSON payload + chữ ký RSA-PSS, đóng gói thành
    1 chuỗi duy nhất  "<base64url(payload)>.<base64url(signature)>"
    để nhúng thẳng vào URL nghe nhạc (/listen/<license>).
    """
    payload = {
        "transfer_id": transfer_id,
        "track_id": track_id,
        "recipient": recipient_email,
        "issued_at": now_utc_iso(),
        "expires_at": expires_at_iso,   # "YYYY-MM-DD"
        "max_plays": max_plays,
        "trial": bool(trial),
        "nonce": _b64e(os.urandom(6)),  # tránh 2 license trùng hệt nhau
    }
    signature_b64 = sign_data(payload)
    payload_b64 = _b64e(_canonical_json(payload))
    return f"{payload_b64}.{signature_b64}"


def parse_and_verify_license(license_token: str) -> dict:
    """
    Giải mã + xác minh chữ ký của license token.
    - Không hợp lệ / sai định dạng -> LicenseMalformed
    - Payload bị sửa (chữ ký không khớp) -> LicenseTampered
    - Hết hạn -> LicenseExpired
    Trả về payload dict nếu hợp lệ.
    NOTE: hàm này CHỈ kiểm tra tính toàn vẹn + thời hạn của bản thân token.
    Việc kiểm tra thu hồi (revoke) / số lượt nghe còn lại vẫn cần tra DB
    riêng (vì đó là trạng thái động, license tĩnh không thể tự biết).
    """
    try:
        payload_b64, signature_b64 = license_token.split(".", 1)
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        raise LicenseMalformed("Định dạng license token không hợp lệ.")

    if not verify_signature(payload, signature_b64):
        raise LicenseTampered("Chữ ký license không hợp lệ — license đã bị sửa hoặc giả mạo.")

    expires_at = payload.get("expires_at")
    today = datetime.now().strftime("%Y-%m-%d")
    if not expires_at or expires_at < today:
        raise LicenseExpired("License đã hết hạn sử dụng.")

    return payload