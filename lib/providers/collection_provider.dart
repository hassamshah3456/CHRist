import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../models/answer.dart';
import '../models/collection.dart';
import '../services/api_client.dart';
import '../services/local_database.dart';
import '../services/sync_service.dart';

/// Dashboard statistics, computed from whatever the local cache holds.
class Stats {
  final int total;
  final int today;
  final int week;
  final int month;
  final int consentYes;
  final int consentNo;
  const Stats({
    this.total = 0,
    this.today = 0,
    this.week = 0,
    this.month = 0,
    this.consentYes = 0,
    this.consentNo = 0,
  });
}

class CollectionProvider extends ChangeNotifier {
  final ApiClient api;
  final LocalDatabase db;
  final SyncService sync;
  final _uuid = const Uuid();

  CollectionProvider({
    required this.api,
    required this.db,
    required this.sync,
  }) {
    // Refresh views whenever a background sync finishes.
    sync.onSynced = () {
      refreshStats();
      loadCollections(_currentPeriod);
    };
  }

  String _currentPeriod = 'week';
  String get currentPeriod => _currentPeriod;

  List<Collection> collections = [];
  Stats stats = const Stats();
  bool loading = false;
  int pendingSync = 0;

  /// Creates a collection, stores it locally, and attempts an immediate sync.
  Future<void> addCollection({
    required String collectorName,
    required bool verbalConsent,
    String? phone,
    String? childName,
    int? childAge,
    int? childAgeMonths,
    String? childSex,
    String? responder,
    String? responderOther,
    bool? medicalRecord,
    String? vaccines,
    String? medicalRecordPhotoLocalPath,
    double? lat,
    double? lng,
    String? address,
    List<CollectionAnswer> answers = const [],
  }) async {
    final c = Collection(
      id: _uuid.v4(),
      collectorName: collectorName,
      verbalConsent: verbalConsent,
      phone: phone,
      childName: childName,
      childAge: childAge,
      childAgeMonths: childAgeMonths,
      childSex: childSex,
      responder: responder,
      responderOther: responderOther,
      medicalRecord: medicalRecord,
      vaccines: vaccines,
      medicalRecordPhotoLocalPath: medicalRecordPhotoLocalPath,
      locationLat: lat,
      locationLng: lng,
      locationAddress: address,
      collectedAt: DateTime.now(),
      synced: false,
      answers: answers,
    );

    if (kIsWeb) {
      // Web: save directly to the API (sqflite web is unreliable under /web/).
      await sync.pushCollection(c);
      await refreshStats();
      await loadCollections(_currentPeriod);
      return;
    }

    await db.insert(c);
    await refreshStats();
    // Try to push right away; if offline it stays queued.
    await sync.syncNow();
    await refreshStats();
    await loadCollections(_currentPeriod);
  }

  Future<void> loadCollections(String period) async {
    _currentPeriod = period;
    loading = true;
    notifyListeners();

    if (kIsWeb) {
      try {
        final pulled = await api.get('/collections?period=$period');
        if (pulled is List) {
          collections = pulled
              .map((e) => Collection.fromApiJson(e as Map<String, dynamic>))
              .toList();
        }
      } on ApiException {
        collections = [];
      }
      pendingSync = 0;
      loading = false;
      notifyListeners();
      return;
    }

    // Pull fresh data if we can; ignore failures (offline).
    await sync.syncNow();
    collections = await db.queryByPeriod(period);
    pendingSync = await db.unsyncedCount();

    loading = false;
    notifyListeners();
  }

  Future<void> refreshStats() async {
    if (kIsWeb) {
      try {
        final data = await api.get('/stats') as Map<String, dynamic>?;
        stats = Stats(
          total: (data?['total'] as num?)?.toInt() ?? 0,
          today: (data?['today'] as num?)?.toInt() ?? 0,
          week: (data?['this_week'] as num?)?.toInt() ?? 0,
          month: (data?['this_month'] as num?)?.toInt() ?? 0,
          consentYes: (data?['consent_yes'] as num?)?.toInt() ?? 0,
          consentNo: (data?['consent_no'] as num?)?.toInt() ?? 0,
        );
      } on ApiException {
        stats = const Stats();
      }
      pendingSync = 0;
      notifyListeners();
      return;
    }

    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final week = today.subtract(const Duration(days: 7));
    final month = today.subtract(const Duration(days: 30));

    final all = await db.queryByPeriod('all');
    int t = 0, w = 0, mo = 0, yes = 0;
    for (final c in all) {
      if (!c.collectedAt.isBefore(today)) t++;
      if (!c.collectedAt.isBefore(week)) w++;
      if (!c.collectedAt.isBefore(month)) mo++;
      if (c.verbalConsent) yes++;
    }
    stats = Stats(
      total: all.length,
      today: t,
      week: w,
      month: mo,
      consentYes: yes,
      consentNo: all.length - yes,
    );
    pendingSync = await db.unsyncedCount();
    notifyListeners();
  }
}
