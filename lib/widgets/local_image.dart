import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../services/photo_storage.dart';
import 'local_image_io.dart' if (dart.library.html) 'local_image_stub.dart';

/// Displays a locally stored photo (native file path or web base64 blob).
class LocalImage extends StatelessWidget {
  final String path;
  final double? height;
  final double? width;
  final BoxFit fit;

  const LocalImage({
    super.key,
    required this.path,
    this.height,
    this.width,
    this.fit = BoxFit.cover,
  });

  @override
  Widget build(BuildContext context) {
    if (path.startsWith(kWebPhotoPrefix)) {
      final bytes = base64Decode(path.substring(kWebPhotoPrefix.length));
      return Image.memory(
        Uint8List.fromList(bytes),
        height: height,
        width: width,
        fit: fit,
      );
    }
    if (kIsWeb) {
      // Blob URL from image_picker on web (same session, before persist).
      return Image.network(path, height: height, width: width, fit: fit);
    }
    return NativeLocalImage(
      path: path,
      height: height,
      width: width,
      fit: fit,
    );
  }
}
