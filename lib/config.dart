import 'package:flutter/foundation.dart';

/// App-wide configuration.
///
/// The API base URL can be overridden at build time without editing code:
///   flutter build apk --dart-define=API_BASE_URL=https://your-server.com
class AppConfig {
  /// Base URL of the FastAPI backend. No trailing slash.
  ///
  /// On web the app is served from the same origin as the API (e.g. /web on
  /// api.usmlewise.com), so relative paths are used. On mobile, override at
  /// build time or use the emulator default (10.0.2.2).
  static String get apiBaseUrl {
    if (kIsWeb) return '';
    return const String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://10.0.2.2:8000',
    );
  }

  static const String appName = 'CRIST Tool';
}
