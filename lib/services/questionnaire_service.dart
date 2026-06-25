import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/question.dart';
import 'api_client.dart';

/// Fetches the active questionnaire from the server and caches it locally so
/// the screening screen still works offline.
class QuestionnaireService {
  final ApiClient api;
  QuestionnaireService(this.api);

  static const _cacheKey = 'questionnaire_cache';
  static const _versionKey = 'questionnaire_version';

  List<Question> _memoryCache = [];
  Future<void>? _refreshing;
  bool _cacheReady = false;

  List<Question> get cached => List.unmodifiable(_memoryCache);
  bool get cacheReady => _cacheReady;

  /// Warms the in-memory cache and checks for updates without blocking the UI.
  Future<void> prepare() async {
    if (!_cacheReady) {
      _memoryCache = await _readCache();
    }
    unawaited(refreshIfChanged());
  }

  /// Returns cached questions immediately whenever possible. The tiny version
  /// check runs in the background and downloads the full questionnaire only
  /// when an admin change produced a different fingerprint.
  Future<List<Question>> load() async {
    if (_cacheReady) {
      unawaited(refreshIfChanged());
      return cached;
    }
    _memoryCache = await _readCache();
    if (_cacheReady) {
      unawaited(refreshIfChanged());
      return cached;
    }

    // First use after installation has no cache, so one full download is
    // unavoidable. Later visits render from memory without a network wait.
    await refreshIfChanged();
    if (!_cacheReady) await _downloadAndCache();
    return cached;
  }

  Future<void> refreshIfChanged() {
    return _refreshing ??= _checkForUpdate().whenComplete(() {
      _refreshing = null;
    });
  }

  Future<void> _checkForUpdate() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final localVersion = prefs.getString(_versionKey);
      final result = await api.get('/questionnaire/version');
      final serverVersion =
          result is Map ? result['version']?.toString() : null;
      if (serverVersion == null || serverVersion == localVersion) return;
      await _downloadAndCache(version: serverVersion);
    } catch (_) {
      // Keep the current cache when offline or if the update check fails.
    }
  }

  Future<void> _downloadAndCache({String? version}) async {
    final res = await api.get('/questionnaire');
    if (res is! List) return;
    final questions = res
        .map((e) => Question.fromApiJson(e as Map<String, dynamic>))
        .toList();
    _memoryCache = questions;
    _cacheReady = true;
    await _cache(questions, version: version);
  }

  Future<void> _cache(
    List<Question> questions, {
    String? version,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        _cacheKey, jsonEncode(questions.map((q) => q.toJson()).toList()));
    if (version != null) await prefs.setString(_versionKey, version);
  }

  Future<List<Question>> _readCache() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_cacheKey);
    if (raw == null) return [];
    try {
      final questions = (jsonDecode(raw) as List)
          .map((e) => Question.fromApiJson(e as Map<String, dynamic>))
          .toList();
      _cacheReady = true;
      return questions;
    } catch (_) {
      return [];
    }
  }
}
