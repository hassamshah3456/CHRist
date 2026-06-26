/// App-wide configuration.
///
/// The API base URL can be overridden at build time without editing code:
///   flutter build apk --dart-define=API_BASE_URL=https://your-server.com
class AppConfig {
  /// Base URL of the FastAPI backend. No trailing slash.
  ///
  /// Default points to localhost for emulator testing. On a real device this
  /// MUST be your deployed server (e.g. https://usmlewise-api.onrender.com).
  /// 10.0.2.2 is the Android emulator's alias for the host machine.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const String appName = 'CRIST';
}
