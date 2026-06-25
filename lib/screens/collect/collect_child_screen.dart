import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../providers/collection_provider.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';

/// Step 2 of a collection: details about the child.
class CollectChildScreen extends StatefulWidget {
  final bool verbalConsent;
  final CapturedLocation location;

  const CollectChildScreen({
    super.key,
    required this.verbalConsent,
    required this.location,
  });

  @override
  State<CollectChildScreen> createState() => _CollectChildScreenState();
}

class _CollectChildScreenState extends State<CollectChildScreen> {
  final _form = GlobalKey<FormState>();
  final _age = TextEditingController();
  final _responderOther = TextEditingController();

  String? _sex; // male / female / other
  String? _responder; // father / mother / other
  bool _saving = false;

  @override
  void dispose() {
    _age.dispose();
    _responderOther.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    if (_sex == null) {
      showSnack(context, 'Please select the child\'s sex.', error: true);
      return;
    }
    if (_responder == null) {
      showSnack(context, 'Please select the responder.', error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() => _saving = true);

    final auth = context.read<AuthProvider>();
    final cp = context.read<CollectionProvider>();
    try {
      await cp.addCollection(
        collectorName: auth.user?.name ?? 'Collector',
        verbalConsent: widget.verbalConsent,
        childAge: int.tryParse(_age.text.trim()),
        childSex: _sex,
        responder: _responder,
        responderOther:
            _responder == 'other' ? _responderOther.text.trim() : null,
        lat: widget.location.lat,
        lng: widget.location.lng,
        address: widget.location.address,
      );
      if (!mounted) return;
      await _showSuccess();
    } catch (_) {
      if (mounted) {
        showSnack(context, 'Could not save. Please try again.', error: true);
        setState(() => _saving = false);
      }
    }
  }

  Future<void> _showSuccess() async {
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: const BoxDecoration(
                color: Color(0xFFE7F7EC),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.check_rounded,
                  color: AppTheme.success, size: 40),
            ),
            const SizedBox(height: 16),
            const Text('Collection saved',
                style:
                    TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            const Text(
              'It will sync automatically when online.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textMuted),
            ),
          ],
        ),
        actions: [
          Center(
            child: TextButton(
              onPressed: () {
                Navigator.of(context).pop(); // close dialog
                // Back to the first screen behind the collect flow.
                Navigator.of(context).popUntil((r) => r.isFirst);
              },
              child: const Text('Done'),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('About the Child')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Form(
            key: _form,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const _StepIndicator(step: 2),
                const SizedBox(height: 20),
                Expanded(
                  child: ListView(
                    children: [
                      const Text('Age',
                          style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: AppTheme.textDark)),
                      const SizedBox(height: 8),
                      TextFormField(
                        controller: _age,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          hintText: 'Age in years',
                          prefixIcon: Icon(Icons.cake_outlined),
                        ),
                        validator: (v) {
                          if (v == null || v.trim().isEmpty) {
                            return 'Enter the child\'s age';
                          }
                          final n = int.tryParse(v.trim());
                          if (n == null || n < 0 || n > 18) {
                            return 'Enter a valid age (0–18)';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 18),
                      LabeledDropdown<String>(
                        label: 'Sex',
                        value: _sex,
                        hint: 'Select sex',
                        items: const [
                          DropdownMenuItem(
                              value: 'male', child: Text('Male')),
                          DropdownMenuItem(
                              value: 'female', child: Text('Female')),
                          DropdownMenuItem(
                              value: 'other', child: Text('Other')),
                        ],
                        onChanged: (v) => setState(() => _sex = v),
                      ),
                      const SizedBox(height: 18),
                      LabeledDropdown<String>(
                        label: 'Responder',
                        value: _responder,
                        hint: 'Who is responding?',
                        items: const [
                          DropdownMenuItem(
                              value: 'father', child: Text('Father')),
                          DropdownMenuItem(
                              value: 'mother', child: Text('Mother')),
                          DropdownMenuItem(
                              value: 'other', child: Text('Others')),
                        ],
                        onChanged: (v) => setState(() => _responder = v),
                      ),
                      // Free-text field appears only for "Others".
                      if (_responder == 'other') ...[
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _responderOther,
                          decoration: const InputDecoration(
                            labelText: 'Specify responder',
                            prefixIcon: Icon(Icons.edit_outlined),
                          ),
                          validator: (v) => (_responder == 'other' &&
                                  (v == null || v.trim().isEmpty))
                              ? 'Please specify the responder'
                              : null,
                        ),
                      ],
                    ],
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2.4),
                        )
                      : const Icon(Icons.save_rounded),
                  label: Text(_saving ? 'Saving…' : 'Save collection'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StepIndicator extends StatelessWidget {
  final int step;
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
