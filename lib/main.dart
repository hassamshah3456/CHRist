import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config.dart';
import 'providers/auth_provider.dart';
import 'providers/collection_provider.dart';
import 'services/api_client.dart';
import 'services/local_database.dart';
import 'services/location_service.dart';
import 'services/presence_service.dart';
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
  final presence = PresenceService(api, location);
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
            presence: presence,
          )..bootstrap(),
        ),
        ChangeNotifierProvider(
          create: (_) => CollectionProvider(api: api, db: db, sync: sync),
        ),
        Provider<LocationService>.value(value: location),
        Provider<SyncService>.value(value: sync),
        Provider<QuestionnaireService>.value(value: questionnaire),
      ],
      child: UsmleWiseApp(presence: presence),
    ),
  );
}

class UsmleWiseApp extends StatefulWidget {
  final PresenceService presence;
  const UsmleWiseApp({super.key, required this.presence});

  @override
  State<UsmleWiseApp> createState() => _UsmleWiseAppState();
}

class _UsmleWiseAppState extends State<UsmleWiseApp>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      widget.presence.start();
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached ||
        state == AppLifecycleState.hidden) {
      widget.presence.stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.presence.stop();
    super.dispose();
  }

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
