import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import 'photo_storage_io.dart' if (dart.library.html) 'photo_storage_stub.dart';

/// Prefix for photos stored as base64 in SQLite (web offline queue).
const kWebPhotoPrefix = 'base64:';

/// Persists a picked image for offline sync. Returns the stored reference
/// (native file path or base64-prefixed string on web).
Future<String> storePickedPhoto(XFile file, Uuid uuid) async {
  if (kIsWeb) {
    final bytes = await file.readAsBytes();
    return '$kWebPhotoPrefix${base64Encode(bytes)}';
  }
  final dir = await getApplicationDocumentsDirectory();
  final dest = p.join(
    dir.path,
    'photo_${uuid.v4()}${p.extension(file.path)}',
  );
  return copyPickedPhotoTo(file, dest);
}

/// Reads bytes from a stored photo reference (file path or base64 blob).
Future<Uint8List> readPhotoBytes(String stored) async {
  if (stored.startsWith(kWebPhotoPrefix)) {
    return base64Decode(stored.substring(kWebPhotoPrefix.length));
  }
  if (kIsWeb) {
    throw UnsupportedError('Web photos must use $kWebPhotoPrefix storage');
  }
  // Native: read from filesystem — handled by api_client via fromPath.
  throw UnsupportedError('Use uploadPhoto(path) for native file paths');
}

bool isStoredPhotoBytes(String? stored) =>
    stored != null && stored.startsWith(kWebPhotoPrefix);
