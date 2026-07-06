# SoundShield DRM – Hệ thống Gửi Nhạc Bảo Mật

**Môn học:** Nhập môn An toàn Bảo mật Thông tin
**Đề tài 12:** DRM-like Secure Music Delivery – Gửi tập tin nhạc có bản quyền

---

## Giới thiệu

SoundShield DRM là hệ thống quản lý và phân phối âm nhạc có bản quyền theo mô hình DRM (Digital Rights Management). Admin upload nhạc, hệ thống **mã hóa file bằng cơ chế có xác thực (AES-256-GCM)**, gắn **metadata bản quyền được ký số (RSA-PSS/SHA-256)**, phát hành **license token đã ký số và có hạn dùng**, rồi gửi liên kết nghe nhạc cho người nhận qua email.

Mọi lượt mở link đều được hệ thống xác minh lại từ đầu: chữ ký license, hạn dùng, trạng thái thu hồi, số lượt nghe còn lại, và chữ ký của metadata bản quyền — **trước khi** cho phép giải mã. Toàn bộ hoạt động cấp quyền / sử dụng quyền / từ chối đều được ghi vào nhật ký (`/audit`).

---

## Kiến trúc bảo mật (đáp ứng yêu cầu đề bài)

| Yêu cầu | Cách triển khai |
|---|---|
| File nhạc được mã hóa | **AES-256-GCM** — khóa AES-256 riêng cho từng file, derive bằng HKDF-SHA256 từ 1 master key gốc (`keys/master.key`, tự sinh lần chạy đầu). |
| Mã hóa có cơ chế xác thực | AES-GCM là **AEAD** (Authenticated Encryption with Associated Data): mọi thay đổi trên ciphertext hoặc trên AAD khiến giải mã báo lỗi `InvalidTag`, thay vì âm thầm trả dữ liệu sai. |
| Metadata bản quyền được ký số | Khối `{title, artist, copyright_info, uploader, created_at, sha256}` được ký bằng **RSA-2048 PSS/SHA-256** (`keys/drm_private.pem` / `drm_public.pem`, tự sinh lần chạy đầu). |
| Phát hiện metadata bị sửa | Trước khi cho giải mã, hệ thống dùng khóa công khai xác minh lại chữ ký trên metadata hiện có trong DB. Metadata cũng được đưa vào **AAD** của AES-GCM, nên sửa metadata còn khiến việc giải mã ciphertext thất bại luôn. |
| License token / quyền nghe thử | License = `base64(payload_json).base64(chữ_ký_RSA)`, chứa `transfer_id, track_id, recipient, issued_at, expires_at, max_plays, trial`. Có thể tạo license "nghe thử" (giới hạn lượt) khi gửi transfer. |
| Từ chối nếu license hết hạn / không hợp lệ | `crypto_drm.parse_and_verify_license()` kiểm tra chữ ký + `expires_at` trước khi làm bất cứ điều gì khác; sai chữ ký / hết hạn / sai định dạng đều bị từ chối ngay. |
| Log cấp quyền & sử dụng quyền | Bảng `audit_log`: mọi `GRANT` (cấp license), `USE` (phát hợp lệ), `DENY` (hết hạn / thu hồi / hết lượt / metadata bị sửa / ciphertext bị sửa / license giả mạo) đều được ghi lại — xem tại menu **Nhật ký DRM**. |

### Luồng nghe nhạc (`/listen/<license_token>` → `/stream/<license_token>`)

```
Nhận license_token từ URL
        │
        ▼
1. Xác minh CHỮ KÝ + HẠN DÙNG của license (RSA-PSS)
   └─ sai chữ ký / hết hạn / sai định dạng → 403, log DENY
        ▼
2. Tra DB: license có bị thu hồi? còn lượt nghe không?
   └─ vi phạm → 403, log DENY
        ▼
3. Xác minh CHỮ KÝ trên metadata bản quyền của track
   └─ không khớp (đã bị sửa) → 403, log DENY (TAMPERED_METADATA)
        ▼
4. Hợp lệ → tăng plays_used, log USE, render trang nghe
        ▼
5. Thẻ <audio> gọi /stream/<license_token>
   └─ xác minh lại license + metadata, rồi GIẢI MÃ AES-256-GCM
   └─ auth-tag sai (ciphertext bị sửa) → 403, log DENY (TAMPERED_CIPHERTEXT)
   └─ thành công → trả byte nhạc gốc, KHÔNG lưu plaintext ra đĩa
```

> Lưu ý: file plaintext (nhạc gốc) **không bao giờ được ghi ra đĩa** — chỉ tồn tại trong RAM lúc mã hóa (upload) và lúc giải mã (stream).

---

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|------------|-----------|
| Backend    | Python 3, Flask 3 |
| Database   | SQLite (tích hợp sẵn, không cần cài đặt) |
| Frontend   | HTML5, CSS3, JavaScript thuần |
| Email      | smtplib + Gmail SMTP |
| Mã hóa nội dung | AES-256-GCM (`cryptography` — `AESGCM`), khóa dẫn xuất bằng HKDF-SHA256 |
| Ký số      | RSA-2048 PSS/SHA-256 (`cryptography` — `rsa`, `padding.PSS`) |
| License    | JSON tự chứa + chữ ký RSA, kiểm tra hạn dùng phía server |

---

## Cài đặt và chạy

### Yêu cầu
- Python 3.8 trở lên
- pip

### Các bước

