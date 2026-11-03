import 'package:flutter/material.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';

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
      showErrorSnackbar(context, 'كلمة المرور وتأكيد كلمة المرور غير متطابقين.');
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
        'مرحباً بك يا ${user.fullName}! تم إنشاء الحساب بنجاح.',
      );

      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const MainShell()),
        (route) => false,
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'فشل إنشاء الحساب: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final size = mediaQuery.size;
    final isDesktop = size.width > 480;

    return Scaffold(
      backgroundColor: const Color(0xFFF1F5F9), // Slate 100 outer backing
      body: Center(
        child: Container(
          width: isDesktop ? 390 : double.infinity,
          height: isDesktop ? 844 : double.infinity,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(isDesktop ? 38 : 0),
            boxShadow: isDesktop
                ? [
                    BoxShadow(
                      color: const Color(0xFF0F172A).withValues(alpha: 0.07),
                      blurRadius: 36,
                      offset: const Offset(0, 18),
                    ),
                    BoxShadow(
                      color: const Color(0xFF0EA5E9).withValues(alpha: 0.1),
                      blurRadius: 60,
                      offset: const Offset(0, 26),
                      spreadRadius: -4,
                    ),
                  ]
                : null,
          ),
          clipBehavior: Clip.antiAlias,
          child: Stack(
            children: [
              // 1. High-key Cyborg Face Background Asset
              Positioned(
                top: 0,
                right: 0,
                left: 0,
                height: isDesktop ? 480 : size.height * 0.58,
                child: Image.asset(
                  'assets/images/cyborg_bg.jpg',
                  fit: BoxFit.cover,
                  alignment: const Alignment(0.4, -0.2),
                ),
              ),

              // 2. High-key Artistic Gradient Overlay Masks (Taste & Neo-Minimalism)
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.white.withValues(alpha: 0.08),
                        Colors.white.withValues(alpha: 0.35),
                        Colors.white.withValues(alpha: 0.88),
                        Colors.white,
                      ],
                      stops: const [0.0, 0.32, 0.58, 0.82],
                    ),
                  ),
                ),
              ),

              // 3. Subtle Horizontal Softening Glow
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: [
                        Colors.white.withValues(alpha: 0.80),
                        Colors.white.withValues(alpha: 0.15),
                      ],
                      stops: const [0.0, 0.70],
                    ),
                  ),
                ),
              ),

              // 4. Main Scrollable Content
              SafeArea(
                child: Column(
                  children: [
                    // Mockup Status Bar Simulation
                    _buildMockupStatusBar(),

                    Expanded(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 24,
                          vertical: 8,
                        ),
                        physics: const BouncingScrollPhysics(),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const SizedBox(height: 36),

                            // Header Section: Title
                            const Text(
                              'إنشاء حساب جديد',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 28,
                                fontWeight: FontWeight.w900,
                                color: Color(0xFF0F172A), // Deep Slate/Navy 900
                                letterSpacing: 0.2,
                                height: 1.25,
                              ),
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              'انضم إلى شبكة نيبولا للذكاء الاصطناعي المركزي',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: Color(0xFF64748B),
                              ),
                            ),

                            const SizedBox(height: 28),

                            // Floating Neo-Glass Form Card
                            _buildRegisterCard(),

                            const SizedBox(height: 20),

                            // Bottom Home Indicator Bar
                            Center(
                              child: Container(
                                width: 134,
                                height: 4.5,
                                decoration: BoxDecoration(
                                  color: const Color(0xFFCBD5E1),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                              ),
                            ),
                            const SizedBox(height: 12),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Mobile status bar matching mockup (09:41, cyan glowing dot, signals)
  Widget _buildMockupStatusBar() {
    return Padding(
      padding: const EdgeInsets.only(left: 20, right: 20, top: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Left signal & battery glyphs
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 9,
                height: 9,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color(0xFF64748B),
                ),
              ),
              const SizedBox(width: 5),
              const Icon(
                Icons.wifi_rounded,
                size: 14,
                color: Color(0xFF64748B),
              ),
              const SizedBox(width: 5),
              const Icon(
                Icons.battery_5_bar_rounded,
                size: 15,
                color: Color(0xFF64748B),
              ),
            ],
          ),

          // Right time with cyan accent dot
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF00C7E5),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF00C7E5).withValues(alpha: 0.6),
                      blurRadius: 6,
                      spreadRadius: 1,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                '09:41',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF475569),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Floating card matching mockup
  Widget _buildRegisterCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(26),
        border: Border.all(
          color: const Color(0xFFF1F5F9),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.05),
            blurRadius: 28,
            offset: const Offset(0, 14),
          ),
          BoxShadow(
            color: const Color(0xFF0EA5E9).withValues(alpha: 0.07),
            blurRadius: 40,
            offset: const Offset(0, 20),
            spreadRadius: -4,
          ),
        ],
      ),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. Full Name Field
            _buildFieldHeader(
              title: 'الاسم الكامل',
              icon: Icons.person_outline_rounded,
            ),
            const SizedBox(height: 6),
            _buildInputField(
              controller: _fullNameCtrl,
              hint: 'usr@synthcore.ai / ID-094',
              trailingIcon: Icons.person_outline_rounded,
              validator: (v) {
                if (v == null || v.trim().length < 2) {
                  return 'يرجى إدخال الاسم الكامل (حرفين على الأقل)';
                }
                return null;
              },
            ),

            const SizedBox(height: 14),

            // 2. Email Field
            _buildFieldHeader(
              title: 'البريد الإلكتروني',
              icon: Icons.mail_outline_rounded,
            ),
            const SizedBox(height: 6),
            _buildInputField(
              controller: _emailCtrl,
              hint: 'user@synthcore.ai',
              keyboardType: TextInputType.emailAddress,
              validator: (v) {
                if (v == null || v.trim().isEmpty) {
                  return 'يرجى إدخال البريد الإلكتروني';
                }
                if (!v.contains('@') || !v.contains('.')) {
                  return 'البريد الإلكتروني غير صالح';
                }
                return null;
              },
            ),

            const SizedBox(height: 14),

            // 3. Password Field
            _buildFieldHeader(
              title: 'كلمة المرور',
              icon: Icons.shield_outlined,
            ),
            const SizedBox(height: 6),
            _buildInputField(
              controller: _passwordCtrl,
              hint: '••••••••••••',
              obscureText: _obscurePassword,
              onToggleVisibility: () {
                setState(() => _obscurePassword = !_obscurePassword);
              },
              validator: (v) {
                if (v == null || v.length < 8) {
                  return 'كلمة المرور يجب ألا تقل عن 8 خانات';
                }
                return null;
              },
            ),

            const SizedBox(height: 14),

            // 4. Confirm Password Field
            _buildFieldHeader(
              title: 'تأكيد كلمة المرور',
              icon: Icons.lock_outline_rounded,
            ),
            const SizedBox(height: 6),
            _buildInputField(
              controller: _confirmPasswordCtrl,
              hint: '••••••••••••',
              obscureText: _obscureConfirmPassword,
              onToggleVisibility: () {
                setState(
                    () => _obscureConfirmPassword = !_obscureConfirmPassword);
              },
              validator: (v) {
                if (v == null || v.isEmpty) {
                  return 'يرجى تأكيد كلمة المرور';
                }
                if (v != _passwordCtrl.text) {
                  return 'كلمتا المرور غير متطابقتين';
                }
                return null;
              },
            ),

            const SizedBox(height: 22),

            // 5. Submit Button (Dark Navy Pill with Left Arrow)
            _buildSubmitButton(),

            const SizedBox(height: 18),

            // 6. Footer Link back to Login
            _buildFooterLink(),
          ],
        ),
      ),
    );
  }

  /// Field header with label and cyan icon matching mockup
  Widget _buildFieldHeader({required String title, required IconData icon}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: Color(0xFF334155),
          ),
        ),
        const SizedBox(width: 6),
        Icon(
          icon,
          size: 16,
          color: const Color(0xFF00A3C4), // Cyan accent
        ),
      ],
    );
  }

  /// Text Input Field styled to match the mockup
  Widget _buildInputField({
    required TextEditingController controller,
    required String hint,
    IconData? trailingIcon,
    bool obscureText = false,
    VoidCallback? onToggleVisibility,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      keyboardType: keyboardType,
      textDirection: TextDirection.rtl,
      textAlign: TextAlign.right,
      style: const TextStyle(
        fontFamily: 'Cairo',
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0F172A),
      ),
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: Colors.white,
        hintText: hint,
        hintTextDirection: TextDirection.ltr,
        hintStyle: const TextStyle(
          fontFamily: 'Cairo',
          fontSize: 13,
          color: Color(0xFF94A3B8),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 13,
        ),
        prefixIcon: onToggleVisibility != null
            ? IconButton(
                icon: Icon(
                  obscureText
                      ? Icons.visibility_off_outlined
                      : Icons.visibility_outlined,
                  size: 19,
                  color: const Color(0xFF94A3B8),
                ),
                onPressed: onToggleVisibility,
              )
            : null,
        suffixIcon: trailingIcon != null
            ? Icon(
                trailingIcon,
                size: 18,
                color: const Color(0xFF94A3B8),
              )
            : null,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFF00C7E5), width: 1.6),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFEF4444), width: 1.2),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFEF4444), width: 1.6),
        ),
      ),
      validator: validator,
    );
  }

  /// Dark Obsidian Pill button with cyan arrow matching mockup
  Widget _buildSubmitButton() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _loading ? null : _submitRegister,
        borderRadius: BorderRadius.circular(16),
        child: Ink(
          height: 52,
          decoration: BoxDecoration(
            color: const Color(0xFF0C1322), // Sleek deep navy/black from mockup
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF0C1322).withValues(alpha: 0.3),
                blurRadius: 16,
                offset: const Offset(0, 6),
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
                        color: Color(0xFF00E5FF), // Glowing cyan arrow
                        size: 19,
                      ),
                      SizedBox(width: 8),
                      Text(
                        'إنشاء الحساب',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }

  /// Footer back to login link matching mockup
  Widget _buildFooterLink() {
    return GestureDetector(
      onTap: () => Navigator.of(context).pop(),
      behavior: HitTestBehavior.opaque,
      child: Center(
        child: RichText(
          textAlign: TextAlign.center,
          text: const TextSpan(
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              color: Color(0xFF64748B),
            ),
            children: [
              TextSpan(text: 'لديك حساب مفعل بالفعل؟ '),
              TextSpan(
                text: 'تسجيل الدخول ›',
                style: TextStyle(
                  color: Color(0xFF00A3C4), // Cyan link
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
