import 'dart:io';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';
import 'onboarding_wizard_screen.dart';
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
        'نورت يا ${user.fullName}! دخلت على حسابك تمام.',
      );

      final hasCloned = await NebulaRepository.instance.hasClonedVoice();
      if (!mounted) return;
      if (!hasCloned) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const OnboardingWizardScreen()),
        );
      } else {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const MainShell()),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'مش عارفين ندخلك: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loginWithBiometrics() async {
    final email = _emailCtrl.text.trim();

    try {
      XFile? photo;
      try {
        photo = await _picker.pickImage(
          source: ImageSource.camera,
          preferredCameraDevice: CameraDevice.front,
          maxWidth: 1024,
          maxHeight: 1024,
          imageQuality: 90,
        );
      } catch (camErr) {
        // Fallback to gallery / photo file on Windows Desktop if webcam is busy or unhandled
        photo = await _picker.pickImage(
          source: ImageSource.gallery,
          maxWidth: 1024,
          maxHeight: 1024,
          imageQuality: 90,
        );
      }

      // If user still has null (e.g. cancelled picker)
      if (photo == null) return;

      setState(() => _biometricLoading = true);

      if (!mounted) return;
      _showScanningFeedbackDialog();

      final user = await NebulaRepository.instance.loginBiometric(
        email: email, // Optional; backend performs 1:N neural recognition if empty
        faceImage: File(photo.path),
      );

      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop();

      showSuccessSnackbar(
        context,
        'تم التحقق عبر بصمة الوجه بنجاح! مرحباً بك يا ${user.fullName}',
      );

      final hasCloned = await NebulaRepository.instance.hasClonedVoice();
      if (!mounted) return;
      if (!hasCloned) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const OnboardingWizardScreen()),
        );
      } else {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const MainShell()),
        );
      }
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop();
      showErrorSnackbar(context, 'فشل التحقق بالوجه: $e');
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
            borderRadius: BorderRadius.circular(24),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.12),
                blurRadius: 30,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: const Material(
            color: Colors.transparent,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 44,
                  height: 44,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: Color(0xFF0072FF),
                  ),
                ),
                SizedBox(height: 18),
                Text(
                  'جاري مطابقة بصمة الوجه...',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1E293B),
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  'التحقق عبر شبكة Neural Face ID',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11.5,
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

  void _showForgotPasswordDialog() {
    final forgotEmailCtrl = TextEditingController(text: _emailCtrl.text.trim());
    showDialog(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: const Text(
            'استعادة كلمة المرور',
            style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'أدخل بريدك الإلكتروني لإرسال تعليمات إعادة تعيين كلمة المرور.',
                style: TextStyle(fontFamily: 'Cairo', fontSize: 13, color: Color(0xFF64748B)),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: forgotEmailCtrl,
                keyboardType: TextInputType.emailAddress,
                style: const TextStyle(fontFamily: 'Cairo', fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'name@example.com',
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                showSuccessSnackbar(
                  context,
                  'تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك.',
                );
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0F172A),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('إرسال', style: TextStyle(fontFamily: 'Cairo', color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  void _showServerSettingsDialog() {
    final currentUrl = StorageService.instance.getBaseUrl();
    final urlCtrl = TextEditingController(text: currentUrl);
    bool testing = false;
    String? statusMsg;
    bool statusOk = false;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) => Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            backgroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: const Row(
              children: [
                Icon(Icons.dns_rounded, color: Color(0xFF0284C7)),
                SizedBox(width: 8),
                Text(
                  'إعدادات السيرفر',
                  style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold, fontSize: 18),
                ),
              ],
            ),
            content: SizedBox(
              width: 360,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'اختر أو الصق رابط السيرفر (سواء كان محلي أو على Railway):',
                    style: TextStyle(fontFamily: 'Cairo', fontSize: 12.5, color: Color(0xFF64748B)),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      _serverPresetChip('محلي (PC)', 'http://localhost:8000', urlCtrl, setDialogState),
                      _serverPresetChip('محاكي أندرويد', 'http://10.0.2.2:8000', urlCtrl, setDialogState),
                      _serverPresetChip('شبكة محلية (LAN)', 'http://192.168.1.10:8000', urlCtrl, setDialogState),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: urlCtrl,
                    textDirection: TextDirection.ltr,
                    textAlign: TextAlign.left,
                    style: const TextStyle(fontFamily: 'Courier', fontSize: 13),
                    decoration: InputDecoration(
                      labelText: 'Server Base URL',
                      hintText: 'https://xxx.up.railway.app',
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (statusMsg != null)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: statusOk ? const Color(0xFFF0FDF4) : const Color(0xFFFEF2F2),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: statusOk ? const Color(0xFF86EFAC) : const Color(0xFFFECACA)),
                      ),
                      child: Row(
                        children: [
                          Icon(statusOk ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                              size: 16, color: statusOk ? const Color(0xFF16A34A) : const Color(0xFFDC2626)),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              statusMsg!,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11.5,
                                color: statusOk ? const Color(0xFF166534) : const Color(0xFF991B1B),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: testing
                        ? null
                        : () async {
                            setDialogState(() {
                              testing = true;
                              statusMsg = null;
                            });
                            try {
                              final testUrl = urlCtrl.text.trim().replaceAll(RegExp(r'/+$'), '');
                              final res = await http.get(Uri.parse('$testUrl/health')).timeout(const Duration(seconds: 4));
                              setDialogState(() {
                                testing = false;
                                statusOk = res.statusCode >= 200 && res.statusCode < 400;
                                statusMsg = statusOk ? 'الاتصال بالسيرفر شغال تمام!' : 'رد السيرفر بكود ${res.statusCode}';
                              });
                            } catch (e) {
                              setDialogState(() {
                                testing = false;
                                statusOk = false;
                                statusMsg = 'فشل الاتصال: $e';
                              });
                            }
                          },
                    icon: testing
                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.network_check_rounded, size: 18),
                    label: const Text('فحص الاتصال بالسيرفر', style: TextStyle(fontFamily: 'Cairo', fontSize: 12)),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
              ),
              ElevatedButton(
                onPressed: () async {
                  final newUrl = urlCtrl.text.trim().replaceAll(RegExp(r'/+$'), '');
                  if (newUrl.isNotEmpty) {
                    await StorageService.instance.setBaseUrl(newUrl);
                  }
                  if (ctx.mounted) Navigator.of(ctx).pop();
                  if (mounted && context.mounted) {
                    showSuccessSnackbar(context, 'تم ضبط عنوان السيرفر إلى: $newUrl');
                  }
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF0F172A),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('حفظ', style: TextStyle(fontFamily: 'Cairo', color: Colors.white)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _serverPresetChip(String label, String url, TextEditingController ctrl, StateSetter setDialogState) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontFamily: 'Cairo', fontSize: 11)),
      onPressed: () {
        setDialogState(() {
          ctrl.text = url;
        });
      },
      backgroundColor: const Color(0xFFF1F5F9),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: Directionality(
        textDirection: TextDirection.rtl,
        child: Stack(
          children: [
            // 1. High-key Cyborg Face Background in Upper Area
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
                  // White fade gradient at the bottom of the image
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

            // Server URL Switcher / Settings (Top Left)
            SafeArea(
              child: Align(
                alignment: Alignment.topLeft,
                child: Padding(
                  padding: const EdgeInsets.only(top: 10, left: 18),
                  child: InkWell(
                    onTap: _showServerSettingsDialog,
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.9),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.05),
                            blurRadius: 10,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.dns_rounded, size: 15, color: Color(0xFF0284C7)),
                          SizedBox(width: 5),
                          Text(
                            'السيرفر',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF334155),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),

            // 3. Main Scrollable Content
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 120),

                        // Title Header with cyan indicator pill
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'تسجيل الدخول',
                                  style: TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 27,
                                    fontWeight: FontWeight.bold,
                                    color: Color(0xFF0F172A),
                                    letterSpacing: -0.3,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                const Text(
                                  'مرحبًا بك مجددًا، سجّل الدخول للمتابعة إلى نظامك',
                                  style: TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 12.5,
                                    color: Color(0xFF64748B),
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),

                            // Small cyan status dot pill
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: const Color(0xFFE0F7FA),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Container(
                                width: 6,
                                height: 6,
                                decoration: const BoxDecoration(
                                  color: Color(0xFF00E5FF),
                                  shape: BoxShape.circle,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 20),

                        // Frosted Glass Form Card matching Mockup
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
                                    // Field 1: Email or Identifier
                                    const Text(
                                      'البريد الإلكتروني أو المعرّف',
                                      style: TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 12.5,
                                        fontWeight: FontWeight.bold,
                                        color: Color(0xFF334155),
                                      ),
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
                                      decoration: InputDecoration(
                                        hintText: 'usr@synthcore.ai / ID-094',
                                        hintStyle: const TextStyle(
                                          fontFamily: 'Cairo',
                                          fontSize: 12.5,
                                          color: Color(0xFF94A3B8),
                                        ),
                                        filled: true,
                                        fillColor: const Color(0xFFF8FAFC),
                                        contentPadding: const EdgeInsets.symmetric(
                                          horizontal: 16,
                                          vertical: 14,
                                        ),
                                        suffixIcon: const Icon(
                                          Icons.person_outline_rounded,
                                          color: Color(0xFF94A3B8),
                                          size: 20,
                                        ),
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
                                      ),
                                      validator: (v) {
                                        if (v == null || v.trim().isEmpty) {
                                          return 'يرجى إدخال البريد الإلكتروني أو المعرّف';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 18),

                                    // Field 2: Password
                                    const Text(
                                      'كلمة المرور',
                                      style: TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 12.5,
                                        fontWeight: FontWeight.bold,
                                        color: Color(0xFF334155),
                                      ),
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
                                      decoration: InputDecoration(
                                        hintText: '•••••••••••••',
                                        hintStyle: const TextStyle(
                                          fontSize: 14,
                                          letterSpacing: 2,
                                          color: Color(0xFF94A3B8),
                                        ),
                                        filled: true,
                                        fillColor: const Color(0xFFF8FAFC),
                                        contentPadding: const EdgeInsets.symmetric(
                                          horizontal: 16,
                                          vertical: 14,
                                        ),
                                        prefixIcon: IconButton(
                                          icon: Icon(
                                            _obscurePassword
                                                ? Icons.visibility_off_outlined
                                                : Icons.visibility_outlined,
                                            color: const Color(0xFF94A3B8),
                                            size: 20,
                                          ),
                                          onPressed: () {
                                            setState(() => _obscurePassword = !_obscurePassword);
                                          },
                                        ),
                                        suffixIcon: const Icon(
                                          Icons.lock_outline_rounded,
                                          color: Color(0xFF94A3B8),
                                          size: 20,
                                        ),
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
                                      ),
                                      validator: (v) {
                                        if (v == null || v.isEmpty) {
                                          return 'يرجى إدخال كلمة المرور';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 12),

                                    // Options: Remember Me & Forgot Password
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        // Remember Me
                                        InkWell(
                                          onTap: () => setState(() => _rememberMe = !_rememberMe),
                                          borderRadius: BorderRadius.circular(6),
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              SizedBox(
                                                width: 20,
                                                height: 20,
                                                child: Checkbox(
                                                  value: _rememberMe,
                                                  onChanged: (val) {
                                                    setState(() => _rememberMe = val ?? true);
                                                  },
                                                  activeColor: const Color(0xFF0284C7),
                                                  shape: RoundedRectangleBorder(
                                                    borderRadius: BorderRadius.circular(4),
                                                  ),
                                                  materialTapTargetSize:
                                                      MaterialTapTargetSize.shrinkWrap,
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              const Text(
                                                'تذكّرني على هذا الجهاز',
                                                style: TextStyle(
                                                  fontFamily: 'Cairo',
                                                  fontSize: 11.5,
                                                  color: Color(0xFF475569),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),

                                        // Forgot Password
                                        InkWell(
                                          onTap: _showForgotPasswordDialog,
                                          child: const Text(
                                            'نسيت كلمة المرور؟',
                                            style: TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 11.5,
                                              fontWeight: FontWeight.bold,
                                              color: Color(0xFF0284C7),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 22),

                                    // Primary Button: Dark Navy [← تسجيل الدخول]
                                    InkWell(
                                      onTap: _loading ? null : _login,
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
                                                      'تسجيل الدخول',
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
                                    const SizedBox(height: 12),

                                    // Secondary Button: Biometric Face ID
                                    InkWell(
                                      onTap: _biometricLoading ? null : _loginWithBiometrics,
                                      borderRadius: BorderRadius.circular(16),
                                      child: Container(
                                        height: 50,
                                        decoration: BoxDecoration(
                                          color: Colors.white.withValues(alpha: 0.8),
                                          borderRadius: BorderRadius.circular(16),
                                          border: Border.all(
                                            color: const Color(0xFFE2E8F0),
                                            width: 1.2,
                                          ),
                                        ),
                                        child: Center(
                                          child: _biometricLoading
                                              ? const SizedBox(
                                                  width: 20,
                                                  height: 20,
                                                  child: CircularProgressIndicator(
                                                    strokeWidth: 2,
                                                    color: Color(0xFF0284C7),
                                                  ),
                                                )
                                              : const Row(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Text(
                                                      'تسجيل الدخول عبر التعرّف البيومتري (Neural Face ID)',
                                                      style: TextStyle(
                                                        fontFamily: 'Cairo',
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.w600,
                                                        color: Color(0xFF334155),
                                                      ),
                                                    ),
                                                    SizedBox(width: 8),
                                                    Icon(
                                                      Icons.document_scanner_outlined,
                                                      color: Color(0xFF0284C7),
                                                      size: 18,
                                                    ),
                                                  ],
                                                ),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 22),

                                    // Bottom Navigation Link: Create new account
                                    Center(
                                      child: InkWell(
                                        onTap: () {
                                          Navigator.of(context).push(
                                            MaterialPageRoute(
                                              builder: (_) => const RegisterScreen(),
                                            ),
                                          );
                                        },
                                        child: RichText(
                                          text: const TextSpan(
                                            style: TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 13,
                                            ),
                                            children: [
                                              TextSpan(
                                                text: 'ليس لديك حساب؟ ',
                                                style: TextStyle(color: Color(0xFF64748B)),
                                              ),
                                              TextSpan(
                                                text: 'إنشاء حساب جديد',
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
}
