import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

const kDatabaseKeyName = 'local_db_key';

const _dbFileName = 'usmlewise_christ.db';

/// Web fallback: the WASM build of SQLite has no SQLCipher, so the local
/// database cannot be encrypted at rest in the browser.
///
/// This is a documented limitation, not an oversight. The browser build exists
/// for demonstration and administrative convenience; collecting participant
/// data through it places unencrypted records in browser-managed storage
/// (IndexedDB), which is readable by anyone with access to that browser
/// profile. Field collection must use the mobile app, where
/// db_opener_io.dart opens the same schema through SQLCipher.
Future<Database> openAppDatabase({
  required int version,
  required OnDatabaseCreateFn onCreate,
  required OnDatabaseVersionChangeFn onUpgrade,
}) async {
  databaseFactory = databaseFactoryFfiWeb;
  return databaseFactory.openDatabase(
    _dbFileName,
    options: OpenDatabaseOptions(
      version: version,
      onCreate: onCreate,
      onUpgrade: onUpgrade,
    ),
  );
}
