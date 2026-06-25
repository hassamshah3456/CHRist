import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import 'auth/welcome_screen.dart';
import 'dashboard_screen.dart';

/// Decides where to send the user once the saved session is restored.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    Widget body;
    switch (auth.status) {
      case AuthStatus.authenticated:
        return const DashboardScreen();
      case AuthStatus.unauthenticated:
        return const WelcomeScreen();
      case AuthStatus.unknown:
        body = const _Loading();
    }

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [AppTheme.primary, AppTheme.primaryDark],
          ),
        ),
        child: body,
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          BrandLogo(light: true),
          SizedBox(height: 28),
          SizedBox(
            width: 26,
            height: 26,
            child: CircularProgressIndicator(
              color: Colors.white,
              strokeWidth: 2.5,
            ),
          ),
        ],
      ),
    );
  }
}