```bash
# 1. Cài thư viện (bao gồm cryptography cho AES-GCM & RSA)
pip install -r requirements.txt

# 2. (Tuỳ chọn) Cấu hình biến môi trường
#    Windows:
set GMAIL_USER=youremail@gmail.com
set GMAIL_APP_PASSWORD=xxxxxxxxxxxx
set ADMIN_PASSWORD=matkhaucuaban

#    Linux/macOS:
export GMAIL_USER=youremail@gmail.com
export GMAIL_APP_PASSWORD=xxxxxxxxxxxx
export ADMIN_PASSWORD=matkhaucuaban

# 3. Chạy ứng dụng
python app.py
```

Lần chạy đầu tiên, hệ thống sẽ tự sinh:
- `keys/drm_private.pem` + `keys/drm_public.pem` (cặp khóa RSA-2048 ký số)
- `keys/master.key` (khóa gốc AES-256, dùng để dẫn xuất khóa từng file)

**Giữ bí mật thư mục `keys/`** — mất `drm_private.pem` thì không cấp license mới được; lộ `master.key` thì mọi file `.drm` đã phát hành có thể bị giải mã bởi kẻ tấn công.

### Hoặc chạy nhanh
- **Windows:** Mở file `run.bat`
- **Linux/macOS:** Chạy `bash run.sh`

### Mở trình duyệt
Truy cập: **http://localhost:5000**

---

## Kiểm thử bắt buộc

Bộ test tự động nằm ở `tests/test_drm.py`, chạy bằng:

```bash
pip install pytest
pytest -v
```

| Test | Mô tả | Kết quả mong đợi |
|---|---|---|
| `test_valid_user_can_open_track` | Người dùng hợp lệ mở file nhạc | `200 OK`, byte giải mã khớp 100% file gốc |
| `test_expired_license_is_denied` | License hết hạn | `403`, log `DENY / EXPIRED` |
| `test_tampered_metadata_is_detected` | Sửa metadata bản quyền trực tiếp trong DB | `403`, log `DENY / TAMPERED_METADATA` |
| `test_tampered_ciphertext_is_detected` | Lật 1 bit trong file `.drm` | `403`, log `DENY / TAMPERED_CIPHERTEXT` (AES-GCM auth-tag mismatch) |
| `test_revoked_license_is_denied` | Admin thu hồi license | `403` |
| `test_out_of_plays_is_denied` | Dùng hết số lượt nghe cho phép | `403` |
| `test_forged_license_signature_is_rejected` | Tự sửa payload license (vd gỡ giới hạn lượt) mà không ký lại | `403`, chữ ký không khớp |

Mỗi test chạy trên DB / khóa / thư mục upload **tạm thời riêng biệt** (fixture `app_client` trong `tests/test_drm.py`), không đụng tới dữ liệu thật.

---

## Cấu trúc thư mục

```
soundshield-python/
├── app.py               # Flask app, toàn bộ routes + luồng cấp/giải mã license
├── crypto_drm.py         # Lõi mật mã: RSA ký số, AES-256-GCM, license token
├── database.py           # Schema SQLite + audit_log + hàm log_event()
├── requirements.txt
├── run.bat / run.sh
├── tests/
│   └── test_drm.py       # 7 test: 4 bắt buộc + 3 khuyến khích
├── keys/                 # (tự sinh) RSA keypair + AES master key — KHÔNG commit
├── soundshield.db         # (tự tạo khi chạy lần đầu)
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   └── uploads/           # file .drm đã mã hóa (KHÔNG lưu plaintext)
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── library.html
    ├── upload.html
    ├── transfers.html
    ├── audit.html         # nhật ký cấp quyền & sử dụng quyền (MỚI)
    ├── listen.html
    └── error.html
```

---

## Cơ chế bảo mật — chi tiết

1. **Mã hóa file**: mỗi track có 1 khóa AES-256 riêng = `HKDF-SHA256(master_key, info="soundshield-track-<key_id>")`. Định dạng file `.drm` = `nonce(12B) || ciphertext||tag(AES-GCM)`.
2. **Ký số metadata**: `signature = RSA-PSS-Sign(private_key, canonical_json(metadata))`. Xác minh bằng khóa công khai — không cần chia sẻ khóa riêng cho việc kiểm tra.
3. **Ràng buộc metadata ↔ ciphertext**: `AAD = SHA-256(canonical_json(metadata) || signature)` được đưa vào AES-GCM khi mã hóa/giải mã — tráo ciphertext giữa 2 bài hoặc sửa metadata mà không mã hóa lại đều làm giải mã thất bại.
4. **License**: `token = base64url(json) + "." + base64url(RSA-PSS-Sign(json))`. Trạng thái động (thu hồi, số lượt đã dùng) vẫn tra theo `transfer_id` trong DB vì license tĩnh không tự biết được các thay đổi xảy ra sau khi phát hành.
5. **Audit log**: mọi request tới `/listen` và `/stream` đều ghi đúng 1 dòng log (GRANT lúc tạo license, USE lúc phát hợp lệ, DENY kèm lý do cụ thể khi bị từ chối).

---

## Tính năng chính

| Tính năng | Mô tả |
|-----------|-------|
| Upload nhạc | Mã hóa AES-256-GCM + ký số metadata ngay khi upload, không lưu plaintext |
| Thư viện nhạc | Xem danh sách, trạng thái mã hóa/ký số; không phát trực tiếp file mã hóa |
| Tạo transfer | Chọn nhạc, nhập email, cấu hình số lượt nghe / thời hạn / có phải bản nghe thử |
| Gửi email | Tự động gửi link license qua Gmail SMTP |
| Thu hồi license | Vô hiệu hóa ngay lập tức, ghi log |
| Trang nghe nhạc | Xác thực license + metadata realtime trước khi cho giải mã |
| Nhật ký DRM | Xem toàn bộ GRANT / USE / DENY tại `/audit` |
| Dashboard | Thống kê tổng quan hệ thống |