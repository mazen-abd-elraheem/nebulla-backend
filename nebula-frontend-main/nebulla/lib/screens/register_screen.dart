import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'login_screen.dart';
import 'onboarding_wizard_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _fullNameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _confirmPasswordCtrl = TextEditingController();

  bool _loading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  @override
  void dispose() {
    _fullNameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmPasswordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submitRegister() async {
    if (!_formKey.currentState!.validate()) return;

    final fullName = _fullNameCtrl.text.trim();
    final email = _emailCtrl.text.trim().toLowerCase();
    final password = _passwordCtrl.text;
    final confirmPassword = _confirmPasswordCtrl.text;

    if (password != confirmPassword) {
      showErrorSnackbar(context, 'الباسورد وتأكيده مش متطابقين خالص.');
      return;
    }

    setState(() => _loading = true);

    try {
      final user = await NebulaRepository.instance.register(
        fullName: fullName,
        email: email,
        password: password,
        confirmPassword: confirmPassword,
      );

      if (!mounted) return;
      showSuccessSnackbar(
        context,
        'نورت نيبولا يا ${user.fullName}! حسابك اتعمل بنجاح.',
      );

      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const OnboardingWizardScreen()),
        (route) => false,
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'معرفناش نعمل الحساب: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: Directionality(
        textDirection: TextDirection.rtl,
        child: Stack(
          children: [
            // 1. High-key Cyborg Face Background in Upper Area matching Mockup
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              height: 480,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.asset(
                    'assets/images/cyborg_bg.jpg',
                    fit: BoxFit.cover,
                    alignment: Alignment.topCenter,
                  ),
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Colors.white.withValues(alpha: 0.1),
                          Colors.white.withValues(alpha: 0.85),
                          Colors.white,
                        ],
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // 2. Cyan Indicator Dot at the very top right
            SafeArea(
              child: Align(
                alignment: Alignment.topRight,
                child: Padding(
                  padding: const EdgeInsets.only(top: 14, right: 28),
                  child: Container(
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      color: const Color(0xFF00E5FF),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF00E5FF).withValues(alpha: 0.7),
                          blurRadius: 8,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),

            // 3. Scrollable Form Content
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 80),

                        // Title Header matching Mockup Image 1
                        const Text(
                          'إنشاء حساب جديد',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 27,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF0F172A),
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 18),

                        // Frosted Glass Form Card
                        ClipRRect(
                          borderRadius: BorderRadius.circular(26),
                          child: BackdropFilter(
                            filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
                            child: Container(
                              padding: const EdgeInsets.all(22),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.92),
                                borderRadius: BorderRadius.circular(26),
                                border: Border.all(
                                  color: Colors.white,
                                  width: 1.5,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.05),
                                    blurRadius: 28,
                                    offset: const Offset(0, 8),
                                  ),
                                ],
                              ),
                              child: Form(
                                key: _formKey,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    // 1. Full Name (الاسم الكامل)
                                    _buildFieldLabel(
                                      title: 'الاسم الكامل',
                                      icon: Icons.person_outline_rounded,
                                    ),
                                    const SizedBox(height: 7),
                                    TextFormField(
                                      controller: _fullNameCtrl,
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 13.5,
                                        color: Color(0xFF1E293B),
                                      ),
                                      decoration: _buildInputDecoration(
                                        hintText: 'usr@synthcore.ai / ID-094',
                                        suffixIcon: Icons.person_outline_rounded,
                                      ),
                                      validator: (v) {
                                        if (v == null || v.trim().isEmpty) {
                                          return 'يرجى إدخال الاسم الكامل';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 16),

                                    // 2. Email (البريد الإلكتروني)
                                    _buildFieldLabel(
                                      title: 'البريد الإلكتروني',
                                      icon: Icons.mail_outline_rounded,
                                    ),
                                    const SizedBox(height: 7),
                                    TextFormField(
                                      controller: _emailCtrl,
                                      keyboardType: TextInputType.emailAddress,
                                      textDirection: TextDirection.ltr,
                                      textAlign: TextAlign.right,
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 13.5,
                                        color: Color(0xFF1E293B),
                                      ),
                                      decoration: _buildInputDecoration(
                                        hintText: 'usr@synthcore.ai',
                                      ),
                                      validator: (v) {
                                        if (v == null || v.trim().isEmpty) {
                                          return 'يرجى إدخال البريد الإلكتروني';
                                        }
                                        if (!v.contains('@')) {
                                          return 'يرجى إدخال بريد إلكتروني صحيح';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 16),

                                    // 3. Password (كلمة المرور)
                                    _buildFieldLabel(
                                      title: 'كلمة المرور',
                                      icon: Icons.shield_outlined,
                                    ),
                                    const SizedBox(height: 7),
                                    TextFormField(
                                      controller: _passwordCtrl,
                                      obscureText: _obscurePassword,
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 13.5,
                                        color: Color(0xFF1E293B),
                                      ),
                                      decoration: _buildInputDecoration(
                                        hintText: '•••••••••••••',
                                        isPassword: true,
                                        obscure: _obscurePassword,
                                        onToggleObscure: () {
                                          setState(() => _obscurePassword = !_obscurePassword);
                                        },
                                      ),
                                      validator: (v) {
                                        if (v == null || v.length < 6) {
                                          return 'يجب أن تكون كلمة المرور 6 أحرف على الأقل';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 16),

                                    // 4. Confirm Password (تأكيد كلمة المرور)
                                    _buildFieldLabel(
                                      title: 'تأكيد كلمة المرور',
                                      icon: Icons.lock_outline_rounded,
                                    ),
                                    const SizedBox(height: 7),
                                    TextFormField(
                                      controller: _confirmPasswordCtrl,
                                      obscureText: _obscureConfirmPassword,
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 13.5,
                                        color: Color(0xFF1E293B),
                                      ),
                                      decoration: _buildInputDecoration(
                                        hintText: '•••••••••••••',
                                        isPassword: true,
                                        obscure: _obscureConfirmPassword,
                                        onToggleObscure: () {
                                          setState(() => _obscureConfirmPassword = !_obscureConfirmPassword);
                                        },
                                      ),
                                      validator: (v) {
                                        if (v != _passwordCtrl.text) {
                                          return 'كلمة المرور غير متطابقة';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 24),

                                    // Primary Button: Dark Navy [← إنشاء الحساب]
                                    InkWell(
                                      onTap: _loading ? null : _submitRegister,
                                      borderRadius: BorderRadius.circular(16),
                                      child: Container(
                                        height: 52,
                                        decoration: BoxDecoration(
                                          color: const Color(0xFF0B132B),
                                          borderRadius: BorderRadius.circular(16),
                                          boxShadow: [
                                            BoxShadow(
                                              color: Colors.black.withValues(alpha: 0.12),
                                              blurRadius: 16,
                                              offset: const Offset(0, 4),
                                            ),
                                          ],
                                        ),
                                        child: Center(
                                          child: _loading
                                              ? const SizedBox(
                                                  width: 22,
                                                  height: 22,
                                                  child: CircularProgressIndicator(
                                                    strokeWidth: 2.2,
                                                    color: Colors.white,
                                                  ),
                                                )
                                              : const Row(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(
                                                      Icons.arrow_back_rounded,
                                                      color: Colors.white,
                                                      size: 19,
                                                    ),
                                                    SizedBox(width: 10),
                                                    Text(
                                                      'إنشاء الحساب',
                                                      style: TextStyle(
                                                        fontFamily: 'Cairo',
                                                        fontWeight: FontWeight.bold,
                                                        fontSize: 14.5,
                                                        color: Colors.white,
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 22),

                                    // Bottom Navigation Link: Back to login
                                    Center(
                                      child: InkWell(
                                        onTap: () {
                                          if (Navigator.of(context).canPop()) {
                                            Navigator.of(context).pop();
                                          } else {
                                            Navigator.of(context).pushReplacement(
                                              MaterialPageRoute(
                                                builder: (_) => const LoginScreen(),
                                              ),
                                            );
                                          }
                                        },
                                        child: RichText(
                                          text: const TextSpan(
                                            style: TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 13,
                                            ),
                                            children: [
                                              TextSpan(
                                                text: 'لديك حساب مفعل بالفعل؟ ',
                                                style: TextStyle(color: Color(0xFF64748B)),
                                              ),
                                              TextSpan(
                                                text: 'تسجيل الدخول >',
                                                style: TextStyle(
                                                  color: Color(0xFF0284C7),
                                                  fontWeight: FontWeight.bold,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFieldLabel({required String title, required IconData icon}) {
    return Row(
      children: [
        Icon(icon, size: 16, color: const Color(0xFF0284C7)),
        const SizedBox(width: 6),
        Text(
          title,
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 12.5,
            fontWeight: FontWeight.bold,
            color: Color(0xFF334155),
          ),
        ),
      ],
    );
  }

  InputDecoration _buildInputDecoration({
    required String hintText,
    IconData? suffixIcon,
    bool isPassword = false,
    bool obscure = false,
    VoidCallback? onToggleObscure,
  }) {
    return InputDecoration(
      hintText: hintText,
      hintStyle: TextStyle(
        fontFamily: isPassword ? null : 'Cairo',
        fontSize: isPassword ? 14 : 12.5,
        letterSpacing: isPassword ? 2 : 0,
        color: const Color(0xFF94A3B8),
      ),
      filled: true,
      fillColor: const Color(0xFFF8FAFC),
      contentPadding: const EdgeInsets.symmetric(
        horizontal: 16,
        vertical: 14,
      ),
      prefixIcon: isPassword
          ? IconButton(
              icon: Icon(
                obscure ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                color: const Color(0xFF94A3B8),
                size: 20,
              ),
              onPressed: onToggleObscure,
            )
          : null,
      suffixIcon: suffixIcon != null
          ? Icon(
              suffixIcon,
              color: const Color(0xFF94A3B8),
              size: 20,
            )
          : null,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(
          color: Color(0xFFE2E8F0),
          width: 1,
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(
          color: Color(0xFFE2E8F0),
          width: 1,
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(
          color: Color(0xFF0284C7),
          width: 1.5,
        ),
      ),
    );
  }
}
