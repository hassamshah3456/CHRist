import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../i18n/app_localizations.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import 'splash_screen.dart';

/// Shown on first launch so the collector picks their language. The choice is
/// persisted; this screen won't appear again unless storage is cleared.
class LanguagePickerScreen extends StatefulWidget {
  const LanguagePickerScreen({super.key});

  @override
  State<LanguagePickerScreen> createState() => _LanguagePickerScreenState();
}

class _LanguagePickerScreenState extends State<LanguagePickerScreen> {
  String _selected = 'en';

  @override
  Widget build(BuildContext context) {
    final locale = context.read<LocaleProvider>();
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 28),
              const Center(child: BrandLogo()),
              const SizedBox(height: 36),
              Text(
                context.t('select_language'),
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 20, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 20),
              ...LocaleProvider.supported.map((code) {
                final selected = _selected == code;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () => setState(() => _selected = code),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 18, vertical: 18),
                      decoration: BoxDecoration(
                        color: selected
                            ? AppTheme.primary.withOpacity(.10)
                            : Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: selected
                              ? AppTheme.primary
                              : const Color(0xFFDADFEA),
                          width: selected ? 1.6 : 1,
                        ),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              LocaleProvider.names[code] ?? code,
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w700,
                                color: selected
                                    ? AppTheme.primary
                                    : AppTheme.textDark,
                              ),
                            ),
                          ),
                          if (selected)
                            const Icon(Icons.check_circle_rounded,
                                color: AppTheme.primary),
                        ],
                      ),
                    ),
                  ),
                );
              }),
              const Spacer(),
              ElevatedButton(
                onPressed: () async {
                  await locale.setLanguage(_selected);
                  if (!context.mounted) return;
                  Navigator.of(context).pushReplacement(
                    MaterialPageRoute(builder: (_) => const SplashScreen()),
                  );
                },
                child: Text(context.t('continue')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
