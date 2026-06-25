import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/answer.dart';
import '../../providers/auth_provider.dart';
import '../../providers/collection_provider.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import 'step_indicator.dart';

/// Step 4: review everything captured, then save the collection.
///
/// Saving stores the record locally (offline-safe) and attempts an immediate
/// sync. On success the whole flow is popped back to where it started.
class CollectRecordsScreen extends StatefulWidget {
  final bool verbalConsent;
  final String phone;
  final CapturedLocation location;
  final String? childName;
  final int? childAge;
  final int? childAgeMonths;
  final String? childSex;
  final String? responder;
  final String? responderOther;
  final List<CollectionAnswer> screeningAnswers;

  const CollectRecordsScreen({
    super.key,
    required this.verbalConsent,
    required this.phone,
    required this.location,
    required this.childName,
    required this.childAge,
    required this.childAgeMonths,
    required this.childSex,
    required this.responder,
    required this.responderOther,
    required this.screeningAnswers,
  });

  @override
  State<CollectRecordsScreen> createState() => _CollectRecordsScreenState();
}

class _CollectRecordsScreenState extends State<CollectRecordsScreen> {
  bool _saving = false;

  String get _ageText {
    final parts = <String>[];
    if (widget.childAge != null) parts.add('${widget.childAge} yrs');
    if (widget.childAgeMonths != null && widget.childAgeMonths! > 0) {
      parts.add('${widget.childAgeMonths} mo');
    }
    return parts.isEmpty ? '—' : parts.join(' ');
  }

  String get _responderText {
    if (widget.responder == 'other') {
      return widget.responderOther?.isNotEmpty == true
          ? widget.responderOther!
          : 'Other';
    }
    return _cap(widget.responder);
  }

  Future<void> _submit() async {
    setState(() => _saving = true);
    final auth = context.read<AuthProvider>();
    try {
      await context.read<CollectionProvider>().addCollection(
            collectorName: auth.user?.name ?? 'Collector',
            verbalConsent: widget.verbalConsent,
            phone: widget.phone,
            childName: widget.childName,
            childAge: widget.childAge,
            childAgeMonths: widget.childAgeMonths,
            childSex: widget.childSex,
            responder: widget.responder,
            responderOther: widget.responderOther,
            lat: widget.location.lat,
            lng: widget.location.lng,
            address: widget.location.address,
            answers: widget.screeningAnswers,
          );
      if (!mounted) return;
      showSnack(context, 'Collection saved.');
      Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showSnack(context, 'Could not save: $e', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Review & Save')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const StepIndicator(step: 4),
              const SizedBox(height: 20),
              Expanded(
                child: ListView(
                  children: [
                    SectionCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const _CardTitle('Child'),
                          _Row('Name', widget.childName?.isNotEmpty == true
                              ? widget.childName!
                              : '—'),
                          _Row('Age', _ageText),
                          _Row('Sex', _cap(widget.childSex)),
                          _Row('Responder', _responderText),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    SectionCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const _CardTitle('Consent & contact'),
                          _Row('Phone', widget.phone),
                          _Row('Verbal consent',
                              widget.verbalConsent ? 'Yes' : 'No'),
                          _Row(
                            'Location',
                            widget.location.address ??
                                (widget.location.hasFix
                                    ? '${widget.location.lat!.toStringAsFixed(4)}, '
                                        '${widget.location.lng!.toStringAsFixed(4)}'
                                    : 'Not captured'),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    SectionCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _CardTitle(
                              'Screening (${widget.screeningAnswers.length})'),
                          if (widget.screeningAnswers.isEmpty)
                            const Padding(
                              padding: EdgeInsets.only(top: 6),
                              child: Text('No screening answers.',
                                  style: TextStyle(color: AppTheme.textMuted)),
                            )
                          else
                            ...widget.screeningAnswers
                                .map((a) => _AnswerRow(answer: a)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              ElevatedButton.icon(
                onPressed: _saving ? null : _submit,
                icon: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.2, color: Colors.white),
                      )
                    : const Icon(Icons.check_rounded),
                label: Text(_saving ? 'Saving…' : 'Save Collection'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _cap(String? s) =>
    (s == null || s.isEmpty) ? '—' : '${s[0].toUpperCase()}${s.substring(1)}';

class _CardTitle extends StatelessWidget {
  final String text;
  const _CardTitle(this.text);
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text,
            style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                color: AppTheme.textDark)),
      );
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  const _Row(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(label,
                style: const TextStyle(
                    color: AppTheme.textMuted, fontSize: 13.5)),
          ),
          Expanded(
            child: Text(value,
                style: const TextStyle(
                    color: AppTheme.textDark,
                    fontSize: 14,
                    fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

class _AnswerRow extends StatelessWidget {
  final CollectionAnswer answer;
  const _AnswerRow({required this.answer});

  String get _value {
    if (answer.valueBool != null) return answer.valueBool! ? 'Yes' : 'No';
    if (answer.valueNumber != null) {
      final n = answer.valueNumber!;
      return n == n.roundToDouble() ? n.toInt().toString() : n.toString();
    }
    if (answer.valueText?.isNotEmpty == true) return answer.valueText!;
    return '—';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(answer.questionTitle ?? answer.questionCode,
              style: const TextStyle(
                  color: AppTheme.textMuted, fontSize: 13.5)),
          const SizedBox(height: 2),
          Text(_value,
              style: const TextStyle(
                  color: AppTheme.textDark,
                  fontSize: 14,
                  fontWeight: FontWeight.w600)),
          if (answer.photoLocalPath != null) ...[
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.file(File(answer.photoLocalPath!),
                  height: 120, width: double.infinity, fit: BoxFit.cover),
            ),
          ],
        ],
      ),
    );
  }
}
