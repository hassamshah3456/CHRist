import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/collection_provider.dart';
import '../services/location_service.dart';
import '../services/sync_service.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import 'auth/welcome_screen.dart';
import 'collect/collect_consent_screen.dart';
import 'payment_screen.dart';
import 'collections_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _locationOn = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CollectionProvider>().refreshStats();
      _checkLocation();
    });
  }

  Future<void> _checkLocation() async {
    final loc = context.read<LocationService>();
    final ok = await loc.ensurePermission();
    if (mounted) setState(() => _locationOn = ok);
  }

  Future<void> _startCollecting() async {
    // Ensure location before a collection so it gets geo-tagged.
    await _checkLocation();
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const CollectConsentScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final cp = context.watch<CollectionProvider>();
    final name = auth.user?.name ?? 'Collector';
    final firstName = name.split(' ').first;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            await context.read<SyncService>().syncNow();
            await context.read<CollectionProvider>().refreshStats();
            await _checkLocation();
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 30),
            children: [
              _Header(firstName: firstName, onLogout: _confirmLogout),
              const SizedBox(height: 20),
              if (!_locationOn) ...[
                LocationBanner(onEnable: () async {
                  await context.read<LocationService>().openLocationSettings();
                  _checkLocation();
                }),
                const SizedBox(height: 16),
              ],
              if (cp.pendingSync > 0) ...[
                _PendingChip(count: cp.pendingSync),
                const SizedBox(height: 16),
              ],
              _StatsGrid(stats: cp.stats),
              const SizedBox(height: 22),
              ElevatedButton.icon(
                onPressed: _startCollecting,
                icon: const Icon(Icons.add_location_alt_rounded),
                label: const Text('Start Collecting'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                      builder: (_) => const CollectionsScreen()),
                ),
                icon: const Icon(Icons.history_rounded),
                label: const Text('See past collections'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const PaymentScreen()),
                ),
                icon: const Icon(Icons.payments_outlined),
                label: const Text('My payments'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmLogout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
            'Unsynced collections will be cleared on this device.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Sign out')),
        ],
      ),
    );
    if (ok == true && mounted) {
      await context.read<AuthProvider>().logout();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const WelcomeScreen()),
          (_) => false,
        );
      }
    }
  }
}

class _Header extends StatelessWidget {
  final String firstName;
  final VoidCallback onLogout;
  const _Header({required this.firstName, required this.onLogout});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Welcome back,',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
              Text(
                firstName,
                style: const TextStyle(
                    fontSize: 26, fontWeight: FontWeight.w800),
              ),
            ],
          ),
        ),
        IconButton(
          onPressed: onLogout,
          icon: const Icon(Icons.logout_rounded),
          tooltip: 'Sign out',
        ),
      ],
    );
  }
}

class _PendingChip extends StatelessWidget {
  final int count;
  const _PendingChip({required this.count});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppTheme.accent.withOpacity(.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Icon(Icons.sync_rounded, color: AppTheme.accent, size: 20),
          const SizedBox(width: 8),
          Text(
            '$count collection${count == 1 ? '' : 's'} waiting to sync',
            style: const TextStyle(
                color: AppTheme.textDark, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _StatsGrid extends StatelessWidget {
  final Stats stats;
  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            _StatTile(
              label: 'Today',
              value: stats.today,
              icon: Icons.today_rounded,
              color: AppTheme.primary,
            ),
            const SizedBox(width: 14),
            _StatTile(
              label: 'This week',
              value: stats.week,
              icon: Icons.calendar_view_week_rounded,
              color: AppTheme.accent,
            ),
          ],
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            _StatTile(
              label: 'This month',
              value: stats.month,
              icon: Icons.calendar_month_rounded,
              color: const Color(0xFF7A5AF8),
            ),
            const SizedBox(width: 14),
            _StatTile(
              label: 'Total',
              value: stats.total,
              icon: Icons.dataset_rounded,
              color: AppTheme.success,
            ),
          ],
        ),
        const SizedBox(height: 14),
        SectionCard(
          child: Row(
            children: [
              _ConsentStat(
                  label: 'Consent: Yes',
                  value: stats.consentYes,
                  color: AppTheme.success),
              Container(
                  width: 1, height: 36, color: const Color(0xFFE6E9F2)),
              _ConsentStat(
                  label: 'Consent: No',
                  value: stats.consentNo,
                  color: AppTheme.danger),
            ],
          ),
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final int value;
  final IconData icon;
  final Color color;
  const _StatTile({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: SectionCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withOpacity(.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: color, size: 22),
            ),
            const SizedBox(height: 14),
            Text(
              '$value',
              style:
                  const TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
            ),
            Text(label,
                style: const TextStyle(
                    color: AppTheme.textMuted, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _ConsentStat extends StatelessWidget {
  final String label;
  final int value;
  final Color color;
  const _ConsentStat(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text('$value',
              style: TextStyle(
                  fontSize: 22, fontWeight: FontWeight.w800, color: color)),
          const SizedBox(height: 2),
          Text(label,
              style:
                  const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
        ],
      ),
    );
  }
}
