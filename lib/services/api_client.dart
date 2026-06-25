import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

/// Thrown for non-2xx API responses, carrying a user-friendly message.
class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => message;
}

/// Thin wrapper over `http` that injects the bearer token and decodes JSON.
class ApiClient {
  String? _token;

  void setToken(String? token) => _token = token;

  Map<String, String> get _jsonHeaders => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Uri _uri(String path) => Uri.parse('${AppConfig.apiBaseUrl}$path');

  Future<dynamic> get(String path) async {
    final res = await http
        .get(_uri(path), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> postJson(String path, Map<String, dynamic> body) async {
    final res = await http
        .post(_uri(path), headers: _jsonHeaders, body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  /// Posts form-encoded data (used by the OAuth2 login endpoint).
  Future<dynamic> postForm(String path, Map<String, String> form) async {
    final headers = {
      'Content-Type': 'application/x-www-form-urlencoded',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };
    final res = await http
        .post(_uri(path), headers: headers, body: form)
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  /// Uploads a photo file (multipart) and returns the server-side filename.
  Future<String> uploadPhoto(String filePath) async {
    final req = http.MultipartRequest('POST', _uri('/collections/photo'));
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    req.files.add(await http.MultipartFile.fromPath('file', filePath));
    final streamed = await req.send().timeout(const Duration(seconds: 60));
    final res = await http.Response.fromStream(streamed);
    final body = _decode(res);
    return (body as Map)['filename'] as String;
  }

  dynamic _decode(http.Response res) {
    final isJson = (res.headers['content-type'] ?? '').contains('json');
    final body = res.body.isNotEmpty && isJson ? jsonDecode(res.body) : null;
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return body;
    }
    final detail = (body is Map && body['detail'] != null)
        ? body['detail'].toString()
        : 'Request failed (${res.statusCode}).';
    throw ApiException(res.statusCode, detail);
  }
}
