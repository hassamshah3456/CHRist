import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Lightweight i18n: a translation map + a [LocaleProvider] that persists the
/// chosen language. English is the fallback. Hindi/Kannada are auto-translated
/// and can be refined later.
class LocaleProvider extends ChangeNotifier {
  static const _key = 'app_lang';
  static const supported = ['en', 'hi', 'kn'];
  static const names = {'en': 'English', 'hi': 'हिन्दी', 'kn': 'ಕನ್ನಡ'};

  String _code = 'en';
  bool _chosen = false;
  bool _ready = false;

  String get code => _code;
  bool get chosen => _chosen; // false until the user picks on first launch
  bool get ready => _ready; // false until persisted prefs are loaded

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_key);
    if (saved != null && supported.contains(saved)) {
      _code = saved;
      _chosen = true;
    }
    _ready = true;
    notifyListeners();
  }

  Future<void> setLanguage(String code) async {
    if (!supported.contains(code)) return;
    _code = code;
    _chosen = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, code);
    notifyListeners();
  }

  String t(String key) {
    final row = _strings[key];
    if (row == null) return key;
    return row[_code] ?? row['en'] ?? key;
  }
}

/// Convenience: `context.t('key')`.
extension L10nX on BuildContext {
  String t(String key) {
    // Read without listening would miss rebuilds; callers are inside build().
    final p = _maybeLocale(this);
    return p?.t(key) ?? (_strings[key]?['en'] ?? key);
  }
}

LocaleProvider? _maybeLocale(BuildContext context) {
  try {
    return _LocaleScope.of(context);
  } catch (_) {
    return null;
  }
}

/// Minimal inherited access so `context.t` works without importing provider
/// everywhere. main.dart wires the active [LocaleProvider] in.
class _LocaleScope extends InheritedNotifier<LocaleProvider> {
  const _LocaleScope({required LocaleProvider provider, required super.child})
      : super(notifier: provider);

  static LocaleProvider of(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<_LocaleScope>();
    return scope!.notifier!;
  }
}

class LocaleScope extends StatelessWidget {
  final LocaleProvider provider;
  final Widget child;
  const LocaleScope({super.key, required this.provider, required this.child});

  @override
  Widget build(BuildContext context) =>
      _LocaleScope(provider: provider, child: child);
}

