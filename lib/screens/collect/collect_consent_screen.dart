import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import 'collect_child_screen.dart';
import 'step_indicator.dart';

/// Step 1 of a collection: contact phone + verbal consent.
///
/// The collector's name is shown automatically. Location/address is captured
/// silently in the background (not displayed) and carried through the flow.
class CollectConsentScreen extends StatefulWidget {
  const CollectConsentScreen({super.key});

  @override
  State<CollectConsentScreen> createState() => _CollectConsentScreenState();
}

class _CollectConsentScreenState extends State<CollectConsentScreen> {
  final _phone = TextEditingController();
  bool? _consent; // true = yes, false = no
  CapturedLocation _location = const CapturedLocation();
  bool _capturing = true;

  @override
  void initState() {
    super.initState();
    _capture();
  }

  Future<void> _capture() async {
    final loc = await context.read<LocationService>().capture();
    if (mounted) {
      setState(() {
        _location = loc;
        _capturing = false;
      });
    }
  }

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  void _next() {
    final phone = _phone.text.trim();
    if (phone.length < 7) {
      showSnack(context, 'Enter a valid phone number.', error: true);
      return;
    }
    if (_consent == null) {
      showSnack(context, 'Please select verbal consent.', error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectChildScreen(
          verbalConsent: _consent!,
          phone: phone,
          location: _location,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final name = auth.user?.name ?? 'Collector';

    return Scaffold(
      appBar: AppBar(title: const Text('New Collection')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const StepIndicator(step: 1),
              const SizedBox(height: 18),
              Expanded(
                child: ListView(
                  children: [
                    SectionCard(
                      child: Row(
                        children: [
                          const CircleAvatar(
                            radius: 22,
                            backgroundColor: Color(0xFFE9EDFB),
                            child: Icon(Icons.person_rounded,
                                color: AppTheme.primary),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('Collector',
                                    style: TextStyle(
                                        color: AppTheme.textMuted,
                                        fontSize: 13)),
                                Text(name,
                                    style: const TextStyle(
                                        fontSize: 17,
                                        fontWeight: FontWeight.w700)),
                              ],
                            ),
                          ),
                          _LocationStatus(
                              capturing: _capturing,
                              hasFix: _location.hasFix),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    const Text('Phone number',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    const Text(
                      'Children registered under the same number are grouped.',
                      style: TextStyle(color: AppTheme.textMuted, fontSize: 13),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        hintText: 'e.g. 98765 43210',
                        prefixIcon: Icon(Icons.phone_outlined),
                      ),
                    ),
                    const SizedBox(height: 24),
                    const Text('Verbal Consent',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    const Text('Did the responder give verbal consent?',
                        style: TextStyle(color: AppTheme.textMuted)),
                    const SizedBox(height: 12),
                    YesNoButtons(
                      value: _consent,
                      onChanged: (v) => setState(() => _consent = v),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              ElevatedButton.icon(
                onPressed: _next,
                icon: const Icon(Icons.arrow_forward_rounded),
                label: const Text('Next'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LocationStatus extends StatelessWidget {
  final bool capturing;
  final bool hasFix;
  const _LocationStatus({required this.capturing, required this.hasFix});

  @override
  Widget build(BuildContext context) {
    if (capturing) {
      return const SizedBox(
        width: 20,
        height: 20,
        child: CircularProgressIndicator(strokeWidth: 2.2),
      );
    }
    return Icon(
      hasFix ? Icons.location_on_rounded : Icons.location_off_rounded,
      color: hasFix ? AppTheme.success : AppTheme.danger,
    );
  }
}
