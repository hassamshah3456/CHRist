import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../i18n/app_localizations.dart';
import '../providers/collection_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

/// Shows the signed-in collector how much they've earned: total entries,
/// entries since the last payout, the amount due, and the last payment received.
class PaymentScreen extends StatefulWidget {
  const PaymentScreen({super.key});

  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen> {
  Map<String, dynamic>? _data;
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
      final res = await api.get('/collections/payment');
      if (!mounted) return;
      setState(() {
        _data = (res as Map).cast<String, dynamic>();
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load payments. Check your connection.';
        _loading = false;
      });
    }
  }

  String _money(String cur, num v) => '$cur${v % 1 == 0 ? v.toInt() : v}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(context.t('my_payments_title'))),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? ListView(children: [
                      const SizedBox(height: 120),
                      Center(
                          child: Text(_error!,
                              style:
                                  const TextStyle(color: AppTheme.textMuted))),
                    ])
                  : _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
    final d = _data!;
    final cur = (d['currency'] ?? '₹') as String;
    final perEntry = (d['per_entry'] ?? 0) as num;
    final training = (d['training'] ?? 0) as num;
    final total = (d['total_entries'] ?? 0) as num;
    final unpaid = (d['unpaid_entries'] ?? 0) as num;
    final due = (d['due'] ?? 0) as num;
    final trainingPaid = (d['training_paid'] ?? false) as bool;
    final last = d['last_payout'] as Map?;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 30),
      children: [
        // Headline: amount due now.
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.t('due_now'),
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
              const SizedBox(height: 4),
              Text(_money(cur, due),
                  style: const TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.primary)),
              const SizedBox(height: 4),
              Text('$unpaid entr${unpaid == 1 ? 'y' : 'ies'} since last payout'
                  '${trainingPaid ? '' : ' + training'}',
                  style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
            ],
          ),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
                child: _MiniStat(
                    label: context.t('total_entries'), value: '$total')),
            const SizedBox(width: 12),
            Expanded(
                child: _MiniStat(
                    label: context.t('rate_per_entry'), value: _money(cur, perEntry))),
          ],
        ),
        const SizedBox(height: 14),
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.t('training_fee'),
                  style: TextStyle(
                      fontWeight: FontWeight.w700, color: AppTheme.textDark)),
              const SizedBox(height: 6),
              Row(
                children: [
                  Text(_money(cur, training),
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w700)),
                  const SizedBox(width: 10),
                  _Pill(
                    text: trainingPaid ? context.t('paid') : context.t('pending'),
                    color: trainingPaid ? AppTheme.success : AppTheme.danger,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.t('last_payout'),
                  style: TextStyle(
                      fontWeight: FontWeight.w700, color: AppTheme.textDark)),
              const SizedBox(height: 8),
              if (last == null)
                Text(context.t('no_payouts'),
                    style: TextStyle(color: AppTheme.textMuted))
              else
                Row(
                  children: [
                    const Icon(Icons.check_circle_rounded,
                        color: AppTheme.success, size: 22),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Paid ${_money(cur, (last['amount'] ?? 0) as num)} '
                        'on ${_fmtDate(last['created_at'] as String?)} '
                        '(${last['entries_count']} entries)',
                        style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: AppTheme.textDark),
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ],
    );
  }

  String _fmtDate(String? iso) {
    if (iso == null) return '—';
    try {
      return DateFormat('d MMM yyyy').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  const _MiniStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
          const SizedBox(height: 6),
          Text(value,
              style: const TextStyle(
                  fontSize: 22, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final String text;
  final Color color;
  const _Pill({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontWeight: FontWeight.w700, fontSize: 12)),
    );
  }
}
