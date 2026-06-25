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
  final String phone;
  final CapturedLocation location;

  const CollectChildScreen({
    super.key,
    required this.verbalConsent,
    required this.phone,
    required this.location,
  });

  @override
  State<CollectChildScreen> createState() => _CollectChildScreenState();
}

class _CollectChildScreenState extends State<CollectChildScreen> {
  final _name = TextEditingController();
  final _age = TextEditingController();
  final _ageMonths = TextEditingController();
  final _responderOther = TextEditingController();

  String? _sex; // Male / Female / Other
  String? _responder; // Father / Mother / Others

  @override
  void dispose() {
    _name.dispose();
    _age.dispose();
    _ageMonths.dispose();
    _responderOther.dispose();
    super.dispose();
  }

  void _next() {
    final name = _name.text.trim();
    if (name.isEmpty) {
      showSnack(context, 'Enter the child\'s name.', error: true);
      return;
    }
    final ageText = _age.text.trim();
    final age = int.tryParse(ageText);
    if (ageText.isEmpty || age == null || age < 0 || age > 18) {
      showSnack(context, 'Enter a valid age (0–18 years).', error: true);
      return;
    }
    final monthsText = _ageMonths.text.trim();
    int? months;
    if (monthsText.isNotEmpty) {
      months = int.tryParse(monthsText);
      if (months == null || months < 0 || months > 11) {
        showSnack(context, 'Enter valid months (0–11).', error: true);
        return;
      }
    }
    if (_sex == null) {
      showSnack(context, 'Please select the child\'s sex.', error: true);
      return;
    }
    if (_responder == null) {
      showSnack(context, 'Please select the responder.', error: true);
      return;
    }
    if (_responder == 'Others' && _responderOther.text.trim().isEmpty) {
      showSnack(context, 'Please specify the responder.', error: true);
      return;
    }
    FocusScope.of(context).unfocus();

    final responderCode = _responder == 'Others' ? 'other' : _responder!.toLowerCase();
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectScreeningScreen(
          verbalConsent: widget.verbalConsent,
          phone: widget.phone,
          location: widget.location,
          childName: name,
          childAge: age,
          childAgeMonths: months,
          childSex: _sex!.toLowerCase(),
          responder: responderCode,
          responderOther:
              _responder == 'Others' ? _responderOther.text.trim() : null,
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
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const StepIndicator(step: 2),
              const SizedBox(height: 20),
              Expanded(
                child: ListView(
                  children: [
                    const _Label('Name'),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _name,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        hintText: 'Child\'s name',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const _Label('Age'),
                    const SizedBox(height: 8),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _age,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              hintText: 'Years',
                              prefixIcon: Icon(Icons.cake_outlined),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: _ageMonths,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              hintText: 'Months (0–11)',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    const _Label('Sex'),
                    const SizedBox(height: 8),
                    OptionChips(
                      options: const ['Male', 'Female', 'Other'],
                      value: _sex,
                      onChanged: (v) => setState(() => _sex = v),
                    ),
                    const SizedBox(height: 20),
                    const _Label('Responder'),
                    const SizedBox(height: 8),
                    OptionChips(
                      options: const ['Father', 'Mother', 'Others'],
                      value: _responder,
                      onChanged: (v) => setState(() => _responder = v),
                    ),
                    if (_responder == 'Others') ...[
                      const SizedBox(height: 14),
                      TextField(
                        controller: _responderOther,
                        decoration: const InputDecoration(
                          labelText: 'Specify responder',
                          prefixIcon: Icon(Icons.edit_outlined),
                        ),
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
    );
  }
}

class _Label extends StatelessWidget {
  final String text;
  const _Label(this.text);
  @override
  Widget build(BuildContext context) => Text(text,
      style: const TextStyle(
          fontWeight: FontWeight.w600, color: AppTheme.textDark));
}
