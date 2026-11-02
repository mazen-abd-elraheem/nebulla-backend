import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();

  bool _loading = false;
  bool _biometricLoading = false;
  bool _rememberMe = true;
  bool _obscurePassword = true;

  final ImagePicker _picker = ImagePicker();

  @override
  void initState() {
    super.initState();
    _loadSavedPreferences();
  }

  void _loadSavedPreferences() {
    final savedEmail = StorageService.instance.getSavedEmail();
    final remember = StorageService.instance.getRememberMe();
    setState(() {
      _rememberMe = remember;
      if (savedEmail != null && savedEmail.isNotEmpty) {
        _emailCtrl.text = savedEmail;
      }
    });
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);

    try {
      final user = await NebulaRepository.instance.login(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
        rememberMe: _rememberMe,
      );

      if (!mounted) return;
      showSuccessSnackbar(
        context,
        'تم تسجيل الدخول بنجاح. أهلاً بك يا ${user.fullName}',
      );

      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const MainShell()),
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'فشل تسجيل الدخول: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loginWithBiometrics() async {
    final email = _emailCtrl.text.trim();
    if (email.isEmpty) {
      showErrorSnackbar(
        context,
        'يرجى إدخال البريد الإلكتروني أولاً للتحقق من بصمة الوجه.',
      );
      return;
    }

    try {
      final XFile? photo = await _picker.pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.front,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 90,
      );

      if (photo == null) return; // User cancelled camera

      setState(() => _biometricLoading = true);

      if (!mounted) return;
      _showScanningFeedbackDialog();

      final user = await NebulaRepository.instance.loginBiometric(
        email: email,
        faceImage: File(photo.path),
      );

      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); // dismiss scanning dialog

      showSuccessSnackbar(
        context,
        'تم التحقق البيومتري بنجاح! مرحباً ${user.fullName}',
      );

      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const MainShell()),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); // dismiss scanning dialog if open
      showErrorSnackbar(context, 'فشل التحقق البيومتري: $e');
    } finally {
      if (mounted) setState(() => _biometricLoading = false);
    }
  }

  void _showScanningFeedbackDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => Center(
        child: Container(
          width: 280,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 26),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(22),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF0F172A).withValues(alpha: 0.12),
                blurRadius: 32,
                offset: const Offset(0, 16),
              ),
              BoxShadow(
                color: const Color(0xFF00C7E5).withValues(alpha: 0.18),
                blurRadius: 40,
                offset: const Offset(0, 20),
              ),
            ],
          ),
          child: Material(
            color: Colors.transparent,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: const Color(0xFFE0F7FA),
                        border: Border.all(
                          color: const Color(0xFF00C7E5).withValues(alpha: 0.4),
                          width: 2,
                        ),
                      ),
                      child: const Icon(
                        Icons.filter_center_focus_rounded,
                        color: Color(0xFF00A3C4),
                        size: 32,
                      ),
                    ),
                    const SizedBox(
                      width: 74,
                      height: 74,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.2,
                        color: Color(0xFF00C7E5),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                const Text(
                  'جاري التحقق من بصمة الوجه',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'مطابقة الملامح عبر شبكة Neural Face ID...',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: Color(0xFF64748B),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _openForgotPasswordSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _ForgotPasswordSheet(initialEmail: _emailCtrl.text),
    );
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
              // 1. High-key Cyborg Face Background Asset (Upper-Right Profile)
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
                            const SizedBox(height: 52),

                            // Small Glowing Cyan Capsule Indicator above Title
                            Align(
                              alignment: Alignment.centerRight,
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 10,
                                  vertical: 4,
                                ),
                                decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.85),
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                    color: const Color(0xFFE2E8F0),
                                  ),
                                  boxShadow: [
                                    BoxShadow(
                                      color: const Color(0xFF00C7E5)
                                          .withValues(alpha: 0.15),
                                      blurRadius: 10,
                                    ),
                                  ],
                                ),
                                child: Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: const Color(0xFF00C7E5),
                                    boxShadow: [
                                      BoxShadow(
                                        color: const Color(0xFF00C7E5)
                                            .withValues(alpha: 0.7),
                                        blurRadius: 6,
                                        spreadRadius: 1,
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),

                            const SizedBox(height: 8),

                            // Header Section: Title & Subtitle matching Mockup
                            const Text(
                              'تسجيل الدخول',
                              textAlign: TextAlign.right,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 30,
                                fontWeight: FontWeight.w900,
                                color: Color(0xFF0F172A),
                                letterSpacing: 0.2,
                                height: 1.25,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              'مرحباً بك مجددًا، سجّل الدخول للمتابعة إلى نظامك',
                              textAlign: TextAlign.right,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: Color(0xFF64748B),
                                height: 1.35,
                              ),
                            ),

                            const SizedBox(height: 24),

                            // Floating Neo-Glass Form Card
                            _buildLoginFormCard(),

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

  /// Elevated Form Card exactly as depicted in mockup
  Widget _buildLoginFormCard() {
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
            // 1. Email or Identifier Label
            const Align(
              alignment: Alignment.centerRight,
              child: Text(
                'البريد الإلكتروني أو المعرّف',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF334155),
                ),
              ),
            ),
            const SizedBox(height: 6),

            // Email Input Field
            TextFormField(
              controller: _emailCtrl,
              keyboardType: TextInputType.emailAddress,
              textDirection: TextDirection.ltr,
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
                hintText: 'usr@synthcore.ai / ID-094',
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
                suffixIcon: const Icon(
                  Icons.person_outline_rounded,
                  size: 19,
                  color: Color(0xFF94A3B8),
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFF00C7E5), width: 1.6),
                ),
                errorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFEF4444), width: 1.2),
                ),
                focusedErrorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFEF4444), width: 1.6),
                ),
              ),
              validator: (v) {
                if (v == null || v.trim().isEmpty) {
                  return 'يرجى إدخال البريد الإلكتروني أو المعرّف';
                }
                return null;
              },
            ),

            const SizedBox(height: 16),

            // 2. Password Label
            const Align(
              alignment: Alignment.centerRight,
              child: Text(
                'كلمة المرور',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF334155),
                ),
              ),
            ),
            const SizedBox(height: 6),

            // Password Input Field
            TextFormField(
              controller: _passwordCtrl,
              obscureText: _obscurePassword,
              textDirection: TextDirection.ltr,
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
                hintText: '••••••••••••',
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
                prefixIcon: IconButton(
                  icon: Icon(
                    _obscurePassword
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                    size: 19,
                    color: const Color(0xFF94A3B8),
                  ),
                  onPressed: () {
                    setState(() => _obscurePassword = !_obscurePassword);
                  },
                ),
                suffixIcon: const Icon(
                  Icons.lock_outline_rounded,
                  size: 19,
                  color: Color(0xFF94A3B8),
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFF00C7E5), width: 1.6),
                ),
                errorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFEF4444), width: 1.2),
                ),
                focusedErrorBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide:
                      const BorderSide(color: Color(0xFFEF4444), width: 1.6),
                ),
              ),
              validator: (v) {
                if (v == null || v.isEmpty) {
                  return 'يرجى إدخال كلمة المرور';
                }
                return null;
              },
            ),

            const SizedBox(height: 12),

            // 3. Remember Me Checkbox & Forgot Password Row
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // Right (RTL): Remember Me Checkbox
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 22,
                      height: 22,
                      child: Checkbox(
                        value: _rememberMe,
                        onChanged: (val) {
                          setState(() => _rememberMe = val ?? false);
                        },
                        activeColor: const Color(0xFF0C1322),
                        checkColor: const Color(0xFF00E5FF),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(5),
                        ),
                        side: const BorderSide(
                          color: Color(0xFFCBD5E1),
                          width: 1.4,
                        ),
                      ),
                    ),
                    const SizedBox(width: 7),
                    const Text(
                      'تذكّرني على هذا الجهاز',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF475569),
                      ),
                    ),
                  ],
                ),

                // Left (RTL): Forgot Password Link
                GestureDetector(
                  onTap: _openForgotPasswordSheet,
                  behavior: HitTestBehavior.opaque,
                  child: const Text(
                    'نسيت كلمة المرور؟',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF00A3C4), // Cyan link from mockup
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            // 4. Primary Dark Submit Button: "تسجيل الدخول ←"
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: _loading ? null : _login,
                borderRadius: BorderRadius.circular(16),
                child: Ink(
                  height: 52,
                  decoration: BoxDecoration(
                    color: const Color(0xFF0C1322), // Sleek obsidian navy from mockup
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
                                color: Color(0xFF00E5FF), // Cyan glowing arrow
                                size: 19,
                              ),
                              SizedBox(width: 8),
                              Text(
                                'تسجيل الدخول',
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
            ),

            const SizedBox(height: 12),

            // 5. Secondary Biometric Button: "تسجيل الدخول عبر التعرّف البيومتري (Neural Face ID)"
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: _biometricLoading ? null : _loginWithBiometrics,
                borderRadius: BorderRadius.circular(16),
                child: Ink(
                  height: 50,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: const Color(0xFFE2E8F0),
                      width: 1.2,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF0F172A).withValues(alpha: 0.03),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Center(
                    child: _biometricLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.0,
                              color: Color(0xFF00A3C4),
                            ),
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                'تسجيل الدخول عبر التعرّف البيومتري (Neural Face ID)',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                  color: const Color(0xFF334155),
                                ),
                              ),
                              const SizedBox(width: 8),
                              const Icon(
                                Icons.filter_center_focus_rounded,
                                color: Color(0xFF00A3C4),
                                size: 18,
                              ),
                            ],
                          ),
                  ),
                ),
              ),
            ),

            const SizedBox(height: 18),

            // 6. Footer: "ليس لديك حساب؟ إنشاء حساب جديد"
            GestureDetector(
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const RegisterScreen()),
                );
              },
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
                      TextSpan(text: 'ليس لديك حساب؟ '),
                      TextSpan(
                        text: 'إنشاء حساب جديد',
                        style: TextStyle(
                          color: Color(0xFF00A3C4),
                          fontWeight: FontWeight.w800,
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
    );
  }
}

