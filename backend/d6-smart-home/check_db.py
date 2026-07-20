import sqlite3, os
db = sqlite3.connect('/data/A9/control/data/smart_home.db')
print('=== TODAY 2026-07-16 ===')
tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall() if t[0] != 'sqlite_sequence']
for t in tables:
    try:
        c = db.execute('SELECT COUNT(*) FROM ' + t + " WHERE created_at LIKE '2026-07-16%'").fetchone()[0]
        if c > 0: print('  ' + t + ': ' + str(c))
    except: pass
print()
print('=== YESTERDAY 2026-07-15 ===')
for t in tables:
    try:
        c = db.execute('SELECT COUNT(*) FROM ' + t + " WHERE created_at LIKE '2026-07-15%'").fetchone()[0]
        if c > 0: print('  ' + t + ': ' + str(c))
    except: pass
print()
print('=== device_operations by date ===')
for r in db.execute('SELECT date(created_at), COUNT(*) FROM device_operations GROUP BY date(created_at) ORDER BY date(created_at) DESC LIMIT 5').fetchall():
    print('  ' + str(r[0]) + ': ' + str(r[1]))
print()
print('=== chat_history by date ===')
for r in db.execute('SELECT date(created_at), COUNT(*) FROM chat_history GROUP BY date(created_at) ORDER BY date(created_at) DESC LIMIT 5').fetchall():
    print('  ' + str(r[0]) + ': ' + str(r[1]))
print()
print('=== sensor_readings by date ===')
for r in db.execute('SELECT date(created_at), COUNT(*) FROM sensor_readings GROUP BY date(created_at) ORDER BY date(created_at) DESC LIMIT 5').fetchall():
    print('  ' + str(r[0]) + ': ' + str(r[1]))
print()
print('=== DB files ===')
for p in ['/data/A9/control/data/smart_home.db', '/data/A9/smart_home/smart_home.db']:
    if os.path.exists(p):
        print('  ' + p + ' size=' + str(os.path.getsize(p)))
db.close()
