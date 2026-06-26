import 'dart:async';

import 'package:geocoding/geocoding.dart';
import 'package:geolocator/geolocator.dart';

/// A captured location plus a best-effort reverse-geocoded address.
class CapturedLocation {
  final double? lat;
  final double? lng;
  final String? address;
  const CapturedLocation({this.lat, this.lng, this.address});

  bool get hasFix => lat != null && lng != null;
}

/// Handles location permission prompts and captures fixes at app stages
/// (sign-up, each collection). Designed to never throw to the caller — if
/// location can't be obtained it returns an empty [CapturedLocation].
class LocationService {
  static const double _targetAccuracyMeters = 35;
  static const double _heartbeatTargetAccuracyMeters = 100;

  /// Ensures services + permission are on. Returns true if we can read a fix.
  Future<bool> ensurePermission() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      // Triggers the OS dialog to turn on location on most devices.
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return false;
    }
    return true;
  }

  /// Whether the device's location services toggle is currently on.
  Future<bool> isServiceEnabled() => Geolocator.isLocationServiceEnabled();

  /// Opens the OS location settings so the user can switch location on.
  Future<void> openLocationSettings() => Geolocator.openLocationSettings();

  Future<void> openAppSettings() => Geolocator.openAppSettings();

  Future<Position> _captureBestPosition({required bool precise}) async {
    final targetAccuracy =
        precise ? _targetAccuracyMeters : _heartbeatTargetAccuracyMeters;
    final first = await Geolocator.getCurrentPosition(
      desiredAccuracy: precise
          ? LocationAccuracy.bestForNavigation
          : LocationAccuracy.high,
      timeLimit: precise
          ? const Duration(seconds: 20)
          : const Duration(seconds: 8),
    );
    if (first.accuracy <= targetAccuracy || !precise) return first;

    Position best = first;
    StreamSubscription<Position>? sub;
    final completer = Completer<Position>();
    Timer? timeout;

    void finish() {
      if (!completer.isCompleted) completer.complete(best);
      timeout?.cancel();
      sub?.cancel();
    }

    timeout = Timer(const Duration(seconds: 12), finish);
    sub = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        distanceFilter: 0,
      ),
    ).listen((pos) {
      if (pos.accuracy < best.accuracy) best = pos;
      if (best.accuracy <= targetAccuracy) finish();
    }, onError: (_) => finish());

    return completer.future;
  }

  /// Captures the current position and reverse-geocodes it. Never throws.
  Future<CapturedLocation> capture({bool includeAddress = true}) async {
    try {
      final ok = await ensurePermission();
      if (!ok) return const CapturedLocation();

      final pos = await _captureBestPosition(precise: includeAddress);

      String? address;
      if (includeAddress) {
        try {
          final placemarks =
              await placemarkFromCoordinates(pos.latitude, pos.longitude);
          if (placemarks.isNotEmpty) {
            final p = placemarks.first;
            address = [
              p.name,
              p.subLocality,
              p.locality,
              p.administrativeArea,
              p.country,
            ].where((s) => s != null && s.trim().isNotEmpty).join(', ');
          }
        } catch (_) {
          // Reverse geocoding is best-effort; coordinates are enough.
        }
      }

      return CapturedLocation(
        lat: pos.latitude,
        lng: pos.longitude,
        address: address,
      );
    } catch (_) {
      return const CapturedLocation();
    }
  }
}
