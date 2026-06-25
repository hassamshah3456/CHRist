import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../models/answer.dart';
import '../../models/question.dart';
import '../../providers/auth_provider.dart';
import '../../providers/collection_provider.dart';
import '../../services/location_service.dart';
import '../../services/questionnaire_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';

/// The entire collection on one scrollable form: child age, who is carrying
/// the child, the dynamic screening questions, an optional medical-record
/// photo, and (for triple-positive cases) the caregiver's phone. One Save.
class CollectFormScreen extends StatefulWidget {
  const CollectFormScreen({super.key});

  @override
  State<CollectFormScreen> createState() => _CollectFormScreenState();
}

class _CollectFormScreenState extends State<CollectFormScreen> {
  final _uuid = const Uuid();

  // Child
  final _age = TextEditingController();
  final _ageMonths = TextEditingController();
  String? _carrying; // Father / Mother / Others
  final _carryingOther = TextEditingController();

  // Caregiver phone (child's) — required for triple-positive cases.
  final _caregiverPhone = TextEditingController();

  // Medical record (optional photo).
  String? _medicalPhoto;

  // Screening answers, keyed by question id.
  bool _loading = true;
  List<Question> _questions = [];
  final Map<String, bool?> _yesNo = {};
  final Map<String, String?> _single = {};
  final Map<String, Set<String>> _multi = {};
  final Map<String, TextEditingController> _text = {};
  final Map<String, String> _notes = {};
  final Map<String, String> _photos = {};

