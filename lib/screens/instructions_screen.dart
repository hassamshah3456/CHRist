import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/collection_provider.dart';
import '../theme/app_theme.dart';

/// Shows the admin-authored instructions (managed in the web dashboard).
class InstructionsScreen extends StatefulWidget {
  const InstructionsScreen({super.key});

  @override
  State<InstructionsScreen> createState() => _InstructionsScreenState();
}

class _InstructionsScreenState extends State<InstructionsScreen> {
  String? _text;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<CollectionProvider>().api;
      final res = await api.get('/collections/instructions');
      final html = ((res as Map)['html'] ?? '').toString();
      if (!mounted) return;
      setState(() {
        _text = _htmlToText(html);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load instructions. Check your connection.';
        _loading = false;
      });
    }
  }

  /// Minimal HTML → readable text (block tags become line breaks, tags stripped).
  String _htmlToText(String html) {
    var s = html;
    s = s.replaceAll(RegExp(r'<\s*br\s*/?>', caseSensitive: false), '\n');
    s = s.replaceAll(RegExp(r'</\s*(p|div|li|h[1-6])\s*>', caseSensitive: false),
        '\n');
    s = s.replaceAll(RegExp(r'<\s*li[^>]*>', caseSensitive: false), '• ');
    s = s.replaceAll(RegExp(r'<[^>]+>'), '');
    s = s
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&#39;', "'")
        .replaceAll('&quot;', '"');
    return s.replaceAll(RegExp(r'\n{3,}'), '\n\n').trim();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Instructions')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 30),
                  children: [
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 100),
                        child: Center(
                            child: Text(_error!,
                                style: const TextStyle(
                                    color: AppTheme.textMuted))),
                      )
                    else if ((_text ?? '').isEmpty)
                      const Padding(
                        padding: EdgeInsets.only(top: 100),
                        child: Center(
                            child: Text('No instructions yet.',
                                style: TextStyle(color: AppTheme.textMuted))),
                      )
                    else
                      Text(_text!,
                          style: const TextStyle(
                              fontSize: 15.5,
                              height: 1.5,
                              color: AppTheme.textDark)),
                  ],
                ),
        ),
      ),
    );
  }
}
