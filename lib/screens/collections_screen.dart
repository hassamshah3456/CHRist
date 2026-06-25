import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../models/collection.dart';
import '../providers/collection_provider.dart';
import '../services/location_service.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import 'collect/collect_consent_screen.dart';

class CollectionsScreen extends StatefulWidget {
  const CollectionsScreen({super.key});

  @override
  State<CollectionsScreen> createState() => _CollectionsScreenState();
}

class _CollectionsScreenState extends State<CollectionsScreen> {
  // Default filter is "Last week" per spec.
  String _period = 'week';

  static const _filters = <String, String>{
    'today': 'Today',
    'yesterday': 'Yesterday',
    'week': 'Last week',
    'month': 'Last month',
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CollectionProvider>().loadCollections(_period);
    });
  }

  void _select(String period) {
    setState(() => _period = period);
    context.read<CollectionProvider>().loadCollections(period);
  }

  Future<void> _startCollecting() async {
    await context.read<LocationService>().ensurePermission();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const CollectConsentScreen()),
    );
    if (mounted) {
      context.read<CollectionProvider>().loadCollections(_period);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cp = context.watch<CollectionProvider>();

    return Scaffold(
      appBar: AppBar(title: const Text('Past Collections')),
      body: SafeArea(
        child: Column(
          children: [
            // Filter chips
            SizedBox(
              height: 46,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: _filters.entries.map((e) {
                  final selected = e.key == _period;
                  return Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: ChoiceChip(
                      label: Text(e.value),
                      selected: selected,
                      onSelected: (_) => _select(e.key),
                      showCheckmark: false,
                      selectedColor: AppTheme.primary,
                      backgroundColor: AppTheme.surface,
                      labelStyle: TextStyle(
                        color: selected ? Colors.white : AppTheme.textDark,
                        fontWeight: FontWeight.w600,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(
                          color: selected
                              ? AppTheme.primary
                              : const Color(0xFFDADFEA),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
            // Count summary
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 6, 20, 8),
              child: Row(
                children: [
                  Text(
                    '${cp.collections.length} collection'
                    '${cp.collections.length == 1 ? '' : 's'}',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                  const Spacer(),
                  Text(
                    _filters[_period]!,
                    style: const TextStyle(color: AppTheme.textMuted),
                  ),
                ],
              ),
            ),
            Expanded(
              child: cp.loading
                  ? const Center(child: CircularProgressIndicator())
                  : cp.collections.isEmpty
                      ? const _EmptyState()
                      : ListView.separated(
                          padding:
                              const EdgeInsets.fromLTRB(16, 4, 16, 100),
                          itemCount: cp.collections.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 10),
                          itemBuilder: (_, i) =>
                              _CollectionTile(c: cp.collections[i]),
                        ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _startCollecting,
        backgroundColor: AppTheme.primary,
        icon: const Icon(Icons.add_location_alt_rounded, color: Colors.white),
        label: const Text('Start Collecting',
            style: TextStyle(color: Colors.white)),
      ),
    );
  }
}

class _CollectionTile extends StatelessWidget {
  final Collection c;
  const _CollectionTile({required this.c});

  @override
  Widget build(BuildContext context) {
    final df = DateFormat('d MMM, h:mm a');
    final responder = c.responder == 'other'
        ? (c.responderOther ?? 'Other')
        : (c.responder ?? '—');

    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: (c.verbalConsent ? AppTheme.success : AppTheme.danger)
                  .withOpacity(.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              c.verbalConsent
                  ? Icons.check_circle_rounded
                  : Icons.cancel_rounded,
              color: c.verbalConsent ? AppTheme.success : AppTheme.danger,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${c.childName?.isNotEmpty == true ? c.childName : 'Child'} • '
                  '${_formatAge(c.childAge, c.childAgeMonths)} • '
                  '${_cap(c.childSex ?? '—')}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  'Responder: ${_cap(responder)}',
                  style: const TextStyle(
                      color: AppTheme.textMuted, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(Icons.schedule_rounded,
                        size: 13, color: AppTheme.textMuted),
                    const SizedBox(width: 4),
                    Text(df.format(c.collectedAt),
                        style: const TextStyle(
                            fontSize: 12, color: AppTheme.textMuted)),
                    if (!c.synced) ...[
                      const SizedBox(width: 8),
                      const Icon(Icons.sync_problem_rounded,
                          size: 14, color: AppTheme.accent),
                      const Text(' pending',
                          style: TextStyle(
                              fontSize: 11, color: AppTheme.accent)),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _cap(String s) =>
      s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1)}';

  String _formatAge(int? years, int? months) {
    if (years == null && months == null) return '—';
    final parts = <String>[];
    if (years != null) parts.add('$years yrs');
    if (months != null && months > 0) parts.add('$months mo');
    return parts.isEmpty ? '—' : parts.join(' ');
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.inbox_rounded,
              size: 64, color: AppTheme.textMuted.withOpacity(.4)),
          const SizedBox(height: 12),
          const Text('No collections in this period',
              style: TextStyle(color: AppTheme.textMuted)),
        ],
      ),
    );
  }
}
