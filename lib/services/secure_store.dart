import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Keystore-backed storage for the two secrets this app holds: the auth token
/// and the local database encryption key.
///
/// Previously the token lived in SharedPreferences, which is a plain XML file
/// in the app sandbox — readable on a rooted or unlocked device, and included
/// in some backup and device-transfer flows. `flutter_secure_storage` puts it
/// behind the Android Keystore / iOS Keychain instead.
///
/// Web has no equivalent hardware-backed store, so there the values fall back
/// to browser storage. That is a real limitation: the browser build should not
/// be used to collect participant data on a shared machine.
class SecureStore {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(
      // Never restored to a different device, and unavailable until the phone
      // has been unlocked once since boot.
      accessibility: KeychainAccessibility.first_unlock_this_device,
    ),
  );

  static Future<void> write(String key, String value) async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(key, value);
      return;
    }
    await _storage.write(key: key, value: value);
  }

  static Future<String?> read(String key) async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(key);
    }
    return _storage.read(key: key);
  }

  static Future<void> delete(String key) async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(key);
      return;
    }
    await _storage.delete(key: key);
  }

  /// A 256-bit random value, base64-encoded. Uses [Random.secure] so the key
  /// comes from the platform CSPRNG rather than a seeded generator.
  static String generateKey() {
    final rng = Random.secure();
    final bytes = List<int>.generate(32, (_) => rng.nextInt(256));
    return base64UrlEncode(bytes);
  }

  /// Returns the value at [key], creating and persisting a fresh random one
  /// the first time it is requested.
  static Future<String> readOrCreateKey(String key) async {
    final existing = await read(key);
    if (existing != null && existing.isNotEmpty) return existing;
    final created = generateKey();
    await write(key, created);
    return created;
  }
}
