import 'dart:async';

import 'package:uuid/uuid.dart';

import 'api_client.dart';
import 'local_database.dart';
import 'location_service.dart';

/// Sends foreground heartbeats so the admin dashboard can show live presence,
/// latest location, and time spent using the app.
///
/// Time tracking is client-driven so it stays accurate offline: real foreground
/// seconds are accrued locally (persisted to SQLite), and each heartbeat reports
/// the increment since the last acknowledged flush. The backlog flushes whenever
/// connectivity returns, so time worked offline is never lost.
class PresenceService {
  final ApiClient api;
  final LocationService location;

  static const Duration _interval = Duration(seconds: 30);

  /// A single interval may never contribute more than this, so time while the
  /// app is suspended (or after a device clock jump) is not counted as worked.
  static const int _maxIntervalSeconds = 90;

  Timer? _timer;
  String? _sessionId;
  bool _sending = false;
  bool _enabled = false;
  bool _loaded = false;

  DateTime? _lastTick;
  int _pendingSeconds = 0;

  PresenceService(this.api, this.location);

  void enable() {
    _enabled = true;
    start();
  }

  void disable() {
    _enabled = false;
    stop();
    _sessionId = null;
  }

  void start() {
    if (!_enabled) return;
    if (_timer != null) return;
    _sessionId ??= const Uuid().v4();
    _lastTick = DateTime.now();
    _tick();
    _timer = Timer.periodic(_interval, (_) => _tick());
  }

  void stop() {
    // Capture the partial interval before pausing so backgrounding doesn't lose
    // the seconds since the last tick.
    _accumulate();
    _timer?.cancel();
    _timer = null;
    _lastTick = null;
  }

  Future<void> _ensureLoaded() async {
    if (_loaded) return;
    _pendingSeconds = await LocalDatabase.instance.getPendingAppSeconds();
    _loaded = true;
  }

  /// Adds real elapsed foreground time since the last tick to the persisted
  /// backlog, capped per interval to ignore suspended time.
  void _accumulate() {
    final now = DateTime.now();
    final last = _lastTick;
    _lastTick = now;
    if (last == null) return;
    final secs = now.difference(last).inSeconds;
    if (secs <= 0) return;
    _pendingSeconds += secs > _maxIntervalSeconds ? _maxIntervalSeconds : secs;
    LocalDatabase.instance.setPendingAppSeconds(_pendingSeconds);
  }

  Future<void> _tick() async {
    await _ensureLoaded();
    _accumulate();
    await _send();
  }

  Future<void> _send() async {
    if (_sending || _sessionId == null) return;
    _sending = true;
    final sessionId = _sessionId!;
    final flushing = _pendingSeconds;
    try {
      // Report presence + the accrued foreground time. A slow GPS fix must not
      // make an active collector appear offline, so location is sent separately.
      await api.postJson('/auth/heartbeat', {
        'session_id': sessionId,
        'app_seconds_delta': flushing,
      });

      // Acknowledged by the server — drop what we flushed (more time may have
      // accrued during the request, so subtract rather than zero out).
      _pendingSeconds =
          (_pendingSeconds - flushing).clamp(0, 1 << 31).toInt();
      await LocalDatabase.instance.setPendingAppSeconds(_pendingSeconds);

      // Then capture and publish the latest position. This second heartbeat
      // updates the same session and is safe if location permission is denied.
      final loc = await location.capture(includeAddress: false);
      if (!loc.hasFix || _sessionId != sessionId) return;
      await api.postJson('/auth/heartbeat', {
        'session_id': sessionId,
        'app_seconds_delta': 0,
        'location': {
          'lat': loc.lat,
          'lng': loc.lng,
          'address': loc.address,
        },
      });
    } catch (_) {
      // Offline / server error — keep the backlog; it flushes on the next
      // successful heartbeat. Presence is best-effort and must never interrupt
      // field collection.
    } finally {
      _sending = false;
    }
  }
}
