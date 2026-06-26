/// An admin-defined screening question, fetched from the server and rendered
/// dynamically by the collection flow.
class Question {
  final String id;
  final String code;
  final int orderIndex;
  final String title;
  final String? helpText;
  final String qtype; // yes_no | single_choice | multi_choice | number | text
  final List<String> options;
  final bool required;
  final bool secondaryAim;
  final bool photoOnYes;
  final bool noteOnYes;
  // Per-language overrides: {"hi": {"title":..,"help_text":..,"options":[..]}}
  final Map<String, dynamic> translations;

  const Question({
    required this.id,
    required this.code,
    required this.orderIndex,
    required this.title,
    this.helpText,
    required this.qtype,
    this.options = const [],
    this.required = true,
    this.secondaryAim = false,
    this.photoOnYes = false,
    this.noteOnYes = false,
    this.translations = const {},
  });

  Map<String, dynamic>? _tr(String lang) {
    final t = translations[lang];
    return t is Map<String, dynamic> ? t : (t is Map ? Map<String, dynamic>.from(t) : null);
  }

  /// Title in [lang], falling back to the base (English) title.
  String localizedTitle(String lang) {
    final v = _tr(lang)?['title'];
    return (v is String && v.trim().isNotEmpty) ? v : title;
  }

  String? localizedHelp(String lang) {
    final v = _tr(lang)?['help_text'];
    return (v is String && v.trim().isNotEmpty) ? v : helpText;
  }

  List<String> localizedOptions(String lang) {
    final v = _tr(lang)?['options'];
    if (v is List && v.length == options.length && v.isNotEmpty) {
      return v.map((e) => e.toString()).toList();
    }
    return options;
  }

  factory Question.fromApiJson(Map<String, dynamic> j) => Question(
        id: j['id'] as String,
        code: j['code'] as String,
        orderIndex: j['order_index'] as int? ?? 0,
        title: j['title'] as String? ?? '',
        helpText: j['help_text'] as String?,
        qtype: j['qtype'] as String? ?? 'yes_no',
        options:
            (j['options'] as List?)?.map((e) => e.toString()).toList() ?? [],
        required: j['required'] as bool? ?? true,
        secondaryAim: j['secondary_aim'] as bool? ?? false,
        photoOnYes: j['photo_on_yes'] as bool? ?? false,
        noteOnYes: j['note_on_yes'] as bool? ?? false,
        translations: (j['translations'] as Map?)?.cast<String, dynamic>() ?? const {},
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'code': code,
        'order_index': orderIndex,
        'title': title,
        'help_text': helpText,
        'qtype': qtype,
        'options': options,
        'required': required,
        'secondary_aim': secondaryAim,
        'photo_on_yes': photoOnYes,
        'note_on_yes': noteOnYes,
        'translations': translations,
      };
}
