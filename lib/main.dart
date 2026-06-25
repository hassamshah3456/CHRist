import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config.dart';
import 'providers/auth_provider.dart';
import 'providers/collection_provider.dart';
import 'services/api_client.dart';
import 'services/local_database.dart';
import 'services/location_service.dart';
import 'services/questionnaire_service.dart';
import 'services/session_store.dart';
import 'services/sync_service.dart';
import 'screens/splash_screen.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Single shared instances wired together by hand (no DI framework needed).
  final api = ApiClient();
  final db = LocalDatabase.instance;
  final location = LocationService();
  final sync = SyncService(api, db);
  final store = SessionStore();
  final questionnaire = QuestionnaireService(api);

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthProvider(
            api: api,
            store: store,
            location: location,
            sync: sync,
          )..bootstrap(),
        ),
        ChangeNotifierProvider(
          create: (_) => CollectionProvider(api: api, db: db, sync: sync),
        ),
        Provider<LocationService>.value(value: location),
        Provider<SyncService>.value(value: sync),
        Provider<QuestionnaireService>.value(value: questionnaire),
      ],
      child: const UsmleWiseApp(),
    ),
  );
}

class UsmleWiseApp extends StatelessWidget {
  const UsmleWiseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const SplashScreen(),
    );
  }
}
