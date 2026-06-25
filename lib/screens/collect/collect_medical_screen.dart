import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../models/answer.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import 'collect_records_screen.dart';
import 'step_indicator.dart';

/// Step 4: medical record (with optional photo) and vaccines administered.
class CollectMedicalScreen extends StatefulWidget {
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

  const CollectMedicalScreen({
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
  State<CollectMedicalScreen> createState() => _CollectMedicalScreenState();
}

class _CollectMedicalScreenState extends State<CollectMedicalScreen> {
  final _uuid = const Uuid();

  bool? _hasRecord; // Medical record yes/no
  String? _photoPath; // local path of the medical-record photo
  final Set<String> _vaccines = {}; // 'opv' / 'ipv' / 'none'

  Future<void> _pickPhoto() async {
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
      final dest = p.join(dir.path, 'medrec_${_uuid.v4()}${p.extension(x.path)}');
      await File(x.path).copy(dest);
      if (mounted) setState(() => _photoPath = dest);
    } catch (_) {
      if (mounted) showSnack(context, 'Could not capture photo.', error: true);
    }
  }

  void _toggleVaccine(String v) {
    setState(() {
      if (v == 'none') {
        _vaccines
          ..clear()
          ..add('none');
      } else {
        _vaccines.remove('none');
        _vaccines.contains(v) ? _vaccines.remove(v) : _vaccines.add(v);
      }
    });
  }

  void _next() {
    if (_hasRecord == null) {
      showSnack(context, 'Select whether there is a medical record.',
          error: true);
      return;
    }
    if (_vaccines.isEmpty) {
      showSnack(context, 'Select the vaccine(s) administered (or None).',
          error: true);
      return;
    }
    FocusScope.of(context).unfocus();
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CollectRecordsScreen(
          verbalConsent: widget.verbalConsent,
          phone: widget.phone,
          location: widget.location,
          childName: widget.childName,
          childAge: widget.childAge,
          childAgeMonths: widget.childAgeMonths,
          childSex: widget.childSex,
          responder: widget.responder,
          responderOther: widget.responderOther,
          medicalRecord: _hasRecord,
          vaccines: _vaccines.join(','),
          medicalRecordPhotoPath: _hasRecord == true ? _photoPath : null,
          screeningAnswers: widget.screeningAnswers,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final showPhoto = _hasRecord == true;
    return Scaffold(
      appBar: AppBar(title: const Text('Medical Record')),
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
                    const _Label('Medical record available?'),
                    const SizedBox(height: 10),
                    YesNoButtons(
                      value: _hasRecord,
                      onChanged: (v) => setState(() {
                        _hasRecord = v;
                        if (v == false) _photoPath = null;
                      }),
                    ),
                    if (showPhoto) ...[
                      const SizedBox(height: 18),
                      const _Label('Photo of the medical record'),
                      const SizedBox(height: 10),
                      if (_photoPath != null)
                        ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.file(File(_photoPath!),
                              height: 160,
                              width: double.infinity,
                              fit: BoxFit.cover),
                        ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: _pickPhoto,
                        icon: const Icon(Icons.photo_camera_rounded),
                        label: Text(_photoPath == null
                            ? 'Add photo (camera or gallery)'
                            : 'Replace photo'),
                      ),
                    ],
                    const SizedBox(height: 24),
                    const _Label('Vaccine administered'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _VaccineChip(
                          label: 'OPV',
                          selected: _vaccines.contains('opv'),
                          onTap: () => _toggleVaccine('opv'),
                        ),
                        _VaccineChip(
                          label: 'IPV',
                          selected: _vaccines.contains('ipv'),
                          onTap: () => _toggleVaccine('ipv'),
                        ),
                        _VaccineChip(
                          label: 'None',
                          selected: _vaccines.contains('none'),
                          onTap: () => _toggleVaccine('none'),
                        ),
                      ],
                    ),
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

class _VaccineChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _VaccineChip(
      {required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onTap(),
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
