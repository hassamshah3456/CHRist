import 'dart:io';

import 'package:flutter/material.dart';

class NativeLocalImage extends StatelessWidget {
  final String path;
  final double? height;
  final double? width;
  final BoxFit fit;

  const NativeLocalImage({
    super.key,
    required this.path,
    this.height,
    this.width,
    this.fit = BoxFit.cover,
  });

  @override
  Widget build(BuildContext context) {
    return Image.file(
      File(path),
      height: height,
      width: width,
      fit: fit,
    );
  }
}
