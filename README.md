# SoundShield DRM – Hệ thống Gửi Nhạc Bảo Mật

**Môn học:** Nhập môn An toàn Bảo mật Thông tin  
**Đề tài 12:** DRM-like Secure Music Delivery – Gửi tập tin nhạc có bản quyền

---

## Giới thiệu

SoundShield DRM là hệ thống quản lý và phân phối âm nhạc có bản quyền theo mô hình DRM (Digital Rights Management). Hệ thống cho phép admin upload nhạc, tạo liên kết nghe nhạc bảo mật và gửi đến người nhận qua email, với các cơ chế kiểm soát:

- **Token bảo mật** (SHA-256) – Mỗi link là duy nhất, không thể đoán
- **Giới hạn thời gian** – Link tự hết hạn sau số ngày cấu hình
- **Giới hạn lượt nghe** – Kiểm soát số lần phát nhạc
- **Thu hồi tức thì** – Admin có thể vô hiệu hóa link bất kỳ lúc nào

---

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|------------|-----------|
| Backend    | Python 3, Flask 3 |
| Database   | SQLite (tích hợp sẵn, không cần cài đặt) |
| Frontend   | HTML5, CSS3, JavaScript thuần |
| Email      | smtplib + Gmail SMTP |
| Bảo mật    | SHA-256 token, Session-based auth |

---

## Cài đặt và chạy

### Yêu cầu
- Python 3.8 trở lên
- pip

### Các bước

```bash
# 1. Cài thư viện
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

### Hoặc chạy nhanh
- **Windows:** Mở file `run.bat`
- **Linux/macOS:** Chạy `bash run.sh`

### Mở trình duyệt
Truy cập: **http://localhost:5000**  
Mật khẩu mặc định: **admin123**

---

## Cấu trúc thư mục

```
soundshield-python/
├── app.py              # Ứng dụng Flask chính, toàn bộ routes
├── database.py         # Khởi tạo và kết nối SQLite
├── requirements.txt    # Thư viện Python cần cài
├── run.bat             # Script chạy nhanh (Windows)
├── run.sh              # Script chạy nhanh (Linux/macOS)
├── soundshield.db      # Database SQLite (tự tạo khi chạy lần đầu)
├── static/
│   ├── css/style.css   # Giao diện tối (dark theme)
│   ├── js/main.js      # JavaScript: file drop, copy, alerts
│   └── uploads/        # Thư mục lưu file nhạc upload
└── templates/
    ├── base.html        # Layout chung (sidebar + main)
    ├── login.html       # Trang đăng nhập admin
    ├── dashboard.html   # Trang tổng quan thống kê
    ├── library.html     # Thư viện bài hát
    ├── upload.html      # Form upload nhạc
    ├── transfers.html   # Quản lý gửi nhạc
    ├── listen.html      # Trang nghe nhạc (public, token)
    └── error.html       # Trang báo lỗi token
```

---

## Luồng hoạt động DRM

```
Admin upload nhạc
        ↓
Admin tạo Transfer (chọn nhạc + email người nhận + giới hạn)
        ↓
Hệ thống sinh Token SHA-256 + lưu DB + gửi email
        ↓
Người nhận nhận email → click link bảo mật
        ↓
Hệ thống kiểm tra: Token hợp lệ? Chưa hết hạn? Còn lượt nghe?
        ↓
Cho phép nghe ──── hoặc ──── Từ chối truy cập
        ↓
Ghi nhận lượt nghe vào DB
```

---

## Cơ chế bảo mật

1. **Token generation:** `SHA-256(email + track_id + timestamp)[:16]`
2. **Session auth:** Flask session cookie với secret key
3. **Access control:**  
   - `is_revoked = 1` → từ chối  
   - `expires_at < today` → từ chối  
   - `plays_used >= max_plays` → từ chối
4. **File security:** Filename được hash MD5, không lộ tên gốc

---

## Tính năng chính

| Tính năng | Mô tả |
|-----------|-------|
| Đăng nhập admin | Bảo vệ bằng mật khẩu + Flask session |
| Upload nhạc | Hỗ trợ MP3, WAV, OGG, FLAC, M4A |
| Thư viện nhạc | Xem, phát thử, xóa bài hát |
| Tạo transfer | Chọn nhạc, nhập email, cấu hình giới hạn |
| Gửi email | Tự động gửi link nghe nhạc qua Gmail SMTP |
| Thu hồi token | Vô hiệu hóa link ngay lập tức |
| Trang nghe nhạc | Giao diện công khai, kiểm tra token realtime |
| Dashboard | Thống kê tổng quan hệ thống |
