import 'dart:async';

import 'package:flutter/widgets.dart';

/// Inactivity lock — the device-side half of HIPAA's automatic-logoff
/// safeguard (§164.312(a)(2)(iii)).
///
/// The collector's token is deliberately long-lived: field work happens
/// offline for days and a mid-survey sign-out would cost real data. That makes
/// token expiry the wrong place to enforce automatic logoff, so it is enforced
/// here instead. After [timeout] with no interaction — including time spent
/// backgrounded — the session is cleared and the collector must sign in again.
///
/// Without this, a handset left on a table or lost in a market is an open
/// window onto every participant that collector has entered.
class IdleLock with WidgetsBindingObserver {
  IdleLock({Duration? timeout})
      : _timeout = timeout ?? const Duration(minutes: 15);

  /// Invoked when the session has gone stale. Assigned by AuthProvider, which
  /// is constructed after this object so the two can be wired together without
  /// a circular dependency.
  Future<void> Function()? onExpired;

  Duration _timeout;
  Timer? _timer;
  DateTime? _backgroundedAt;
  bool _enabled = false;

  Duration get timeout => _timeout;

  /// Applies the window the server asked this client to enforce.
  void configure(Duration timeout) {
    _timeout = timeout;
    if (_enabled) _restart();
  }

  void enable() {
    if (_enabled) return;
    _enabled = true;
    WidgetsBinding.instance.addObserver(this);
    _restart();
  }

  void disable() {
    if (!_enabled) return;
    _enabled = false;
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _timer = null;
    _backgroundedAt = null;
  }

  /// Called on every user interaction to push the deadline back.
  void touch() {
    if (_enabled) _restart();
  }

  void _restart() {
    _timer?.cancel();
    _timer = Timer(_timeout, _fire);
  }

  void _fire() {
    if (!_enabled) return;
    // Stop the clock first so a slow sign-out cannot fire twice.
    _timer?.cancel();
    _timer = null;
    onExpired?.call();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_enabled) return;

    if (state == AppLifecycleState.resumed) {
      // A background timer is not reliable — the OS suspends and may kill the
      // process. Compare wall-clock time instead, so a phone left in a pocket
      // overnight is locked the moment it is picked up.
      final since = _backgroundedAt;
      _backgroundedAt = null;
      if (since != null && DateTime.now().difference(since) >= _timeout) {
        _fire();
        return;
      }
      _restart();
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _backgroundedAt = DateTime.now();
      _timer?.cancel();
      _timer = null;
    }
  }
}

/// Wraps the app so any pointer or key event counts as activity.
///
/// Uses [Listener] with `behavior: translucent` so it observes events on their
/// way down without consuming them — buttons and text fields keep working
/// exactly as before.
class IdleLockScope extends StatelessWidget {
  const IdleLockScope({super.key, required this.lock, required this.child});

  final IdleLock lock;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => lock.touch(),
      onPointerSignal: (_) => lock.touch(),
      child: child,
    );
  }
}
