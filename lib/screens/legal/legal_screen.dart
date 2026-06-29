import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config.dart';
import '../../theme/app_theme.dart';

enum LegalDocument { privacy, terms }

/// In-app privacy policy / terms viewer with link to the public web page
/// (required for Google Play store listing).
class LegalScreen extends StatelessWidget {
  final LegalDocument document;
  const LegalScreen({super.key, required this.document});

  String get _title =>
      document == LegalDocument.privacy ? 'Privacy Policy' : 'Terms of Use';

  String get _publicUrl => document == LegalDocument.privacy
      ? AppConfig.privacyPolicyUrl
      : AppConfig.termsUrl;

  String get _body => document == LegalDocument.privacy
      ? _privacyBody
      : _termsBody;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_title)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Text(
              _body,
              style: const TextStyle(
                fontSize: 14,
                height: 1.55,
                color: AppTheme.textDark,
              ),
            ),
            const SizedBox(height: 24),
            OutlinedButton.icon(
              onPressed: () => _openPublicUrl(context),
              icon: const Icon(Icons.open_in_new_rounded),
              label: const Text('Open full page in browser'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openPublicUrl(BuildContext context) async {
    final uri = Uri.parse(_publicUrl);
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open link')),
      );
    }
  }
}

const _privacyBody = '''
Last updated: June 2026

CRIST Tool is used by authorised research collectors. This policy describes how information is collected and used.

Collector account data
• Name, phone number, password (stored hashed), optional UPI payment details, and sign-up location.

While the app is open
• Foreground usage time and current location for admin field monitoring (not background location).

Field submissions
• Caregiver phone, child age and gender, screening answers, optional medical-record photos, vaccine information, collection GPS location, and timestamps.

How we use data
• Authenticate collectors, sync submissions, verify field activity, calculate payments, and conduct developmental screening research under verbal caregiver consent.

Permissions
• Location (while in use): geo-tag sign-up and each submission.
• Camera: optional medical-record or screening photos.
• Internet: sync with the research server.

Data sharing
• Data is sent to our research server. We do not sell personal data. Authorised administrators access submissions for study operations.

Deletion
• Collectors can delete their account from Profile. Contact your study coordinator about participant records.

Security
• Production apps use HTTPS. Passwords are hashed. Medical photos are admin-only.

Children
• The app is for adult collectors only. Collectors enter child data only after verbal caregiver consent per study protocol.

Contact: admin@usmlewise.com
''';

const _termsBody = '''
Last updated: June 2026

Acceptance
By registering you agree to these terms and the Privacy Policy.

Authorised use
This app is for authorised research collectors. Follow study protocols and obtain verbal caregiver consent before collecting participant data.

Your responsibilities
• Keep login credentials confidential.
• Enable location while using the app.
• Do not share participant health information outside approved channels.

Payments
Collector payments follow administrator-set rates. UPI details are used only for disbursement.

Account termination
You may delete your account from Profile. Administrators may suspend accounts that violate study rules.

Disclaimer
The app supports research data collection. It is not a medical device and does not provide clinical diagnosis or treatment.

Contact: admin@usmlewise.com
''';
