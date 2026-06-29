import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../screens/legal/legal_screen.dart';
import '../theme/app_theme.dart';

/// Tappable inline links to the in-app privacy policy and terms screens.
class LegalLinksRow extends StatelessWidget {
  final bool light;
  const LegalLinksRow({super.key, this.light = false});

  @override
  Widget build(BuildContext context) {
    final muted = light ? Colors.white70 : AppTheme.textMuted;
    final link = light ? Colors.white : AppTheme.primary;
    return Text.rich(
      TextSpan(
        style: TextStyle(fontSize: 12.5, color: muted),
        children: [
          const TextSpan(text: 'By continuing you agree to our '),
          TextSpan(
            text: 'Privacy Policy',
            style: TextStyle(color: link, fontWeight: FontWeight.w600),
            recognizer: TapGestureRecognizer()
              ..onTap = () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          const LegalScreen(document: LegalDocument.privacy),
                    ),
                  ),
          ),
          const TextSpan(text: ' and '),
          TextSpan(
            text: 'Terms of Use',
            style: TextStyle(color: link, fontWeight: FontWeight.w600),
            recognizer: TapGestureRecognizer()
              ..onTap = () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          const LegalScreen(document: LegalDocument.terms),
                    ),
                  ),
          ),
          const TextSpan(text: '.'),
        ],
      ),
      textAlign: TextAlign.center,
    );
  }
}
