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

  /// Returns the active questions. Tries the network first; on failure falls
  /// back to the last cached copy.
  Future<List<Question>> load() async {
    try {
      final res = await api.get('/questionnaire');
      if (res is List) {
        final questions = res
            .map((e) => Question.fromApiJson(e as Map<String, dynamic>))
            .toList();
        await _cache(questions);
        return questions;
      }
    } catch (_) {
      // fall through to cache
    }
    return _readCache();
  }

  Future<void> _cache(List<Question> questions) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        _cacheKey, jsonEncode(questions.map((q) => q.toJson()).toList()));
  }

  Future<List<Question>> _readCache() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_cacheKey);
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List)
          .map((e) => Question.fromApiJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }
}
