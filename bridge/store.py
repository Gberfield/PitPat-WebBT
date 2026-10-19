"""Private SQLite walk storage. Each operation uses one atomic transaction.

The recorder calls these blocking methods from its single I/O worker, never from
BLE callbacks. JSON payloads preserve fields this version does not understand.
"""
import base64
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading


def private_directory(path):
    path = Path(path).absolute()
    # Check every existing ancestor; never traverse a symlink supplied as state.
    for parent in reversed([path, *path.parents]):
        if parent.is_symlink(): raise ValueError('Private path contains a symlink')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
        raise ValueError('Private directory is not owned by this user')
    path.chmod(0o700)
    return path


class WalkStore:
    def __init__(self, path):
        self.path = private_directory(Path(path).parent) / Path(path).name
        self.lock = threading.Lock()
        for item in (self.path, Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')):
            if item.is_symlink(): raise ValueError('State files must not be symlinks')
            if item.exists():
                if item.stat().st_uid != os.getuid() or not item.is_file():
                    raise ValueError('Invalid state file owner/type')
                item.chmod(0o600)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self.lock, self._db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1): raise ValueError('Unsupported walk database schema')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS walks (id TEXT PRIMARY KEY, date REAL NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)')
            db.execute('PRAGMA user_version=1')

    def _db(self):
        # sqlite's context manager commits but does not close the connection.
        from contextlib import contextmanager
        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=5)
            try:
                with db: yield db
            finally: db.close()
        return connection()

    @staticmethod
    def payload(walk):
        if (not isinstance(walk, dict) or walk.get('schemaVersion') != 2
                or not isinstance(walk.get('sessionId'), str) or not 1 <= len(walk['sessionId']) <= 128
                or type(walk.get('date')) not in (int, float)):
            raise ValueError('Invalid schema-2 walk record')
        try: return json.dumps(walk, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (ValueError, TypeError): raise ValueError('Walk must contain finite JSON data') from None

    def save(self, walk, current):
        payload = self.payload(walk)
        with self.lock, self._db() as db:
            db.execute('INSERT INTO walks VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,payload=excluded.payload',
                       (walk['sessionId'], walk['date'], payload))
            if current:
                db.execute("INSERT OR REPLACE INTO state VALUES ('current', ?)", (walk['sessionId'],))
            else:
                db.execute("DELETE FROM state WHERE key='current' AND value=?", (walk['sessionId'],))

    def current(self):
        with self.lock, self._db() as db:
            row = db.execute("SELECT payload FROM walks JOIN state ON walks.id=state.value WHERE state.key='current'").fetchone()
            return json.loads(row[0]) if row else None

    def page(self, limit=50, before=None):
        if type(limit) is not int or not 1 <= limit <= 100: raise ValueError('Limit must be 1–100')
        params, where = [], ''
        if before is not None:
            try:
                date, sid = json.loads(base64.urlsafe_b64decode(before.encode() + b'=' * (-len(before) % 4)))
                if type(date) not in (int, float) or not isinstance(sid, str): raise ValueError()
            except Exception: raise ValueError('Invalid history cursor') from None
            where = 'WHERE date < ? OR (date = ? AND id < ?)'
            params = [date, date, sid]
        with self.lock, self._db() as db:
            rows = db.execute(f'SELECT date,id,payload FROM walks {where} ORDER BY date DESC,id DESC LIMIT ?',
                              (*params, limit + 1)).fetchall()
        cursor = None
        if len(rows) > limit:
            cursor = base64.urlsafe_b64encode(json.dumps(rows[limit - 1][:2]).encode()).decode().rstrip('=')
        return {'walks': [json.loads(r[2]) for r in rows[:limit]], 'next_cursor': cursor}

    def merge(self, records):
        if not isinstance(records, list): raise ValueError('Expected a list of walks')
        validated = [(r, self.payload(r)) for r in records]
        imported = unchanged = 0
        with self.lock, self._db() as db:
            for row, payload in validated:
                existing = db.execute('SELECT payload FROM walks WHERE id=?', (row['sessionId'],)).fetchone()
                if existing:
                    if existing[0] != payload: raise ValueError('Conflicting walk ID: ' + row['sessionId'])
                    unchanged += 1
                else:
                    db.execute('INSERT INTO walks VALUES (?, ?, ?)', (row['sessionId'], row['date'], payload))
                    imported += 1
        return {'imported': imported, 'unchanged': unchanged}
