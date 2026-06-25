import 'package:flutter/foundation.dart';

import '../models/user.dart';
import '../services/api_client.dart';
import '../services/local_database.dart';
import '../services/location_service.dart';
import '../services/presence_service.dart';
import '../services/session_store.dart';
import '../services/sync_service.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthProvider extends ChangeNotifier {
  final ApiClient api;
  final SessionStore store;
  final LocationService location;
  final SyncService sync;
  final PresenceService presence;

  AuthProvider({
    required this.api,
    required this.store,
    required this.location,
    required this.sync,
    required this.presence,
  });

  AuthStatus status = AuthStatus.unknown;
  AppUser? user;

  /// Restores a saved session on app start.
  Future<void> bootstrap() async {
    final token = await store.readToken();
    final savedUser = await store.readUser();
    if (token != null && savedUser != null) {
      api.setToken(token);
      user = savedUser;
      status = AuthStatus.authenticated;
      sync.start();
      sync.syncNow();
      presence.enable();
    } else {
      status = AuthStatus.unauthenticated;
    }
    notifyListeners();
  }

  Future<void> register({
    required String name,
    required String email,
    required String password,
    required String upiAddress,
    String? upiName,
  }) async {
    // Capture where the collector signed up (best-effort).
    final loc = await location.capture();

    final res = await api.postJson('/auth/register', {
      'name': name,
      'email': email,
      'password': password,
      'upi_address': upiAddress,
      'upi_name': (upiName != null && upiName.trim().isNotEmpty)
          ? upiName.trim()
          : null,
      'signup_location': {
        'lat': loc.lat,
        'lng': loc.lng,
        'address': loc.address,
      },
    });

    await _onAuthSuccess(res);
  }

  Future<void> login({
    required String email,
    required String password,
  }) async {
    // OAuth2 login endpoint expects form fields username/password.
    final res = await api.postForm('/auth/login', {
      'username': email,
      'password': password,
    });
    await _onAuthSuccess(res);
  }

  Future<void> _onAuthSuccess(dynamic res) async {
    final token = res['access_token'] as String;
    final u = AppUser.fromJson(res['user'] as Map<String, dynamic>);
    api.setToken(token);
    await store.save(token, u);
    user = u;
    status = AuthStatus.authenticated;
    sync.start();
    sync.syncNow();
    presence.enable();
    notifyListeners();
  }

  Future<void> logout() async {
    await store.clear();
    await LocalDatabase.instance.clearAll();
    api.setToken(null);
    user = null;
    status = AuthStatus.unauthenticated;
    sync.dispose();
    presence.disable();
    notifyListeners();
  }
}
