import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/collection.dart';

/// On-device SQLite store. Holds the offline sync queue and a local cache of
/// collections so the app works fully without connectivity.
class LocalDatabase {
  static final LocalDatabase instance = LocalDatabase._();
  LocalDatabase._();

  Database? _db;

  Future<Database> get _database async {
    _db ??= await _open();
    return _db!;
  }

  Future<Database> _open() async {
    final dir = await getDatabasesPath();
    final path = p.join(dir, 'usmlewise_christ.db');
    return openDatabase(
      path,
      version: 6,
      onCreate: (db, _) async {
        await db.execute('''
          CREATE TABLE collections (
            id TEXT PRIMARY KEY,
            collector_name TEXT,
            verbal_consent INTEGER,
            phone TEXT,
            child_name TEXT,
            child_age INTEGER,
            child_age_months INTEGER,
            child_sex TEXT,
            responder TEXT,
            responder_other TEXT,
            medical_record INTEGER,
            vaccines TEXT,
            medical_record_photo_local TEXT,
            medical_record_photo TEXT,
            location_lat REAL,
            location_lng REAL,
            location_address TEXT,
            collected_at TEXT,
            synced INTEGER DEFAULT 0,
            answers_json TEXT
          )
        ''');
      },
      onUpgrade: (db, oldV, newV) async {
        if (oldV < 2) {
          await db.execute('ALTER TABLE collections ADD COLUMN answers_json TEXT');
        }
        if (oldV < 3) {
          await db.execute('ALTER TABLE collections ADD COLUMN phone TEXT');
        }
        if (oldV < 4) {
          await db.execute(
              'ALTER TABLE collections ADD COLUMN child_age_months INTEGER');
        }
        if (oldV < 5) {
          await db.execute('ALTER TABLE collections ADD COLUMN child_name TEXT');
        }
        if (oldV < 6) {
          await db.execute('ALTER TABLE collections ADD COLUMN medical_record INTEGER');
          await db.execute('ALTER TABLE collections ADD COLUMN vaccines TEXT');
          await db.execute('ALTER TABLE collections ADD COLUMN medical_record_photo_local TEXT');
          await db.execute('ALTER TABLE collections ADD COLUMN medical_record_photo TEXT');
        }
      },
    );
  }

  /// Replace an existing local record (e.g. after a photo upload sets the
  /// server filename on an answer).
  Future<void> update(Collection c) async {
    final db = await _database;
    await db.update('collections', c.toDbMap(),
        where: 'id = ?', whereArgs: [c.id]);
  }

  Future<void> insert(Collection c) async {
    final db = await _database;
    await db.insert(
      'collections',
      c.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Upsert records that came back from the server (already synced).
  Future<void> upsertAllSynced(List<Collection> items) async {
    final db = await _database;
    final batch = db.batch();
    for (final c in items) {
      batch.insert('collections', c.copyWith(synced: true).toDbMap(),
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  Future<List<Collection>> pendingUnsynced() async {
    final db = await _database;
    final rows = await db.query('collections', where: 'synced = 0');
    return rows.map(Collection.fromDbMap).toList();
  }

  Future<void> markSynced(List<String> ids) async {
    if (ids.isEmpty) return;
    final db = await _database;
    final placeholders = List.filled(ids.length, '?').join(',');
    await db.rawUpdate(
      'UPDATE collections SET synced = 1 WHERE id IN ($placeholders)',
      ids,
    );
  }

  Future<int> unsyncedCount() async {
    final db = await _database;
    final r = await db
        .rawQuery('SELECT COUNT(*) AS c FROM collections WHERE synced = 0');
    return (r.first['c'] as int?) ?? 0;
  }

  /// Local query mirroring the server's period filters, so the list screen
  /// shows data even while offline.
  Future<List<Collection>> queryByPeriod(String period) async {
    final db = await _database;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    String? where;
    List<Object?> args = [];

    switch (period) {
      case 'today':
        where = 'collected_at >= ?';
        args = [today.toIso8601String()];
        break;
      case 'yesterday':
        where = 'collected_at >= ? AND collected_at < ?';
        args = [
          today.subtract(const Duration(days: 1)).toIso8601String(),
          today.toIso8601String(),
        ];
        break;
      case 'week':
        where = 'collected_at >= ?';
        args = [today.subtract(const Duration(days: 7)).toIso8601String()];
        break;
      case 'month':
        where = 'collected_at >= ?';
        args = [today.subtract(const Duration(days: 30)).toIso8601String()];
        break;
      default: // all
        where = null;
    }

    final rows = await db.query(
      'collections',
      where: where,
      whereArgs: where == null ? null : args,
      orderBy: 'collected_at DESC',
    );
    return rows.map(Collection.fromDbMap).toList();
  }

  Future<void> clearAll() async {
    final db = await _database;
    await db.delete('collections');
  }
}
