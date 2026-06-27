import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../models/answer.dart';
import '../../models/question.dart';
import '../../services/location_service.dart';
import '../../services/photo_storage.dart';
import '../../services/questionnaire_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import '../../widgets/local_image.dart';
import 'collect_medical_screen.dart';
import 'step_indicator.dart';

/// Step 3: dynamic, admin-managed screening questions. Saves the collection.
class CollectScreeningScreen extends StatefulWidget {
  final bool verbalConsent;
  final String phone;
  final CapturedLocation location;
  final String? childName;
  final int? childAge;
  final int? childAgeMonths;
  final String? childSex;
  final String? responder;
  final String? responderOther;

  const CollectScreeningScreen({
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
  });

  @override
  State<CollectScreeningScreen> createState() => _CollectScreeningScreenState();
}

class _CollectScreeningScreenState extends State<CollectScreeningScreen> {
  final _uuid = const Uuid();
  bool _loading = true;
  List<Question> _questions = [];

  // Answer state keyed by question id.
  final Map<String, bool?> _yesNo = {};
  final Map<String, String?> _single = {};
  final Map<String, Set<String>> _multi = {};
  final Map<String, TextEditingController> _text = {};
  final Map<String, String> _notes = {};
  final Map<String, String> _photos = {}; // local file paths

  @override
  void initState() {
    super.initState();
    final service = context.read<QuestionnaireService>();
    final cached = service.cached;
    if (service.cacheReady) {
      _setQuestions(cached, notify: false);
      _loading = false;
      service.refreshIfChanged();
    } else {
      _load();
    }
  }

  Future<void> _load() async {
    final qs = await context.read<QuestionnaireService>().load();
    if (!mounted) return;
    _setQuestions(qs);
  }

  void _setQuestions(List<Question> qs, {bool notify = true}) {
    for (final q in qs) {
      if (q.qtype == 'multi_choice') _multi[q.id] = <String>{};
      if (q.qtype == 'number' || q.qtype == 'text') {
        _text[q.id] = TextEditingController();
      }
    }
    void update() {
      _questions = qs;
      _loading = false;
    }

    if (notify) {
      setState(update);
    } else {
      update();
    }
  }

  @override
  void dispose() {
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickPhoto(String qid) async {
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
      final stored = await storePickedPhoto(x, _uuid);
      if (mounted) setState(() => _photos[qid] = stored);
    } catch (_) {
      if (mounted) showSnack(context, 'Could not capture photo.', error: true);
    }
  }

  String? _validate() {
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

  void _next() {
    final missing = _validate();
    if (missing != null) {
      showSnack(context, 'Please answer: $missing', error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectMedicalScreen(
          verbalConsent: widget.verbalConsent,
          phone: widget.phone,
          location: widget.location,
          childName: widget.childName,
          childAge: widget.childAge,
          childAgeMonths: widget.childAgeMonths,
          childSex: widget.childSex,
          responder: widget.responder,
          responderOther: widget.responderOther,
          screeningAnswers: _buildAnswers(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Screening')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const StepIndicator(step: 3),
              const SizedBox(height: 18),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator())
                    : _questions.isEmpty
                        ? const _NoQuestions()
                        : ListView.separated(
                            itemCount: _questions.length,
                            separatorBuilder: (_, __) =>
                                const SizedBox(height: 14),
                            itemBuilder: (_, i) =>
                                _buildQuestion(_questions[i], i + 1),
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

  Widget _buildQuestion(Question q, int number) {
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('$number. ',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, color: AppTheme.primary)),
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
                    color: const Color(0xFF7A5AF8).withOpacity(.12),
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
          _buildInput(q),
        ],
      ),
    );
  }

  Widget _buildInput(Question q) {
    switch (q.qtype) {
      case 'yes_no':
        return _buildYesNo(q);
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

  Widget _buildYesNo(Question q) {
    final v = _yesNo[q.id];
    final showExtras = v == true; // photo / note prompts appear on "Yes"
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: _YesNoButton(
                label: 'Yes',
                selected: v == true,
                color: AppTheme.success,
                onTap: () => setState(() => _yesNo[q.id] = true),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _YesNoButton(
                label: 'No',
                selected: v == false,
                color: AppTheme.danger,
                onTap: () => setState(() {
                  _yesNo[q.id] = false;
                  _photos.remove(q.id);
                  _notes.remove(q.id);
                }),
              ),
            ),
          ],
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
              child: LocalImage(path: _photos[q.id]!,
                  height: 140, width: double.infinity, fit: BoxFit.cover),
            ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () => _pickPhoto(q.id),
            icon: const Icon(Icons.photo_camera_rounded),
            label: Text(_photos[q.id] == null
                ? 'Attach photo (e.g. OPD card)'
                : 'Replace photo'),
          ),
        ],
      ],
    );
  }
}

class _YesNoButton extends StatelessWidget {
  final String label;
  final bool selected;
  final Color color;
  final VoidCallback onTap;
  const _YesNoButton({
    required this.label,
    required this.selected,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? color.withOpacity(.12) : Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? color : const Color(0xFFDADFEA),
            width: selected ? 1.6 : 1,
          ),
        ),
        child: Text(label,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: selected ? color : AppTheme.textDark,
            )),
      ),
    );
  }
}

class _NoQuestions extends StatelessWidget {
  const _NoQuestions();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.checklist_rounded,
              size: 60, color: AppTheme.textMuted.withOpacity(.4)),
          const SizedBox(height: 12),
          const Text('No screening questions configured.',
              style: TextStyle(color: AppTheme.textMuted)),
          const SizedBox(height: 4),
          const Text('Tap Save to record this collection.',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
        ],
      ),
    );
  }
}
