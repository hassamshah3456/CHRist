import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart' show Database, OnDatabaseCreateFn, OnDatabaseVersionChangeFn;
import 'package:sqflite_sqlcipher/sqflite.dart' as cipher;

import 'secure_store.dart';

/// Database encryption key, stored in the Android Keystore / iOS Keychain.
const kDatabaseKeyName = 'local_db_key';

const _dbFileName = 'usmlewise_christ.db';

/// Opens the on-device queue as an encrypted SQLCipher database.
///
/// The queue holds real PHI while a collector is offline — child names,
/// caregiver phone numbers, GPS coordinates and screening answers — so a lost
/// or stolen handset must not yield a readable database file. SQLCipher
/// encrypts the whole file with AES-256; the key is 256 bits of platform CSPRNG
/// output generated on first launch and never leaves the keystore.
///
/// Losing the key (app reinstall, keystore reset) makes the local queue
/// unreadable. That is the intended trade-off: unsynced records are recoverable
/// only until they sync, and the server copy is authoritative.
Future<Database> openAppDatabase({
  required int version,
  required OnDatabaseCreateFn onCreate,
  required OnDatabaseVersionChangeFn onUpgrade,
}) async {
  final key = await SecureStore.readOrCreateKey(kDatabaseKeyName);
  final dir = await cipher.getDatabasesPath();
  final path = p.join(dir, _dbFileName);

  return cipher.openDatabase(
    path,
    password: key,
    version: version,
    onCreate: onCreate,
    onUpgrade: onUpgrade,
  );
}
