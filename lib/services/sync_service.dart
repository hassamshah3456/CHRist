import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../models/collection.dart';
import 'api_client.dart';
import 'local_database.dart';

/// Pushes locally-queued collections to the server whenever connectivity is
/// available, and pulls server records into the local cache. Listens to
/// connectivity changes so a reconnect triggers an automatic sync.
class SyncService {
  final ApiClient api;
  final LocalDatabase db;

  SyncService(this.api, this.db);

  final _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _syncing = false;

  /// Called when a sync completes so listeners (providers) can refresh.
  void Function()? onSynced;

  void start() {
    _sub ??= _connectivity.onConnectivityChanged.listen((results) {
      final online = results.any((r) => r != ConnectivityResult.none);
      if (online) {
        // Fire and forget; errors are swallowed inside syncNow.
        syncNow();
      }
    });
  }

  void dispose() {
    _sub?.cancel();
    _sub = null;
  }

  Future<bool> isOnline() async {
    if (kIsWeb) {
      // Browsers don't expose raw connectivity; assume online and let HTTP fail.
      return true;
    }
    final results = await _connectivity.checkConnectivity();
    return results.any((r) => r != ConnectivityResult.none);
  }

  /// Pushes pending records then pulls the latest. Safe to call often.
  /// Returns true if a push/pull actually ran.
  Future<bool> syncNow() async {
    if (_syncing) return false;
    if (!await isOnline()) return false;
    _syncing = true;
    try {
      // 1. Push unsynced local records.
      final pending = await db.pendingUnsynced();
      if (pending.isNotEmpty) {
        // Upload any pending photos first so each answer carries a server
        // filename. Persist as we go, so a later failure never re-uploads.
        for (final c in pending) {
          var changed = false;
          if (c.medicalRecordPhotoLocalPath != null &&
              c.medicalRecordPhotoFilename == null) {
            c.medicalRecordPhotoFilename = await api.uploadPhoto(
              c.medicalRecordPhotoLocalPath!,
            );
            changed = true;
          }
          for (final a in c.answers) {
            if (a.photoLocalPath != null && a.photoFilename == null) {
              a.photoFilename = await api.uploadPhoto(a.photoLocalPath!);
              changed = true;
            }
          }
          if (changed) await db.update(c);
        }

        final res = await api.postJson('/collections/sync', {
          'collections': pending.map((c) => c.toApiJson()).toList(),
        });
        final ids = (res?['synced_ids'] as List?)?.cast<String>() ?? [];
        await db.markSynced(ids);
      }

      // 2. Pull the recent server set to keep the cache fresh across devices.
      final pulled = await api.get('/collections?period=all');
      if (pulled is List) {
        final items = pulled
            .map((e) => Collection.fromApiJson(e as Map<String, dynamic>))
            .toList();
        await db.upsertAllSynced(items);
      }

      onSynced?.call();
      return true;
    } catch (_) {
      // Offline / server error — keep records queued and try again later.
      return false;
    } finally {
      _syncing = false;
    }
  }
}
