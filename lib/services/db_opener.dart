import 'package:sqflite/sqflite.dart';

export 'db_opener_stub.dart' if (dart.library.io) 'db_opener_io.dart';

/// Shared signature for the platform-specific database opener.
///
/// Mobile opens the file through SQLCipher with a key from the platform
/// keystore; web falls back to the plain WASM build, which has no SQLCipher.
typedef DbOpener = Future<Database> Function({
  required int version,
  required OnDatabaseCreateFn onCreate,
  required OnDatabaseVersionChangeFn onUpgrade,
});