const Map<String, Map<String, String>> _strings = {
  'select_language': {
    'en': 'Select language',
    'hi': 'भाषा चुनें',
    'kn': 'ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ',
  },
  'continue': {'en': 'Continue', 'hi': 'जारी रखें', 'kn': 'ಮುಂದುವರಿಸಿ'},
  'instructions': {'en': 'Instructions', 'hi': 'निर्देश', 'kn': 'ಸೂಚನೆಗಳು'},
  'start_collecting': {
    'en': 'Start Collecting',
    'hi': 'डेटा एकत्र करें',
    'kn': 'ಡೇಟಾ ಸಂಗ್ರಹಿಸಿ',
  },
  'past_collections': {
    'en': 'See past collections',
    'hi': 'पिछले संग्रह देखें',
    'kn': 'ಹಿಂದಿನ ಸಂಗ್ರಹಗಳನ್ನು ನೋಡಿ',
  },
  'my_payments': {
    'en': 'My payments',
    'hi': 'मेरे भुगतान',
    'kn': 'ನನ್ನ ಪಾವತಿಗಳು',
  },
  'todays_entries': {
    'en': "Today's entries",
    'hi': 'आज की प्रविष्टियाँ',
    'kn': 'ಇಂದಿನ ನಮೂದುಗಳು',
  },
  'total_to_be_paid': {
    'en': 'Total to be paid',
    'hi': 'कुल देय राशि',
    'kn': 'ಪಾವತಿಸಬೇಕಾದ ಒಟ್ಟು',
  },
  'new_collection': {
    'en': 'New Collection',
    'hi': 'नया संग्रह',
    'kn': 'ಹೊಸ ಸಂಗ್ರಹ',
  },
  'child_age': {'en': 'Child age', 'hi': 'बच्चे की उम्र', 'kn': 'ಮಗುವಿನ ವಯಸ್ಸು'},
  'years': {'en': 'Years', 'hi': 'वर्ष', 'kn': 'ವರ್ಷಗಳು'},
  'months_0_11': {
    'en': 'Months (0–11)',
    'hi': 'महीने (0–11)',
    'kn': 'ತಿಂಗಳುಗಳು (0–11)',
  },
  'who_carrying': {
    'en': 'Who is carrying the child',
    'hi': 'बच्चे को कौन ले जा रहा है',
    'kn': 'ಮಗುವನ್ನು ಯಾರು ಹೊತ್ತಿದ್ದಾರೆ',
  },
  'father': {'en': 'Father', 'hi': 'पिता', 'kn': 'ತಂದೆ'},
  'mother': {'en': 'Mother', 'hi': 'माता', 'kn': 'ತಾಯಿ'},
  'others': {'en': 'Others', 'hi': 'अन्य', 'kn': 'ಇತರರು'},
  'specify': {'en': 'Specify', 'hi': 'बताएं', 'kn': 'ಸೂಚಿಸಿ'},
  'screening': {'en': 'Screening', 'hi': 'स्क्रीनिंग', 'kn': 'ಸ್ಕ್ರೀನಿಂಗ್'},
  'medical_optional': {
    'en': 'Medical record (optional)',
    'hi': 'मेडिकल रिकॉर्ड (वैकल्पिक)',
    'kn': 'ವೈದ್ಯಕೀಯ ದಾಖಲೆ (ಐಚ್ಛಿಕ)',
  },
  'add_medical_photo': {
    'en': 'Add medical record photo (optional)',
    'hi': 'मेडिकल रिकॉर्ड फोटो जोड़ें (वैकल्पिक)',
    'kn': 'ವೈದ್ಯಕೀಯ ದಾಖಲೆ ಫೋಟೋ ಸೇರಿಸಿ (ಐಚ್ಛಿಕ)',
  },
  'replace_photo': {
    'en': 'Replace photo',
    'hi': 'फोटो बदलें',
    'kn': 'ಫೋಟೋ ಬದಲಾಯಿಸಿ',
  },
  'caregiver_phone': {
    'en': "Child caregiver's phone",
    'hi': 'बच्चे के देखभालकर्ता का फोन',
    'kn': 'ಮಗುವಿನ ಆರೈಕೆದಾರರ ಫೋನ್',
  },
  'caregiver_hint': {
    'en': "Phone number of the child’s caregiver. Required for triple-positive cases.",
    'hi': 'बच्चे के देखभालकर्ता का फोन नंबर। ट्रिपल-पॉज़िटिव मामलों के लिए आवश्यक।',
    'kn': 'ಮಗುವಿನ ಆರೈಕೆದಾರರ ಫೋನ್ ಸಂಖ್ಯೆ. ಟ್ರಿಪಲ್-ಪಾಸಿಟಿವ್ ಪ್ರಕರಣಗಳಿಗೆ ಅಗತ್ಯವಿದೆ.',
  },
  'save_collection': {
    'en': 'Save Collection',
    'hi': 'संग्रह सहेजें',
    'kn': 'ಸಂಗ್ರಹ ಉಳಿಸಿ',
  },
  'saving': {'en': 'Saving…', 'hi': 'सहेजा जा रहा है…', 'kn': 'ಉಳಿಸಲಾಗುತ್ತಿದೆ…'},
  'optional': {'en': 'optional', 'hi': 'वैकल्पिक', 'kn': 'ಐಚ್ಛಿಕ'},
  'required': {'en': 'required', 'hi': 'आवश्यक', 'kn': 'ಅಗತ್ಯವಿದೆ'},
  // Auth
  'registration': {'en': 'Registration', 'hi': 'पंजीकरण', 'kn': 'ನೋಂದಣಿ'},
  'sign_in': {'en': 'Sign in', 'hi': 'साइन इन करें', 'kn': 'ಸೈನ್ ಇನ್ ಮಾಡಿ'},
  'register': {'en': 'Register', 'hi': 'पंजीकरण करें', 'kn': 'ನೋಂದಾಯಿಸಿ'},
  'full_name': {'en': 'Full name', 'hi': 'पूरा नाम', 'kn': 'ಪೂರ್ಣ ಹೆಸರು'},
  'email': {'en': 'Email', 'hi': 'ईमेल', 'kn': 'ಇಮೇಲ್'},
  'password': {'en': 'Password', 'hi': 'पासवर्ड', 'kn': 'ಪಾಸ್‌ವರ್ಡ್'},
  'upi_id_optional': {
    'en': 'UPI ID (optional)',
    'hi': 'UPI आईडी (वैकल्पिक)',
    'kn': 'UPI ಐಡಿ (ಐಚ್ಛಿಕ)',
  },
  'upi_holder_name': {
    'en': 'UPI account holder name',
    'hi': 'UPI खाताधारक का नाम',
    'kn': 'UPI ಖಾತೆದಾರರ ಹೆಸರು',
  },
  // Payments
  'my_payments_title': {
    'en': 'My Payments',
    'hi': 'मेरे भुगतान',
    'kn': 'ನನ್ನ ಪಾವತಿಗಳು',
  },
  'due_now': {'en': 'Due now', 'hi': 'अभी देय', 'kn': 'ಈಗ ಬಾಕಿ'},
  'total_entries': {
    'en': 'Total entries',
    'hi': 'कुल प्रविष्टियाँ',
    'kn': 'ಒಟ್ಟು ನಮೂದುಗಳು',
  },
  'rate_per_entry': {
    'en': 'Rate / entry',
    'hi': 'दर / प्रविष्टि',
    'kn': 'ದರ / ನಮೂದು',
  },
  'training_fee': {
    'en': 'Training fee',
    'hi': 'प्रशिक्षण शुल्क',
    'kn': 'ತರಬೇತಿ ಶುಲ್ಕ',
  },
  'last_payout': {
    'en': 'Last payout',
    'hi': 'पिछला भुगतान',
    'kn': 'ಕೊನೆಯ ಪಾವತಿ',
  },
  'no_payouts': {
    'en': 'No payouts yet.',
    'hi': 'अभी तक कोई भुगतान नहीं।',
    'kn': 'ಇನ್ನೂ ಪಾವತಿಗಳಿಲ್ಲ.',
  },
  'paid': {'en': 'Paid', 'hi': 'भुगतान किया गया', 'kn': 'ಪಾವತಿಸಲಾಗಿದೆ'},
  'pending': {'en': 'Pending', 'hi': 'लंबित', 'kn': 'ಬಾಕಿ ಇದೆ'},
  'past_collections_title': {
    'en': 'Collections',
    'hi': 'संग्रह',
    'kn': 'ಸಂಗ್ರಹಗಳು',
  },
};
