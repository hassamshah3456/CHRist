import 'package:flutter/material.dart';

/// Web stub — native file paths are never used on web.
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
  Widget build(BuildContext context) => const SizedBox.shrink();
}
