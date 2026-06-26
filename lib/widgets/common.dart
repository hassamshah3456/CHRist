import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../i18n/app_localizations.dart';
import '../services/location_service.dart';
import '../theme/app_theme.dart';

/// The app's brand wordmark used on auth screens.
class BrandLogo extends StatelessWidget {
  final bool light;
  const BrandLogo({super.key, this.light = false});

  @override
  Widget build(BuildContext context) {
    final color = light ? Colors.white : AppTheme.primary;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Image.asset(
            'assets/logo.png',
            width: 76,
            height: 76,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                color: light ? Colors.white24 : AppTheme.primary.withOpacity(.1),
                borderRadius: BorderRadius.circular(22),
              ),
              child: Icon(Icons.fact_check_rounded, size: 40, color: color),
            ),
          ),
        ),
        const SizedBox(height: 14),
        Text(
          'CRIST Tool',
          style: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w800,
            color: color,
            letterSpacing: -0.5,
          ),
        ),
      ],
    );
  }
}

/// A soft rounded card container.
class SectionCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  const SectionCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.04),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

/// Small inline banner shown when location is off.
class LocationBanner extends StatelessWidget {
  final VoidCallback onEnable;
  const LocationBanner({super.key, required this.onEnable});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.danger.withOpacity(.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.danger.withOpacity(.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.location_off_rounded,
              color: AppTheme.danger, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              context.t('location_off_banner'),
              style: const TextStyle(fontSize: 13, color: AppTheme.textDark),
            ),
          ),
          TextButton(onPressed: onEnable, child: Text(context.t('enable'))),
        ],
      ),
    );
  }
}

/// Blocks the whole app behind a mandatory location check. While the device's
/// location services are off (or permission is denied) the [child] is hidden
/// and the user is repeatedly directed to switch location on. The check
/// re-runs on a short timer and whenever the app is resumed, so the moment the
/// user turns location on they're let straight through — no manual retry.
class LocationGate extends StatefulWidget {
  final Widget child;
  const LocationGate({super.key, required this.child});

  @override
  State<LocationGate> createState() => _LocationGateState();
}

class _LocationGateState extends State<LocationGate>
    with WidgetsBindingObserver {
  bool _checking = true;
  bool _ok = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _check();
    // Keep nudging until location is on; stop polling once it is.
    _timer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!_ok) _check();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _check();
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _check() async {
    final loc = context.read<LocationService>();
    final ok = await loc.ensurePermission();
    if (!mounted) return;
    setState(() {
      _ok = ok;
      _checking = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_ok) return widget.child;
    // Avoid flashing the warning before the first check resolves.
    if (_checking) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final loc = context.read<LocationService>();
    return Scaffold(
      backgroundColor: AppTheme.surface,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                width: 92,
                height: 92,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppTheme.danger.withOpacity(.10),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.location_off_rounded,
                    size: 46, color: AppTheme.danger),
              ),
              const SizedBox(height: 24),
              Text(
                context.t('location_required_title'),
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 21, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 12),
              Text(
                context.t('location_required_body'),
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 14, color: AppTheme.textMuted, height: 1.5),
              ),
              const SizedBox(height: 28),
              ElevatedButton.icon(
                onPressed: () async {
                  await loc.openLocationSettings();
                  _check();
                },
                icon: const Icon(Icons.my_location_rounded),
                label: Text(context.t('turn_on_location')),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  await loc.openAppSettings();
                  _check();
                },
                icon: const Icon(Icons.settings_outlined),
                label: Text(context.t('open_app_settings')),
              ),
              const SizedBox(height: 20),
              if (_checking)
                const Center(
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2.4),
                  ),
                )
              else
                TextButton(
                  onPressed: _check,
                  child: Text(context.t('checking_location')),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Reusable labelled dropdown.
class LabeledDropdown<T> extends StatelessWidget {
  final String label;
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?> onChanged;
  final String? hint;
  const LabeledDropdown({
    super.key,
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(
                fontWeight: FontWeight.w600, color: AppTheme.textDark)),
        const SizedBox(height: 8),
        DropdownButtonFormField<T>(
          value: value,
          isExpanded: true,
          hint: hint != null ? Text(hint!) : null,
          items: items,
          onChanged: onChanged,
        ),
      ],
    );
  }
}

/// A two-button Yes / No selector (used on the consent and records screens).
class YesNoButtons extends StatelessWidget {
  final bool? value;
  final ValueChanged<bool> onChanged;
  const YesNoButtons({super.key, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    Widget btn(String label, bool val, Color color) {
      final selected = value == val;
      return Expanded(
        child: InkWell(
          onTap: () => onChanged(val),
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 16),
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
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: selected ? color : AppTheme.textDark,
                )),
          ),
        ),
      );
    }

    return Row(
      children: [
        btn(context.t('yes'), true, AppTheme.success),
        const SizedBox(width: 10),
        btn(context.t('no'), false, AppTheme.danger),
      ],
    );
  }
}

/// A row of single-select chips for short option lists.
class OptionChips extends StatelessWidget {
  final List<String> options;
  final String? value;
  final ValueChanged<String> onChanged;
  const OptionChips({
    super.key,
    required this.options,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: options
          .map((o) => ChoiceChip(
                label: Text(o),
                selected: value == o,
                onSelected: (_) => onChanged(o),
              ))
          .toList(),
    );
  }
}

void showSnack(BuildContext context, String message, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? AppTheme.danger : AppTheme.textDark,
        behavior: SnackBarBehavior.floating,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
}
