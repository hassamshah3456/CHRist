import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../i18n/app_localizations.dart';
import '../../models/answer.dart';
import '../../models/question.dart';
import '../../providers/auth_provider.dart';
import '../../providers/collection_provider.dart';
import '../../services/location_service.dart';
import '../../services/photo_storage.dart';
import '../../services/questionnaire_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import '../../widgets/local_image.dart';

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
  bool? _verbalConsent;

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
  Timer? _locTimer;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
    _captureLocation();
  }

  Future<void> _captureLocation() async {
    final loc = await context.read<LocationService>().capture();
    if (!mounted) return;
    setState(() => _location = loc);
    // A single GPS attempt can fail (cold start, indoors). Keep retrying in the
    // background while the form is open so a fix is ready by the time they save.
    if (!loc.hasFix) {
      _locTimer ??= Timer.periodic(const Duration(seconds: 5), (t) async {
        if (!mounted || _location.hasFix) {
          t.cancel();
          _locTimer = null;
          return;
        }
        final retry = await context.read<LocationService>().capture();
        if (!mounted) return;
        if (retry.hasFix) {
          setState(() => _location = retry);
          t.cancel();
          _locTimer = null;
        }
      });
    }
  }

  Future<void> _load() async {
    final qs = await context.read<QuestionnaireService>().load();
    if (!mounted) return;
    for (final q in qs) {
      _prepareState(q);
      if (q.followUp != null) _prepareState(q.followUp!);
    }
    setState(() {
      _questions = qs;
      _loading = false;
    });
  }

  /// Sets up the per-question controllers/sets used by the input widgets.
  void _prepareState(Question q) {
    if (q.qtype == 'multi_choice') _multi[q.id] = <String>{};
    if (q.qtype == 'number' || q.qtype == 'text') {
      _text[q.id] = TextEditingController();
    }
  }

  @override
  void dispose() {
    _locTimer?.cancel();
    _age.dispose();
    _ageMonths.dispose();
    _carryingOther.dispose();
    _caregiverPhone.dispose();
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  String get _lang => context.read<LocaleProvider>().code;

  /// Triple-positive (and quadruple+): 3 or more of the admin-loaded screening
  /// yes/no questions answered "Yes" → caregiver phone becomes required.
  bool get _triplePositive {
    var yes = 0;
    for (final q in _questions) {
      if (q.qtype == 'yes_no' && _yesNo[q.id] == true) yes++;
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
              title: Text(context.t('take_photo')),
              onTap: () => Navigator.pop(context, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_rounded),
              title: Text(context.t('choose_gallery')),
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
      if (!mounted) return;
      setState(() {
        if (qid == null) {
          _medicalPhoto = stored;
        } else {
          _photos[qid] = stored;
        }
      });
    } catch (_) {
      if (mounted) {
        showSnack(context, context.t('could_not_capture_photo'), error: true);
      }
    }
  }

  String? _validate() {
    if (_verbalConsent == null) {
      return 'Please record whether verbal consent was obtained.';
    }
    final age = int.tryParse(_age.text.trim());
    if (_age.text.trim().isEmpty || age == null || age < 0 || age > 18) {
      return context.t('invalid_age');
    }
    final mTxt = _ageMonths.text.trim();
    if (mTxt.isNotEmpty) {
      final m = int.tryParse(mTxt);
      if (m == null || m < 0 || m > 11) return context.t('invalid_months');
    }
    if (_carrying == null) return context.t('select_carrying');
    if (_carrying == 'Others' && _carryingOther.text.trim().isEmpty) {
      return context.t('specify_carrying');
    }
    for (final q in _questions) {
      final missing = _missingAnswer(q);
      if (missing != null) return missing;
      // A follow-up is only required when its parent yes/no is answered "Yes".
      if (q.qtype == 'yes_no' &&
          _yesNo[q.id] == true &&
          q.followUp != null) {
        final fuMissing = _missingAnswer(q.followUp!);
        if (fuMissing != null) return fuMissing;
      }
    }
    if (_triplePositive && _caregiverPhone.text.trim().length < 7) {
      return context.t('caregiver_required_msg');
    }
    return null;
  }

  /// Returns a localized "please answer …" message if [q] is required and
  /// unanswered, otherwise null.
  String? _missingAnswer(Question q) {
    if (!q.required) return null;
    bool answered;
    switch (q.qtype) {
      case 'yes_no':
        answered = _yesNo[q.id] != null;
        break;
      case 'single_choice':
        answered = _single[q.id] != null;
        break;
      case 'multi_choice':
        answered = (_multi[q.id] ?? {}).isNotEmpty;
        break;
      case 'number':
      case 'text':
        answered = (_text[q.id]?.text.trim() ?? '').isNotEmpty;
        break;
      default:
        answered = true;
    }
    return answered ? null : '${context.t('please_answer')}: ${q.localizedTitle(_lang)}';
  }

  List<CollectionAnswer> _buildAnswers() {
    final out = <CollectionAnswer>[];
    for (final q in _questions) {
      final a = _answerFor(q);
      if (a != null) out.add(a);
      // Capture the follow-up answer only when the parent was answered "Yes".
      if (q.qtype == 'yes_no' && _yesNo[q.id] == true && q.followUp != null) {
        final fu = _answerFor(q.followUp!);
        if (fu != null) out.add(fu);
      }
    }
    return out;
  }

  /// Builds the [CollectionAnswer] for a single question (parent or follow-up)
  /// from the current form state, or null if it wasn't answered.
  CollectionAnswer? _answerFor(Question q) {
    switch (q.qtype) {
      case 'yes_no':
        final v = _yesNo[q.id];
        if (v == null) return null;
        return CollectionAnswer(
          questionId: q.id,
          questionCode: q.code,
          questionTitle: q.title,
          qtype: q.qtype,
          valueBool: v,
          valueText: _notes[q.id],
          photoLocalPath: _photos[q.id],
        );
      case 'single_choice':
        if (_single[q.id] == null) return null;
        return CollectionAnswer(
          questionId: q.id,
          questionCode: q.code,
          questionTitle: q.title,
          qtype: q.qtype,
          valueText: _single[q.id],
        );
      case 'multi_choice':
        final set = _multi[q.id] ?? {};
        if (set.isEmpty) return null;
        return CollectionAnswer(
          questionId: q.id,
          questionCode: q.code,
          questionTitle: q.title,
          qtype: q.qtype,
          valueText: set.join(', '),
        );
      case 'number':
        final t = _text[q.id]?.text.trim() ?? '';
        if (t.isEmpty) return null;
        return CollectionAnswer(
          questionId: q.id,
          questionCode: q.code,
          questionTitle: q.title,
          qtype: q.qtype,
          valueNumber: double.tryParse(t),
          valueText: double.tryParse(t) == null ? t : null,
        );
      case 'text':
        final t = _text[q.id]?.text.trim() ?? '';
        if (t.isEmpty) return null;
        return CollectionAnswer(
          questionId: q.id,
          questionCode: q.code,
          questionTitle: q.title,
          qtype: q.qtype,
          valueText: t,
        );
      default:
        return null;
    }
  }

  Future<void> _save() async {
    final err = _validate();
    if (err != null) {
      showSnack(context, err, error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() => _saving = true);

    // Collections must be geo-tagged. If we don't have a fix yet, try once more
    // (this also falls back to the last known position) before refusing to save.
    if (!_location.hasFix) {
      final retry = await context.read<LocationService>().capture();
      if (!mounted) return;
      if (retry.hasFix) {
        _location = retry;
      } else {
        setState(() => _saving = false);
        showSnack(context, context.t('location_not_ready'), error: true);
        return;
      }
    }

    final auth = context.read<AuthProvider>();
    final carryingCode =
        _carrying == 'Others' ? 'other' : _carrying!.toLowerCase();
    try {
      await context.read<CollectionProvider>().addCollection(
            collectorName: auth.user?.name ?? 'Collector',
            verbalConsent: _verbalConsent!,
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
      showSnack(context, context.t('collection_saved'));
      Navigator.of(context).popUntil((r) => r.isFirst);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showSnack(context, '${context.t('could_not_save')}: $e', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(context.t('new_collection'))),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                      children: [
                        _section('Verbal consent'),
                        const Text(
                          'Did the caregiver give verbal consent for this screening?',
                          style: TextStyle(
                              color: AppTheme.textMuted, fontSize: 13),
                        ),
                        const SizedBox(height: 10),
                        YesNoButtons(
                          value: _verbalConsent,
                          onChanged: (v) => setState(() => _verbalConsent = v),
                        ),
                        const SizedBox(height: 22),
                        _section(context.t('child_age')),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(child: _ageField(_age, context.t('years'))),
                            const SizedBox(width: 12),
                            Expanded(
                                child: _ageField(
                                    _ageMonths, context.t('months_0_11'))),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                                child: _quickPicks(
                                    _age, const [0, 1, 2, 3, 4, 5])),
                            const SizedBox(width: 12),
                            Expanded(
                                child: _quickPicks(
                                    _ageMonths, const [0, 2, 4, 6, 8, 10, 11])),
                          ],
                        ),
                        const SizedBox(height: 22),
                        _section(context.t('who_carrying')),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: const ['Father', 'Mother', 'Others']
                              .map((opt) => ChoiceChip(
                                    label: Text(context.t(opt.toLowerCase())),
                                    selected: _carrying == opt,
                                    onSelected: (_) =>
                                        setState(() => _carrying = opt),
                                  ))
                              .toList(),
                        ),
                        if (_carrying == 'Others') ...[
                          const SizedBox(height: 12),
                          TextField(
                            controller: _carryingOther,
                            decoration: InputDecoration(
                              labelText: context.t('specify'),
                              prefixIcon: const Icon(Icons.edit_outlined),
                            ),
                          ),
                        ],
                        const SizedBox(height: 22),
                        _section(context.t('screening')),
                        ..._questions.map(_questionTile),
                        const SizedBox(height: 22),
                        _section(context.t('medical_optional')),
                        if (_medicalPhoto != null) ...[
                          ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: LocalImage(path: _medicalPhoto!,
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
                              ? context.t('add_medical_photo')
                              : context.t('replace_photo')),
                        ),
                        const SizedBox(height: 22),
                        _section('${context.t('caregiver_phone')} '
                            '(${_triplePositive ? context.t('required') : context.t('optional')})'),
                        Text(
                          context.t('caregiver_hint'),
                          style: const TextStyle(
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
                      label: Text(
                          _saving ? context.t('saving') : context.t('save_collection')),
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
                  child: Text(q.localizedTitle(_lang),
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
            if ((q.localizedHelp(_lang) ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(q.localizedHelp(_lang)!,
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
        final opts = q.options;
        final lopts = q.localizedOptions(_lang);
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (var i = 0; i < opts.length; i++)
              ChoiceChip(
                label: Text(lopts[i]),
                selected: _single[q.id] == opts[i],
                onSelected: (_) => setState(() => _single[q.id] = opts[i]),
              ),
          ],
        );
      case 'multi_choice':
        final opts = q.options;
        final lopts = q.localizedOptions(_lang);
        final set = _multi[q.id] ?? <String>{};
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (var i = 0; i < opts.length; i++)
              FilterChip(
                label: Text(lopts[i]),
                selected: set.contains(opts[i]),
                onSelected: (sel) => setState(() {
                  sel ? set.add(opts[i]) : set.remove(opts[i]);
                  _multi[q.id] = set;
                }),
              ),
          ],
        );
      case 'number':
        return TextField(
          controller: _text[q.id],
          keyboardType: TextInputType.number,
          decoration: InputDecoration(hintText: context.t('enter_number')),
        );
      case 'text':
        return TextField(
          controller: _text[q.id],
          decoration: InputDecoration(hintText: context.t('type_answer')),
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
              // Drop any answer to the follow-up if the parent flips to "No".
              _clearAnswer(q.followUp);
            }
          }),
        ),
        if (showExtras && q.noteOnYes) ...[
          const SizedBox(height: 12),
          TextField(
            decoration: InputDecoration(hintText: context.t('add_note')),
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
            onPressed: () => _pickPhoto(qid: q.id),
            icon: const Icon(Icons.photo_camera_rounded),
            label: Text(_photos[q.id] == null
                ? context.t('attach_photo_optional')
                : context.t('replace_photo')),
          ),
        ],
        // Follow-up question: only revealed when this yes/no is "Yes".
        if (showExtras && q.followUp != null) _followUpTile(q.followUp!),
      ],
    );
  }

  /// The nested follow-up shown under a "Yes" answer. Reuses the same input
  /// widgets (incl. its own yes/no + photo/note upload).
  Widget _followUpTile(Question fu) {
    return Container(
      margin: const EdgeInsets.only(top: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.primary.withOpacity(.05),
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(color: AppTheme.primary.withOpacity(.5), width: 3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            fu.localizedTitle(_lang),
            style:
                const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
          ),
          if ((fu.localizedHelp(_lang) ?? '').isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(fu.localizedHelp(_lang)!,
                style: const TextStyle(
                    color: AppTheme.textMuted, fontSize: 12.5)),
          ],
          const SizedBox(height: 10),
          _questionInput(fu),
        ],
      ),
    );
  }

  void _clearAnswer(Question? q) {
    if (q == null) return;
    _yesNo.remove(q.id);
    _single.remove(q.id);
    _multi[q.id]?.clear();
    _text[q.id]?.clear();
    _notes.remove(q.id);
    _photos.remove(q.id);
  }
}
