import 'package:flutter/material.dart';

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
          'UsmleWise',
          style: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w800,
            color: color,
            letterSpacing: -0.5,
          ),
        ),
        Text(
          'CRIST',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            letterSpacing: 6,
            color: light ? Colors.white70 : AppTheme.accent,
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
          const Expanded(
            child: Text(
              'Location is off. Turn it on so collections are geo-tagged.',
              style: TextStyle(fontSize: 13, color: AppTheme.textDark),
            ),
          ),
          TextButton(onPressed: onEnable, child: const Text('Enable')),
        ],
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
        btn('Yes', true, AppTheme.success),
        const SizedBox(width: 10),
        btn('No', false, AppTheme.danger),
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
