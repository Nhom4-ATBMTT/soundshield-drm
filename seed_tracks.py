"""Seed nhạc vào SQLite database cho Flask demo."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), "soundshield.db")

tracks = [
    ("Chúng Ta Không Thuộc Về Nhau", "Sơn Tùng M-TP", "Sky Tour",    "Chúng Ta Không Thuộc Về Nhau.mp3"),
    ("Come My Way",                   "Phúc Du",        "",            "Come My Way.mp3"),
    ("Hãy Trao Cho Anh",              "Sơn Tùng M-TP", "Sky Tour",    "Hãy Trao Cho Anh.mp3"),
    ("Muộn Rồi Mà Sao Còn",          "Sơn Tùng M-TP", "Sky Tour",    "Muộn Rồi Mà Sao Còn.mp3"),
    ("Nơi Này Có Anh",                "Sơn Tùng M-TP", "m-tp M-TP",  "Nơi Này Có Anh.mp3"),
    ("Nắng Ấm Xa Dần (Remix)",        "Sơn Tùng M-TP", "Âm Nhạc",    "Nắng Ấm Xa Dần (Remix Instrumental).mp3"),
]

conn = sqlite3.connect(DB)

# Xóa tracks cũ nếu có
conn.execute("DELETE FROM tracks")
conn.execute("DELETE FROM sqlite_sequence WHERE name='tracks'")

for title, artist, album, filename in tracks:
    conn.execute(
        "INSERT INTO tracks (title, artist, album, filename) VALUES (?,?,?,?)",
        (title, artist, album, filename)
    )
    print(f"✅ Thêm: {title}")

conn.commit()
conn.close()
print("\nDone! Đã seed xong SQLite database.")
