import 'dart:async';

import 'package:uuid/uuid.dart';

import 'api_client.dart';
import 'location_service.dart';

/// Sends foreground heartbeats so the admin dashboard can show live presence,
/// latest location, and approximate time spent using the app.
class PresenceService {
  final ApiClient api;
  final LocationService location;

  Timer? _timer;
  String? _sessionId;
  bool _sending = false;
  bool _enabled = false;
  CapturedLocation? _lastLocation;
  DateTime? _locationCapturedAt;

  PresenceService(this.api, this.location);

  void enable() {
    _enabled = true;
    start();
  }

  void disable() {
    _enabled = false;
    stop();
  }

  void start() {
    if (!_enabled) return;
    if (_timer != null) return;
    _sessionId = const Uuid().v4();
    _send();
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => _send());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _sessionId = null;
    _lastLocation = null;
    _locationCapturedAt = null;
  }

  Future<void> _send() async {
    if (_sending || _sessionId == null) return;
    _sending = true;
    try {
      final now = DateTime.now();
      if (_lastLocation == null ||
          _locationCapturedAt == null ||
          now.difference(_locationCapturedAt!) >= const Duration(minutes: 5)) {
        _lastLocation = await location.capture();
        _locationCapturedAt = now;
      }
      final loc = _lastLocation!;
      await api.postJson('/auth/heartbeat', {
        'session_id': _sessionId,
        'location': {
          'lat': loc.lat,
          'lng': loc.lng,
          'address': loc.address,
        },
      });
    } catch (_) {
      // Presence is best-effort and must never interrupt field collection.
    } finally {
      _sending = false;
    }
  }
}
