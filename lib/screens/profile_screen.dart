import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../i18n/app_localizations.dart';
import '../providers/auth_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import 'auth/welcome_screen.dart';
import 'language_picker_screen.dart';

/// Collector profile: identity, payment (UPI) details, language switch, and the
/// sign-out action (moved here from the dashboard header).
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthProvider>().user;
    final lang = context.watch<LocaleProvider>().code;

    return Scaffold(
      appBar: AppBar(title: Text(context.t('profile'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            _avatar(user?.name ?? 'Collector'),
            const SizedBox(height: 24),
            _sectionTitle(context, context.t('account')),
            const SizedBox(height: 10),
            SectionCard(
              child: Column(
                children: [
                  _InfoRow(
                    icon: Icons.person_outline_rounded,
                    label: context.t('full_name'),
                    value: user?.name,
                  ),
                  _InfoRow(
                    icon: Icons.phone_outlined,
                    label: context.t('phone'),
                    value: user?.phone,
                  ),
                  _InfoRow(
                    icon: Icons.email_outlined,
                    label: context.t('email'),
                    value: user?.email,
                    isLast: true,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            _sectionTitle(context, context.t('payment_details')),
            const SizedBox(height: 10),
            SectionCard(
              child: Column(
                children: [
                  _InfoRow(
                    icon: Icons.account_balance_wallet_outlined,
                    label: context.t('upi_id'),
                    value: (user?.upiAddress.isNotEmpty ?? false)
                        ? user!.upiAddress
                        : null,
                  ),
                  _InfoRow(
                    icon: Icons.badge_outlined,
                    label: context.t('upi_holder_name'),
                    value: user?.upiName,
                    isLast: true,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            OutlinedButton.icon(
              onPressed: () => showLanguageSheet(context),
              icon: const Icon(Icons.translate_rounded),
              label: Text('${context.t('change_language')} · '
                  '${LocaleProvider.names[lang] ?? lang}'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => _confirmLogout(context),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppTheme.danger,
                side: const BorderSide(color: AppTheme.danger),
              ),
              icon: const Icon(Icons.logout_rounded),
              label: Text(context.t('sign_out')),
            ),
          ],
        ),
      ),
    );
  }

  Widget _avatar(String name) {
    final initial = name.trim().isNotEmpty ? name.trim()[0].toUpperCase() : '?';
    return Center(
      child: Column(
        children: [
          CircleAvatar(
            radius: 40,
            backgroundColor: AppTheme.primary.withOpacity(.12),
            child: Text(
              initial,
              style: const TextStyle(
                fontSize: 34,
                fontWeight: FontWeight.w800,
                color: AppTheme.primary,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            name,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String text) => Text(
        text,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: AppTheme.textMuted,
          letterSpacing: 0.4,
        ),
      );

  Future<void> _confirmLogout(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(context.t('sign_out_q')),
        content: Text(context.t('sign_out_body')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text(context.t('cancel'))),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(context.t('sign_out'))),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await context.read<AuthProvider>().logout();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      (_) => false,
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? value;
  final bool isLast;
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final hasValue = value != null && value!.trim().isNotEmpty;
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
      child: Row(
        children: [
          Icon(icon, size: 22, color: AppTheme.textMuted),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.textMuted)),
                const SizedBox(height: 2),
                Text(
                  hasValue ? value! : context.t('not_set'),
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: hasValue ? AppTheme.textDark : AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
