import 'dart:io';

import 'package:image_picker/image_picker.dart';

Future<String> copyPickedPhotoTo(XFile file, String destPath) async {
  await File(file.path).copy(destPath);
  return destPath;
}
