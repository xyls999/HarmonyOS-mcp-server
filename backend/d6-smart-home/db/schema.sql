-- 智慧家居数据库 Schema (SQLite)
-- /data/A9/smart_home/db/schema.sql

CREATE TABLE IF NOT EXISTS devices (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    status      TEXT DEFAULT 'online',
    room        TEXT NOT NULL,
    icon        TEXT DEFAULT '',
    primary_value INTEGER DEFAULT 0,
    is_on       INTEGER DEFAULT 0,
    mode        TEXT,
    battery     INTEGER,
    protocol    TEXT DEFAULT 'wifi',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sensors (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    sensor_group TEXT DEFAULT '环境监测',
    room        TEXT NOT NULL,
    icon        TEXT DEFAULT '',
    current_value REAL DEFAULT 0,
    unit        TEXT DEFAULT '',
    threshold_min REAL,
    threshold_max REAL,
    protocol    TEXT DEFAULT 'wifi',
    is_alert    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS device_operations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    params_json TEXT DEFAULT '{}',
    result      TEXT DEFAULT 'ok',
    source      TEXT DEFAULT 'api',
    scene_id    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id   TEXT NOT NULL,
    value       REAL NOT NULL,
    unit        TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scenes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    icon        TEXT DEFAULT '',
    color       TEXT DEFAULT '#007DFF',
    is_active   INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scene_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id    TEXT NOT NULL,
    device_id   TEXT NOT NULL,
    is_on       INTEGER DEFAULT 0,
    primary_value INTEGER,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    nickname    TEXT DEFAULT '用户',
    home_name   TEXT DEFAULT '我的家',
    member_count INTEGER DEFAULT 1,
    avatar      TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT DEFAULT 'u001',
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    scene_id    TEXT,
    tools_used  TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ops_device ON device_operations(device_id);
CREATE INDEX IF NOT EXISTS idx_ops_time ON device_operations(created_at);
CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_readings_time ON sensor_readings(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_time ON chat_history(created_at);
