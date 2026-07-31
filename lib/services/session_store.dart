import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/user.dart';
import 'secure_store.dart';

/// Persists the auth token and cached user across app launches.
///
/// The token now lives in the platform keystore rather than SharedPreferences.
/// A bearer token for this API can read every participant record the collector
/// has entered, so it belongs behind the Android Keystore / iOS Keychain, not
/// in a plain XML file that backup and device-transfer flows may copy
/// elsewhere.
///
/// The cached user profile (name, phone, UPI address) stays in
/// SharedPreferences: it is the collector's own contact detail, not
/// participant data, and it is re-fetched from /me on every launch.
class SessionStore {
  static const _kToken = 'auth_token';
  static const _kUser = 'auth_user';
  static const _kIdleLockMinutes = 'idle_lock_minutes';

  Future<void> save(String token, AppUser user, {int? idleLockMinutes}) async {
    await SecureStore.write(_kToken, token);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUser, jsonEncode(user.toJson()));
    if (idleLockMinutes != null) {
      await prefs.setInt(_kIdleLockMinutes, idleLockMinutes);
    }
  }

  /// Updates just the cached user (e.g. after refreshing the profile from the
  /// server), leaving the saved token untouched.
  Future<void> saveUser(AppUser user) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUser, jsonEncode(user.toJson()));
  }

  Future<String?> readToken() async {
    final token = await SecureStore.read(_kToken);
    if (token != null && token.isNotEmpty) return token;

    // One-time migration: builds before the keystore change stored the token
    // in SharedPreferences. Move it across and erase the old copy, so an
    // upgrading collector is not signed out and no plaintext copy lingers.
    final prefs = await SharedPreferences.getInstance();
    final legacy = prefs.getString(_kToken);
    if (legacy != null && legacy.isNotEmpty) {
      await SecureStore.write(_kToken, legacy);
      await prefs.remove(_kToken);
      return legacy;
    }
    return null;
  }

  Future<AppUser?> readUser() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kUser);
    if (raw == null) return null;
    try {
      return AppUser.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Inactivity window the server asked this client to enforce.
  Future<int> readIdleLockMinutes() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_kIdleLockMinutes) ?? 15;
  }

  Future<void> clear() async {
    await SecureStore.delete(_kToken);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken); // any legacy plaintext copy
    await prefs.remove(_kUser);
  }
}
