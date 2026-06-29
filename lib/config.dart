import 'package:flutter/foundation.dart';

/// App-wide configuration.
///
/// The API base URL can be overridden at build time without editing code:
///   flutter build appbundle --dart-define=API_BASE_URL=https://your-server.com
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

  /// Public privacy policy URL (required by Google Play). Override at build:
  /// `--dart-define=PRIVACY_POLICY_URL=https://…`
  static String get privacyPolicyUrl {
    if (kIsWeb) return '/privacy';
    return const String.fromEnvironment(
      'PRIVACY_POLICY_URL',
      defaultValue: 'https://api.usmlewise.com/privacy',
    );
  }

  /// Public terms of use URL. Override at build:
  /// `--dart-define=TERMS_URL=https://…`
  static String get termsUrl {
    if (kIsWeb) return '/terms';
    return const String.fromEnvironment(
      'TERMS_URL',
      defaultValue: 'https://api.usmlewise.com/terms',
    );
  }

  /// Release mobile builds must use HTTPS (Google Play data-in-transit policy).
  static void assertProductionReady() {
    if (kIsWeb || !kReleaseMode) return;
    final url = apiBaseUrl;
    if (url.isEmpty || !url.startsWith('https://')) {
      throw StateError(
        'Release builds require HTTPS. Pass '
        '--dart-define=API_BASE_URL=https://your-server.com',
      );
    }
  }
}
