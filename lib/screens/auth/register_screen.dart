import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../services/api_client.dart';
import '../../services/location_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/common.dart';
import '../dashboard_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _upiAddress = TextEditingController();
  final _upiName = TextEditingController();

  bool _submitting = false;
  bool _differentUpiName = false;
  bool _locationReady = false;

  @override
  void initState() {
    super.initState();
    _checkLocation();
  }

  Future<void> _checkLocation() async {
    final loc = context.read<LocationService>();
    final ok = await loc.ensurePermission();
    if (mounted) setState(() => _locationReady = ok);
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _upiAddress.dispose();
    _upiName.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    setState(() => _submitting = true);
    try {
      await context.read<AuthProvider>().register(
            name: _name.text.trim(),
            email: _email.text.trim(),
            password: _password.text,
            upiAddress: _upiAddress.text.trim(),
            upiName: _differentUpiName ? _upiName.text.trim() : null,
          );
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
        (_) => false,
      );
    } on ApiException catch (e) {
      if (mounted) showSnack(context, e.message, error: true);
    } catch (_) {
      if (mounted) {
        showSnack(context, 'Could not register. Check your connection.',
            error: true);
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Registration')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
          child: Form(
            key: _form,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Create your collector account',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Your sign-up location is recorded for verification.',
                  style: TextStyle(color: AppTheme.textMuted),
                ),
                const SizedBox(height: 18),
                if (!_locationReady) ...[
                  LocationBanner(onEnable: _checkLocation),
                  const SizedBox(height: 16),
                ],
                _field(
                  controller: _name,
                  label: 'Full name',
                  icon: Icons.person_outline,
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Enter your name' : null,
                ),
                const SizedBox(height: 14),
                _field(
                  controller: _email,
                  label: 'Email',
                  icon: Icons.mail_outline,
                  keyboardType: TextInputType.emailAddress,
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) return 'Enter your email';
                    if (!v.contains('@') || !v.contains('.')) {
                      return 'Enter a valid email';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 14),
                _field(
                  controller: _password,
                  label: 'Password',
                  icon: Icons.lock_outline,
                  obscure: true,
                  validator: (v) => (v == null || v.length < 6)
                      ? 'At least 6 characters'
                      : null,
                ),
                const SizedBox(height: 14),
                _field(
                  controller: _upiAddress,
                  label: 'UPI ID (e.g. name@bank)',
                  icon: Icons.account_balance_wallet_outlined,
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? 'Enter your UPI ID'
                      : null,
                ),
                const SizedBox(height: 6),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  value: _differentUpiName,
                  onChanged: (v) =>
                      setState(() => _differentUpiName = v ?? false),
                  title: const Text(
                    'UPI account name is different from my name',
                    style: TextStyle(fontSize: 14),
                  ),
                ),
                if (_differentUpiName) ...[
                  const SizedBox(height: 4),
                  _field(
                    controller: _upiName,
                    label: 'UPI account holder name',
                    icon: Icons.badge_outlined,
                    validator: (v) => _differentUpiName &&
                            (v == null || v.trim().isEmpty)
                        ? 'Enter the UPI account name'
                        : null,
                  ),
                ],
                const SizedBox(height: 26),
                ElevatedButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2.4),
                        )
                      : const Text('Register'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    bool obscure = false,
    TextInputType? keyboardType,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboardType,
      validator: validator,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon),
      ),
    );
  }
}
