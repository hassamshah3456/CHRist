import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import 'collect_child_screen.dart';

/// Step 1 of a collection.
///
/// The collector's name is shown automatically. Their location/address is
/// captured automatically in the background (not displayed on screen, per
/// spec) and carried into step 2 to be saved with the record.
class CollectConsentScreen extends StatefulWidget {
  const CollectConsentScreen({super.key});

  @override
  State<CollectConsentScreen> createState() => _CollectConsentScreenState();
}

class _CollectConsentScreenState extends State<CollectConsentScreen> {
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

  void _next() {
    if (_consent == null) {
      showSnack(context, 'Please select verbal consent.', error: true);
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectChildScreen(
          verbalConsent: _consent!,
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
              const _StepIndicator(step: 1),
              const SizedBox(height: 18),
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
                                  color: AppTheme.textMuted, fontSize: 13)),
                          Text(name,
                              style: const TextStyle(
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700)),
                        ],
                      ),
                    ),
                    // Location capture status (address itself is not shown).
                    _LocationStatus(
                        capturing: _capturing, hasFix: _location.hasFix),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Verbal Consent',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              const Text(
                'Did the responder give verbal consent?',
                style: TextStyle(color: AppTheme.textMuted),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<bool>(
                value: _consent,
                isExpanded: true,
                hint: const Text('Select Yes or No'),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.verified_user_outlined),
                ),
                items: const [
                  DropdownMenuItem(value: true, child: Text('Yes')),
                  DropdownMenuItem(value: false, child: Text('No')),
                ],
                onChanged: (v) => setState(() => _consent = v),
              ),
              const Spacer(),
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

class _StepIndicator extends StatelessWidget {
  final int step; // 1 or 2
  const _StepIndicator({required this.step});

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
                  fontSize: 12,
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
        const SizedBox(width: 10),
        dot(2, 'About child'),
      ],
    );
  }
}
