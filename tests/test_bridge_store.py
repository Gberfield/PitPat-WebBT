"""Store contracts: lost transactions, ID conflicts and permissive file modes."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from bridge.store import WalkStore


def walk(sid='one', **fields):
    return dict(schemaVersion=2, trackingVersion=1, sessionId=sid, date=1000,
                status='completed', duration=60, opaque={'kept': [1, 'yes']}, **fields)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'private' / 'walks.sqlite3'
        self.store = WalkStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_update_and_current_pointer_are_atomic(self):
        row = walk()
        self.store.save(row, current=True)
        self.assertEqual(self.store.current(), row)
        self.assertEqual(self.store.page(50, None)['walks'], [row])
        row['status'] = 'completed'
        self.store.save(row, current=False)
        self.assertIsNone(self.store.current())
        self.assertEqual(self.store.page(50, None)['walks'][0]['opaque'], {'kept': [1, 'yes']})

    def test_identical_import_noop_and_conflicting_batch_rollback(self):
        self.assertEqual(self.store.merge([walk()]), {'imported': 1, 'unchanged': 0})
        self.assertEqual(self.store.merge([walk()]), {'imported': 0, 'unchanged': 1})
        self.assertEqual(len(self.store.page(50, None)['walks']), 1)
        conflict = walk(); conflict['duration'] = 90
        with self.assertRaises(ValueError): self.store.merge([walk('two'), conflict])
        self.assertEqual(self.store.page(50, None)['walks'], [walk()])

    def test_pagination_stable_for_equal_dates(self):
        self.store.merge([walk('a'), walk('b'), walk('c')])
        first = self.store.page(2, None)
        self.store.merge([dict(walk('new'), date=2000)])
        second = self.store.page(2, first['next_cursor'])
        self.assertEqual([r['sessionId'] for r in first['walks'] + second['walks']], ['c', 'b', 'a'])
        with self.assertRaises(ValueError): self.store.page(101, None)
        with self.assertRaises(ValueError): self.store.page(10, 'invalid')

    def test_unknown_database_schema_is_not_deleted(self):
        with sqlite3.connect(self.path) as db: db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError): WalkStore(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 99)

    def test_private_modes_even_with_open_umask_and_reject_symlinks(self):
        previous = os.umask(0)
        try:
            path = Path(self.temp.name) / 'second' / 'walks.sqlite3'
            other = WalkStore(path); other.save(walk(), True)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            for item in path.parent.iterdir(): self.assertEqual(item.stat().st_mode & 0o777, 0o600)
            link = Path(self.temp.name) / 'link'; link.symlink_to(path.parent, target_is_directory=True)
            with self.assertRaises(ValueError): WalkStore(link / 'walks.sqlite3')
            linkfile = path.parent / 'alias'; linkfile.symlink_to(path)
            with self.assertRaises(ValueError): WalkStore(linkfile)
        finally: os.umask(previous)

    def test_bad_payload_batch_cannot_modify_existing_rows(self):
        self.store.merge([walk()])
        for bad in [dict(walk('bad'), schemaVersion=999), dict(walk('bad'), duration=float('nan'))]:
            with self.assertRaises(ValueError): self.store.merge([walk('two'), bad])
            self.assertEqual(self.store.page(50, None)['walks'], [walk()])
