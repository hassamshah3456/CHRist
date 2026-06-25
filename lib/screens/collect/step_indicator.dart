import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

/// Progress indicator for the 3-step collection flow.
class StepIndicator extends StatelessWidget {
  final int step; // 1..3
  const StepIndicator({super.key, required this.step});

  @override
  Widget build(BuildContext context) {
    Widget dot(int n, String label) {
      final active = n <= step;
      return Expanded(
        child: Column(
          children: [
            Container(
              height: 6,
              decoration: BoxDecoration(
                color: active ? AppTheme.primary : const Color(0xFFDADFEA),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(height: 6),
            Text(label,
                style: TextStyle(
                  fontSize: 11,
                  color: active ? AppTheme.primary : AppTheme.textMuted,
                  fontWeight: FontWeight.w600,
                )),
          ],
        ),
      );
    }

    return Row(
      children: [
        dot(1, 'Consent'),
        const SizedBox(width: 8),
        dot(2, 'About child'),
        const SizedBox(width: 8),
        dot(3, 'Screening'),
      ],
    );
  }
}
