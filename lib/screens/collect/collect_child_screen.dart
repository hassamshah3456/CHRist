import 'package:flutter/material.dart';

import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import 'collect_screening_screen.dart';
import 'step_indicator.dart';

/// Step 2 of a collection: details about the child. Continues to the dynamic
/// screening questions (step 3).
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

  String? _sex;
  String? _responder;

  @override
  void dispose() {
    _age.dispose();
    _responderOther.dispose();
    super.dispose();
  }

  void _next() {
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
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectScreeningScreen(
          verbalConsent: widget.verbalConsent,
          location: widget.location,
          childAge: int.tryParse(_age.text.trim()),
          childSex: _sex,
          responder: _responder,
          responderOther:
              _responder == 'other' ? _responderOther.text.trim() : null,
        ),
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
                const StepIndicator(step: 2),
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
                          DropdownMenuItem(value: 'male', child: Text('Male')),
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
                  onPressed: _next,
                  icon: const Icon(Icons.arrow_forward_rounded),
                  label: const Text('Next'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