/// Password recovery modal bottom sheet
class _ForgotPasswordSheet extends StatefulWidget {
  final String initialEmail;
  const _ForgotPasswordSheet({required this.initialEmail});

  @override
  State<_ForgotPasswordSheet> createState() => _ForgotPasswordSheetState();
}

class _ForgotPasswordSheetState extends State<_ForgotPasswordSheet> {
  final _emailCtrl = TextEditingController();
  final _tokenCtrl = TextEditingController();
  final _newPasswordCtrl = TextEditingController();
  final _confirmPasswordCtrl = TextEditingController();

  bool _loading = false;
  int _step = 1; // 1: request token, 2: reset password

  @override
  void initState() {
    super.initState();
    _emailCtrl.text = widget.initialEmail;
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _tokenCtrl.dispose();
    _newPasswordCtrl.dispose();
    _confirmPasswordCtrl.dispose();
    super.dispose();
  }

  Future<void> _requestReset() async {
    final email = _emailCtrl.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      showErrorSnackbar(context, 'يرجى إدخال بريد إلكتروني صالح.');
      return;
    }

    setState(() => _loading = true);
    try {
      final msg = await NebulaRepository.instance.forgotPassword(email);
      if (!mounted) return;
      showSuccessSnackbar(context, msg);
      setState(() => _step = 2);
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'فشل طلب الاستعادة: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _confirmReset() async {
    final token = _tokenCtrl.text.trim();
    final newPassword = _newPasswordCtrl.text;
    final confirmPassword = _confirmPasswordCtrl.text;

    if (token.isEmpty) {
      showErrorSnackbar(context, 'يرجى إدخال رمز الاستعادة.');
      return;
    }
    if (newPassword.length < 8) {
      showErrorSnackbar(context, 'كلمة المرور يجب ألا تقل عن 8 خانات.');
      return;
    }
    if (newPassword != confirmPassword) {
      showErrorSnackbar(context, 'كلمتا المرور غير متطابقتين.');
      return;
    }

    setState(() => _loading = true);
    try {
      final msg = await NebulaRepository.instance.resetPassword(
        token: token,
        newPassword: newPassword,
        confirmPassword: confirmPassword,
      );
      if (!mounted) return;
      showSuccessSnackbar(context, msg);
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'فشل تعيين كلمة المرور: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        top: 24,
        left: 24,
        right: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 44,
                height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFFE2E8F0),
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              _step == 1 ? 'استعادة كلمة المرور' : 'تعيين كلمة المرور الجديدة',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 18,
                fontWeight: FontWeight.w800,
                color: Color(0xFF0F172A),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              _step == 1
                  ? 'أدخل بريدك الإلكتروني المسجل لإرسال رمز الاستعادة.'
                  : 'أدخل رمز الاستعادة وكلمة المرور الجديدة لإتمام العملية.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 12.5,
                color: Color(0xFF64748B),
              ),
            ),
            const SizedBox(height: 20),
            if (_step == 1) ...[
              _buildModalInput(
                controller: _emailCtrl,
                hint: 'البريد الإلكتروني',
                icon: Icons.mail_outline_rounded,
                isLtr: true,
              ),
              const SizedBox(height: 18),
              _buildModalButton(
                title: 'إرسال رمز الاستعادة',
                onTap: _requestReset,
              ),
            ] else ...[
              _buildModalInput(
                controller: _tokenCtrl,
                hint: 'رمز الاستعادة (Token)',
                icon: Icons.key_outlined,
                isLtr: true,
              ),
              const SizedBox(height: 12),
              _buildModalInput(
                controller: _newPasswordCtrl,
                hint: 'كلمة المرور الجديدة',
                icon: Icons.lock_outline_rounded,
                obscure: true,
              ),
              const SizedBox(height: 12),
              _buildModalInput(
                controller: _confirmPasswordCtrl,
                hint: 'تأكيد كلمة المرور الجديدة',
                icon: Icons.lock_outline_rounded,
                obscure: true,
              ),
              const SizedBox(height: 18),
              _buildModalButton(
                title: 'تأكيد كلمة المرور',
                onTap: _confirmReset,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildModalInput({
    required TextEditingController controller,
    required String hint,
    required IconData icon,
    bool isLtr = false,
    bool obscure = false,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      textDirection: isLtr ? TextDirection.ltr : TextDirection.rtl,
      textAlign: isLtr ? TextAlign.left : TextAlign.right,
      style: const TextStyle(
        fontFamily: 'Cairo',
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0F172A),
      ),
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: const Color(0xFFF8FAFC),
        hintText: hint,
        hintStyle: const TextStyle(
          fontFamily: 'Cairo',
          fontSize: 13,
          color: Color(0xFF94A3B8),
        ),
        prefixIcon: Icon(icon, size: 18, color: const Color(0xFF00A3C4)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF00C7E5), width: 1.5),
        ),
      ),
    );
  }

  Widget _buildModalButton({required String title, required VoidCallback onTap}) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _loading ? null : onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          height: 48,
          decoration: BoxDecoration(
            color: const Color(0xFF0C1322),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Center(
            child: _loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.2,
                      color: Colors.white,
                    ),
                  )
                : Text(
                    title,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}
