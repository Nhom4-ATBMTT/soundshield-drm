import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(__file__), "soundshield.db")


def get_db():
    from flask import g
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            artist      TEXT    NOT NULL,
            album       TEXT    DEFAULT '',
            filename    TEXT,
            audio_url   TEXT,
            plays       INTEGER DEFAULT 0,
            transfers   INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS transfers (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id         INTEGER NOT NULL REFERENCES tracks(id),
            recipient_name   TEXT    NOT NULL,
            recipient_email  TEXT    NOT NULL,
            token            TEXT    NOT NULL UNIQUE,
            max_plays        INTEGER,
            plays_used       INTEGER DEFAULT 0,
            expires_at       TEXT    NOT NULL,
            listen_url       TEXT,
            is_revoked       INTEGER DEFAULT 0,
            email_sent       INTEGER DEFAULT 0,
            email_error      TEXT,
            created_at       TEXT    DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()
