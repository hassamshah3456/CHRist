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
  // Yes / No (used by YesNoButtons and admin-managed yes/no questions)
  'yes': {'en': 'Yes', 'hi': 'हाँ', 'kn': 'ಹೌದು'},
  'no': {'en': 'No', 'hi': 'नहीं', 'kn': 'ಇಲ್ಲ'},
  // Notifications / snackbars
  'collection_saved': {
    'en': 'Collection saved.',
    'hi': 'संग्रह सहेजा गया।',
    'kn': 'ಸಂಗ್ರಹ ಉಳಿಸಲಾಗಿದೆ.',
  },
  'could_not_save': {
    'en': 'Could not save',
    'hi': 'सहेजा नहीं जा सका',
    'kn': 'ಉಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ',
  },
  'could_not_capture_photo': {
    'en': 'Could not capture photo.',
    'hi': 'फोटो कैप्चर नहीं की जा सकी।',
    'kn': 'ಫೋಟೋ ಸೆರೆಹಿಡಿಯಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.',
  },
  // Photo picker / inputs
  'take_photo': {
    'en': 'Take a photo',
    'hi': 'फोटो लें',
    'kn': 'ಫೋಟೋ ತೆಗೆಯಿರಿ',
  },
  'choose_gallery': {
    'en': 'Choose from gallery',
    'hi': 'गैलरी से चुनें',
    'kn': 'ಗ್ಯಾಲರಿಯಿಂದ ಆಯ್ಕೆಮಾಡಿ',
  },
  'add_note': {'en': 'Add a note', 'hi': 'एक नोट जोड़ें', 'kn': 'ಟಿಪ್ಪಣಿ ಸೇರಿಸಿ'},
  'attach_photo_optional': {
    'en': 'Attach photo (optional)',
    'hi': 'फोटो संलग्न करें (वैकल्पिक)',
    'kn': 'ಫೋಟೋ ಲಗತ್ತಿಸಿ (ಐಚ್ಛಿಕ)',
  },
  'enter_number': {
    'en': 'Enter a number',
    'hi': 'एक संख्या दर्ज करें',
    'kn': 'ಒಂದು ಸಂಖ್ಯೆ ನಮೂದಿಸಿ',
  },
  'type_answer': {
    'en': 'Type your answer',
    'hi': 'अपना उत्तर लिखें',
    'kn': 'ನಿಮ್ಮ ಉತ್ತರ ಟೈಪ್ ಮಾಡಿ',
  },
  // Validation messages
  'invalid_age': {
    'en': 'Enter a valid age (0–18 years).',
    'hi': 'मान्य आयु दर्ज करें (0–18 वर्ष)।',
    'kn': 'ಮಾನ್ಯ ವಯಸ್ಸನ್ನು ನಮೂದಿಸಿ (0–18 ವರ್ಷ).',
  },
  'invalid_months': {
    'en': 'Enter valid months (0–11).',
    'hi': 'मान्य महीने दर्ज करें (0–11)।',
    'kn': 'ಮಾನ್ಯ ತಿಂಗಳುಗಳನ್ನು ನಮೂದಿಸಿ (0–11).',
  },
  'select_carrying': {
    'en': 'Select who is carrying the child.',
    'hi': 'चुनें कि बच्चे को कौन ले जा रहा है।',
    'kn': 'ಮಗುವನ್ನು ಯಾರು ಹೊತ್ತಿದ್ದಾರೆ ಎಂದು ಆಯ್ಕೆಮಾಡಿ.',
  },
  'specify_carrying': {
    'en': 'Please specify who is carrying the child.',
    'hi': 'कृपया बताएं कि बच्चे को कौन ले जा रहा है।',
    'kn': 'ಮಗುವನ್ನು ಯಾರು ಹೊತ್ತಿದ್ದಾರೆ ಎಂದು ದಯವಿಟ್ಟು ಸೂಚಿಸಿ.',
  },
  'caregiver_required_msg': {
    'en': 'Caregiver phone is required for triple-positive cases.',
    'hi': 'ट्रिपल-पॉज़िटिव मामलों के लिए देखभालकर्ता का फोन आवश्यक है।',
    'kn': 'ಟ್ರಿಪಲ್-ಪಾಸಿಟಿವ್ ಪ್ರಕರಣಗಳಿಗೆ ಆರೈಕೆದಾರರ ಫೋನ್ ಅಗತ್ಯವಿದೆ.',
  },
  'please_answer': {
    'en': 'Please answer',
    'hi': 'कृपया उत्तर दें',
    'kn': 'ದಯವಿಟ್ಟು ಉತ್ತರಿಸಿ',
  },
  // Location gate (mandatory location)
  'location_required_title': {
    'en': 'Location is required',
    'hi': 'स्थान आवश्यक है',
    'kn': 'ಸ್ಥಳ ಅಗತ್ಯವಿದೆ',
  },
  'location_required_body': {
    'en': 'Turn on location to use the app. Collections must be geo-tagged, so the app stays locked until location is on.',
    'hi': 'ऐप का उपयोग करने के लिए स्थान चालू करें। संग्रहों को जियो-टैग किया जाना चाहिए, इसलिए स्थान चालू होने तक ऐप लॉक रहेगा।',
    'kn': 'ಆ್ಯಪ್ ಬಳಸಲು ಸ್ಥಳವನ್ನು ಆನ್ ಮಾಡಿ. ಸಂಗ್ರಹಗಳನ್ನು ಜಿಯೋ-ಟ್ಯಾಗ್ ಮಾಡಬೇಕು, ಆದ್ದರಿಂದ ಸ್ಥಳ ಆನ್ ಆಗುವವರೆಗೆ ಆ್ಯಪ್ ಲಾಕ್ ಆಗಿರುತ್ತದೆ.',
  },
  'turn_on_location': {
    'en': 'Turn on location',
    'hi': 'स्थान चालू करें',
    'kn': 'ಸ್ಥಳ ಆನ್ ಮಾಡಿ',
  },
  'open_app_settings': {
    'en': 'Open app settings',
    'hi': 'ऐप सेटिंग्स खोलें',
    'kn': 'ಆ್ಯಪ್ ಸೆಟ್ಟಿಂಗ್ಸ್ ತೆರೆಯಿರಿ',
  },
  'checking_location': {
    'en': 'Checking location…',
    'hi': 'स्थान जांचा जा रहा है…',
    'kn': 'ಸ್ಥಳ ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ…',
  },
  'location_off_banner': {
    'en': 'Location is off. Turn it on so collections are geo-tagged.',
    'hi': 'स्थान बंद है। इसे चालू करें ताकि संग्रह जियो-टैग हों।',
    'kn': 'ಸ್ಥಳ ಆಫ್ ಆಗಿದೆ. ಸಂಗ್ರಹಗಳು ಜಿಯೋ-ಟ್ಯಾಗ್ ಆಗಲು ಅದನ್ನು ಆನ್ ಮಾಡಿ.',
  },
  'enable': {'en': 'Enable', 'hi': 'सक्षम करें', 'kn': 'ಸಕ್ರಿಯಗೊಳಿಸಿ'},
  // Language switcher
  'change_language': {
    'en': 'Change language',
    'hi': 'भाषा बदलें',
    'kn': 'ಭಾಷೆ ಬದಲಾಯಿಸಿ',
  },
  'cancel': {'en': 'Cancel', 'hi': 'रद्द करें', 'kn': 'ರದ್ದುಮಾಡಿ'},
  'sign_out': {'en': 'Sign out', 'hi': 'साइन आउट', 'kn': 'ಸೈನ್ ಔಟ್'},
  'sign_out_q': {
    'en': 'Sign out?',
    'hi': 'साइन आउट करें?',
    'kn': 'ಸೈನ್ ಔಟ್ ಮಾಡುವುದೇ?',
  },
  'sign_out_body': {
    'en': 'Unsynced collections will be cleared on this device.',
    'hi': 'इस डिवाइस पर बिना सिंक किए संग्रह हटा दिए जाएंगे।',
    'kn': 'ಈ ಸಾಧನದಲ್ಲಿ ಸಿಂಕ್ ಆಗದ ಸಂಗ್ರಹಗಳನ್ನು ತೆರವುಗೊಳಿಸಲಾಗುತ್ತದೆ.',
  },
};
