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
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _send());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _sessionId = null;
  }

  Future<void> _send() async {
    if (_sending || _sessionId == null) return;
    _sending = true;
    final sessionId = _sessionId!;
    try {
      // Report presence immediately. A slow GPS fix must not make an active
      // collector appear offline in the admin dashboard.
      await api.postJson('/auth/heartbeat', {
        'session_id': sessionId,
      });

      // Then capture and publish the latest position. This second heartbeat
      // updates the same session and is safe if location permission is denied.
      final loc = await location.capture(includeAddress: false);
      if (!loc.hasFix || _sessionId != sessionId) return;
      await api.postJson('/auth/heartbeat', {
        'session_id': sessionId,
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