  CapturedLocation _location = const CapturedLocation();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
    _captureLocation();
  }

  Future<void> _captureLocation() async {
    final loc = await context.read<LocationService>().capture();
    if (mounted) setState(() => _location = loc);
  }

  Future<void> _load() async {
    final qs = await context.read<QuestionnaireService>().load();
    if (!mounted) return;
    for (final q in qs) {
      if (q.qtype == 'multi_choice') _multi[q.id] = <String>{};
      if (q.qtype == 'number' || q.qtype == 'text') {
        _text[q.id] = TextEditingController();
      }
    }
    setState(() {
      _questions = qs;
      _loading = false;
    });
  }

  @override
  void dispose() {
    _age.dispose();
    _ageMonths.dispose();
    _carryingOther.dispose();
    _caregiverPhone.dispose();
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// Triple-positive = 3 or more "secondary aim" yes/no questions answered Yes.
  bool get _triplePositive {
    var yes = 0;
    for (final q in _questions) {
      if (q.secondaryAim && q.qtype == 'yes_no' && _yesNo[q.id] == true) yes++;
    }
    return yes >= 3;
  }

  Future<void> _pickPhoto({String? qid}) async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_rounded),
              title: const Text('Take a photo'),
              onTap: () => Navigator.pop(context, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_rounded),
              title: const Text('Choose from gallery'),
              onTap: () => Navigator.pop(context, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null) return;
    try {
      final x = await ImagePicker()
          .pickImage(source: source, imageQuality: 70, maxWidth: 1600);
      if (x == null) return;
      final dir = await getApplicationDocumentsDirectory();
      final dest = p.join(dir.path, 'photo_${_uuid.v4()}${p.extension(x.path)}');
      await File(x.path).copy(dest);
      if (!mounted) return;
      setState(() {
        if (qid == null) {
          _medicalPhoto = dest;
        } else {
          _photos[qid] = dest;
        }
      });
    } catch (_) {
      if (mounted) showSnack(context, 'Could not capture photo.', error: true);
    }
  }

  String? _validate() {
    final age = int.tryParse(_age.text.trim());
    if (_age.text.trim().isEmpty || age == null || age < 0 || age > 18) {
      return 'Enter a valid age (0–18 years).';
    }
    final mTxt = _ageMonths.text.trim();
    if (mTxt.isNotEmpty) {
      final m = int.tryParse(mTxt);
      if (m == null || m < 0 || m > 11) return 'Enter valid months (0–11).';
    }
    if (_carrying == null) return 'Select who is carrying the child.';
    if (_carrying == 'Others' && _carryingOther.text.trim().isEmpty) {
      return 'Please specify who is carrying the child.';
    }
    for (final q in _questions) {
      if (!q.required) continue;
      switch (q.qtype) {
        case 'yes_no':
          if (_yesNo[q.id] == null) return q.title;
          break;
        case 'single_choice':
          if (_single[q.id] == null) return q.title;
          break;
        case 'multi_choice':
          if ((_multi[q.id] ?? {}).isEmpty) return q.title;
          break;
        case 'number':
        case 'text':
          if ((_text[q.id]?.text.trim() ?? '').isEmpty) return q.title;
          break;
      }
    }
    if (_triplePositive && _caregiverPhone.text.trim().length < 7) {
      return "Caregiver phone is required for triple-positive cases.";
    }
    return null;
  }

  List<CollectionAnswer> _buildAnswers() {
    final out = <CollectionAnswer>[];
    for (final q in _questions) {
      CollectionAnswer? a;
      switch (q.qtype) {
        case 'yes_no':
          final v = _yesNo[q.id];
          if (v == null) break;
          a = CollectionAnswer(
            questionId: q.id,
            questionCode: q.code,
            questionTitle: q.title,
            qtype: q.qtype,
            valueBool: v,
            valueText: _notes[q.id],
            photoLocalPath: _photos[q.id],
          );
          break;
        case 'single_choice':
          if (_single[q.id] == null) break;
          a = CollectionAnswer(
            questionId: q.id,
            questionCode: q.code,
            questionTitle: q.title,
            qtype: q.qtype,
            valueText: _single[q.id],
          );
          break;
        case 'multi_choice':
          final set = _multi[q.id] ?? {};
          if (set.isEmpty) break;
          a = CollectionAnswer(
            questionId: q.id,
            questionCode: q.code,
            questionTitle: q.title,
            qtype: q.qtype,
            valueText: set.join(', '),
          );
          break;
        case 'number':
          final t = _text[q.id]?.text.trim() ?? '';
          if (t.isEmpty) break;
          a = CollectionAnswer(
            questionId: q.id,
            questionCode: q.code,
            questionTitle: q.title,
            qtype: q.qtype,
            valueNumber: double.tryParse(t),
            valueText: double.tryParse(t) == null ? t : null,
          );
          break;
        case 'text':
          final t = _text[q.id]?.text.trim() ?? '';
          if (t.isEmpty) break;
          a = CollectionAnswer(
            questionId: q.id,
            questionCode: q.code,
            questionTitle: q.title,
            qtype: q.qtype,
            valueText: t,
          );
          break;
      }
      if (a != null) out.add(a);
    }
    return out;
  }

  Future<void> _save() async {
    final err = _validate();
    if (err != null) {
      showSnack(context, err, error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() => _saving = true);
    final auth = context.read<AuthProvider>();
    final carryingCode =
        _carrying == 'Others' ? 'other' : _carrying!.toLowerCase();
    try {
      await context.read<CollectionProvider>().addCollection(
            collectorName: auth.user?.name ?? 'Collector',
            verbalConsent: true,
            phone: _caregiverPhone.text.trim().isEmpty
                ? null
                : _caregiverPhone.text.trim(),
            childAge: int.tryParse(_age.text.trim()),
            childAgeMonths: _ageMonths.text.trim().isEmpty
                ? null
                : int.tryParse(_ageMonths.text.trim()),
            responder: carryingCode,
            responderOther:
                _carrying == 'Others' ? _carryingOther.text.trim() : null,
            medicalRecord: _medicalPhoto != null ? true : null,
            medicalRecordPhotoLocalPath: _medicalPhoto,
            lat: _location.lat,
            lng: _location.lng,
            address: _location.address,
            answers: _buildAnswers(),
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
      appBar: AppBar(title: const Text('New Collection')),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                      children: [
                        _section('Child age'),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(child: _ageField(_age, 'Years')),
                            const SizedBox(width: 12),
                            Expanded(
                                child: _ageField(_ageMonths, 'Months (0–11)')),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                                child: _quickPicks(
                                    _age, const [1, 2, 3, 4, 5])),
                            const SizedBox(width: 12),
                            Expanded(
                                child: _quickPicks(
                                    _ageMonths, const [2, 4, 6, 8, 10, 11])),
                          ],
                        ),
                        const SizedBox(height: 22),
                        _section('Who is carrying the child'),
                        OptionChips(
                          options: const ['Father', 'Mother', 'Others'],
                          value: _carrying,
                          onChanged: (v) => setState(() => _carrying = v),
                        ),
                        if (_carrying == 'Others') ...[
                          const SizedBox(height: 12),
                          TextField(
                            controller: _carryingOther,
                            decoration: const InputDecoration(
                              labelText: 'Specify',
                              prefixIcon: Icon(Icons.edit_outlined),
                            ),
                          ),
                        ],
                        const SizedBox(height: 22),
                        _section('Screening'),
                        ..._questions.map(_questionTile),
                        const SizedBox(height: 22),
                        _section('Medical record (optional)'),
                        if (_medicalPhoto != null) ...[
                          ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: Image.file(File(_medicalPhoto!),
                                height: 150,
                                width: double.infinity,
                                fit: BoxFit.cover),
                          ),
                          const SizedBox(height: 8),
                        ],
                        OutlinedButton.icon(
                          onPressed: () => _pickPhoto(),
                          icon: const Icon(Icons.photo_camera_rounded),
                          label: Text(_medicalPhoto == null
                              ? 'Add medical record photo (optional)'
                              : 'Replace photo'),
                        ),
                        const SizedBox(height: 22),
                        _section("Child caregiver's phone"
                            '${_triplePositive ? ' (required)' : ' (optional)'}'),
                        const Text(
                          'Phone number of the child’s caregiver. Required for '
                          'triple-positive cases.',
                          style: TextStyle(
                              color: AppTheme.textMuted, fontSize: 13),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _caregiverPhone,
                          keyboardType: TextInputType.phone,
                          decoration: const InputDecoration(
                            hintText: 'e.g. 98765 43210',
                            prefixIcon: Icon(Icons.phone_outlined),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 6, 20, 14),
                    child: ElevatedButton.icon(
                      onPressed: _saving ? null : _save,
                      icon: _saving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2.2, color: Colors.white))
                          : const Icon(Icons.check_rounded),
                      label: Text(_saving ? 'Saving…' : 'Save Collection'),
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _section(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(text,
            style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                color: AppTheme.textDark)),
      );

  Widget _ageField(TextEditingController c, String hint) => TextField(
        controller: c,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          hintText: hint,
          prefixIcon: const Icon(Icons.cake_outlined),
        ),
      );

  /// Tappable shortcut chips that fill the [target] field.
  Widget _quickPicks(TextEditingController target, List<int> values) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: values
          .map((v) => ActionChip(
                label: Text('$v'),
                visualDensity: VisualDensity.compact,
                onPressed: () => setState(() {
                  target.text = '$v';
                  target.selection = TextSelection.collapsed(
                      offset: target.text.length);
                }),
              ))
          .toList(),
    );
  }

  Widget _questionTile(Question q) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: SectionCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(q.title,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 15)),
                ),
                if (q.secondaryAim)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEDE8FE),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text('2° aim',
                        style: TextStyle(
                            fontSize: 11,
                            color: Color(0xFF7A5AF8),
                            fontWeight: FontWeight.w700)),
                  ),
              ],
            ),
            if (q.helpText != null && q.helpText!.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(q.helpText!,
                  style:
                      const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
            ],
            const SizedBox(height: 12),
            _questionInput(q),
          ],
        ),
      ),
    );
  }

  Widget _questionInput(Question q) {
    switch (q.qtype) {
      case 'yes_no':
        return _yesNoInput(q);
      case 'single_choice':
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: q.options
              .map((o) => ChoiceChip(
                    label: Text(o),
                    selected: _single[q.id] == o,
                    onSelected: (_) => setState(() => _single[q.id] = o),
                  ))
              .toList(),
        );
      case 'multi_choice':
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: q.options.map((o) {
            final set = _multi[q.id] ?? <String>{};
            return FilterChip(
              label: Text(o),
              selected: set.contains(o),
              onSelected: (sel) => setState(() {
                sel ? set.add(o) : set.remove(o);
                _multi[q.id] = set;
              }),
            );
          }).toList(),
        );
      case 'number':
        return TextField(
          controller: _text[q.id],
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(hintText: 'Enter a number'),
        );
      case 'text':
        return TextField(
          controller: _text[q.id],
          decoration: const InputDecoration(hintText: 'Type your answer'),
        );
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _yesNoInput(Question q) {
    final v = _yesNo[q.id];
    final showExtras = v == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        YesNoButtons(
          value: v,
          onChanged: (val) => setState(() {
            _yesNo[q.id] = val;
            if (!val) {
              _photos.remove(q.id);
              _notes.remove(q.id);
            }
          }),
        ),
        if (showExtras && q.noteOnYes) ...[
          const SizedBox(height: 12),
          TextField(
            decoration: const InputDecoration(hintText: 'Add a note'),
            onChanged: (t) => _notes[q.id] = t,
          ),
        ],
        if (showExtras && q.photoOnYes) ...[
          const SizedBox(height: 12),
          if (_photos[q.id] != null)
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(File(_photos[q.id]!),
                  height: 140, width: double.infinity, fit: BoxFit.cover),
            ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () => _pickPhoto(qid: q.id),
            icon: const Icon(Icons.photo_camera_rounded),
            label: Text(_photos[q.id] == null
                ? 'Attach photo (optional)'
                : 'Replace photo'),
          ),
        ],
      ],
    );
  }
}
