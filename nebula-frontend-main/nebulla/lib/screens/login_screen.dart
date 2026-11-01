import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';

/// Custom Painter that accurately renders the `@drawable/html_body_m.xml` Android vector drawable.
/// Dimensions: 390dp x 884dp viewport with exact matrix transformations,
/// linear sheen gradients, and radial Sky-500 (#0EA5E9) & Cyan-500 (#06B6D4) glows.
class HtmlBodyMPainter extends CustomPainter {
  const HtmlBodyMPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final double scaleX = size.width / 390.0;
    final double scaleY = size.height / 884.0;

    canvas.save();
    canvas.scale(scaleX, scaleY);

    final rect = const Rect.fromLTWH(0, 0, 390, 884);

    // 1. Clip path: M0 0H390V884H0V0Z
    canvas.clipRect(rect);

    // 2. Base fills: #FFFFFF and #F8FAFC
    final paintWhite = Paint()..color = const Color(0xFFFFFFFF);
    canvas.drawRect(rect, paintWhite);

    final paintSlate50 = Paint()..color = const Color(0xFFF8FAFC);
    canvas.drawRect(rect, paintSlate50);

    // 3. Group 1: Rotated 90° Linear Gradient
    // translateX="1" translateY="0" pivotX="195" pivotY="442" scaleX="2" scaleY="2" rotation="90"
    canvas.save();
    canvas.translate(1.0, 0.0);
    canvas.translate(195.0, 442.0);
    canvas.rotate(90.0 * math.pi / 180.0);
    canvas.scale(2.0, 2.0);
    canvas.translate(-195.0, -442.0);

    final linearShader1 = ui.Gradient.linear(
      const Offset(97.5, 442.0),
      const Offset(292.5, 442.0),
      const [
        Color(0x66E2E8F0),
        Color(0x00E2E8F0),
      ],
      const [0.036, 1.0],
    );
    final paintLinear1 = Paint()..shader = linearShader1;
    canvas.drawRect(rect, paintLinear1);
    canvas.restore();

    // 4. Group 2: Unrotated Linear Gradient
    // pivotX="195" pivotY="442" scaleX="2" scaleY="2"
    canvas.save();
    canvas.translate(195.0, 442.0);
    canvas.scale(2.0, 2.0);
    canvas.translate(-195.0, -442.0);

    final linearShader2 = ui.Gradient.linear(
      const Offset(97.5, 442.0),
      const Offset(292.5, 442.0),
      const [
        Color(0x66E2E8F0),
        Color(0x00E2E8F0),
      ],
      const [0.036, 1.0],
    );
    final paintLinear2 = Paint()..shader = linearShader2;
    canvas.drawRect(rect, paintLinear2);
    canvas.restore();

    // 5. Group 3: Sky Blue (#0EA5E9) Radial Glow Aura
    // translateX="-2.272" translateY="-0.102" pivotX="195" pivotY="442" scaleX="9.088" scaleY="4.009"
    canvas.save();
    canvas.translate(-2.272, -0.102);
    canvas.translate(195.0, 442.0);
    canvas.scale(9.088, 4.009);
    canvas.translate(-195.0, -442.0);

    final radialShader1 = ui.Gradient.radial(
      const Offset(195.0, 442.0),
      97.5,
      const [
        Color(0x0F0EA5E9),
        Color(0x000EA5E9),
      ],
      const [0.0, 0.4],
    );
    final paintRadial1 = Paint()..shader = radialShader1;
    canvas.drawRect(rect, paintRadial1);
    canvas.restore();

    // 6. Group 4: Cyan (#06B6D4) Radial Glow Aura
    // translateX="-1.272" translateY="-0.902" pivotX="195" pivotY="442" scaleX="9.088" scaleY="4.009"
    canvas.save();
    canvas.translate(-1.272, -0.902);
    canvas.translate(195.0, 442.0);
    canvas.scale(9.088, 4.009);
    canvas.translate(-195.0, -442.0);

    final radialShader2 = ui.Gradient.radial(
      const Offset(195.0, 442.0),
      97.5,
      const [
        Color(0x1406B6D4),
        Color(0x0006B6D4),
      ],
      const [0.0, 0.45],
    );
    final paintRadial2 = Paint()..shader = radialShader2;
    canvas.drawRect(rect, paintRadial2);
    canvas.restore();

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with TickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _codeCtrl = TextEditingController();
  final _deviceCtrl = TextEditingController();
  final _urlCtrl = TextEditingController();

  bool _loading = false;
  bool _showAdvanced = false;

  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;
  late Animation<double> _glowScaleAnim;

  @override
  void initState() {
    super.initState();
    _deviceCtrl.text = StorageService.instance.getDeviceName();
    _urlCtrl.text = StorageService.instance.getBaseUrl();

    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3200),
    )..repeat(reverse: true);

    _pulseAnim = Tween<double>(begin: 0.35, end: 1.0).animate(
      CurvedAnimation(
        parent: _pulseCtrl,
        curve: Curves.easeInOutCubic,
      ),
    );

    _glowScaleAnim = Tween<double>(begin: 0.95, end: 1.06).animate(
      CurvedAnimation(
        parent: _pulseCtrl,
        curve: Curves.easeInOutCubic,
      ),
    );
  }

  @override
  void dispose() {
    _codeCtrl.dispose();
    _deviceCtrl.dispose();
    _urlCtrl.dispose();
    _pulseCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);

    await StorageService.instance.setBaseUrl(_urlCtrl.text.trim());
    await StorageService.instance.setDeviceName(_deviceCtrl.text.trim());

    try {
      await NebulaRepository.instance.login(_codeCtrl.text.trim());
      if (!mounted) return;
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

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final screenWidth = mediaQuery.size.width;

    return Scaffold(
      backgroundColor: const Color(0xFFF1F5F9), // Slate 100 outer backing
      body: Center(
        child: Container(
          width: screenWidth > 420 ? 390 : double.infinity,
          height: screenWidth > 420 ? 884 : double.infinity,
          // Elevation 50dp: Multi-layered soft ambient drop shadows matching android:elevation="50dp"
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(screenWidth > 420 ? 36 : 0),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF0F172A).withValues(alpha: 0.05),
                blurRadius: 28,
                offset: const Offset(0, 14),
                spreadRadius: 0,
              ),
              BoxShadow(
                color: const Color(0xFF0EA5E9).withValues(alpha: 0.08),
                blurRadius: 50,
                offset: const Offset(0, 24),
                spreadRadius: -4,
              ),
              BoxShadow(
                color: const Color(0xFF06B6D4).withValues(alpha: 0.05),
                blurRadius: 80,
                offset: const Offset(0, 40),
                spreadRadius: 2,
              ),
            ],
          ),
          clipBehavior: Clip.antiAlias, // android:clipToOutline="true"
          child: Stack(
            children: [
              // 1. Android Vector Drawable Background (Exact html_body_m.xml reproduction)
              const Positioned.fill(
                child: CustomPaint(
                  painter: HtmlBodyMPainter(),
                ),
              ),

              // 2. Main Scrollable Content
              SafeArea(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const SizedBox(height: 16),

                      // Status Badge: Online & Secure
                      _buildStatusPill(),

                      const SizedBox(height: 28),

                      // Animated Nebula Orb & Hero Emblem
                      _buildAnimatedHeroEmblem(),

                      const SizedBox(height: 24),

                      // Typography: Brand Headline & Tagline
                      const Text(
                        'نيبولا',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 34,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFF0F172A), // Slate 900
                          letterSpacing: 1.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'نظام التوأم الرقمي والمساعد الشخصي',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF64748B), // Slate 500
                        ),
                      ),

                      const SizedBox(height: 32),

                      // Elevated Form Card (Light Neo-Glass aesthetic)
                      _buildLoginFormCard(),

                      const SizedBox(height: 28),

                      // Tasteful Footer with Security Indicator
                      _buildFooter(),

                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Top pill badge showing secure local connection status
  Widget _buildStatusPill() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFFE2E8F0),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0EA5E9).withValues(alpha: 0.08),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Pulsing green LED dot
          AnimatedBuilder(
            animation: _pulseAnim,
            builder: (context, child) => Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF10B981), // Emerald Green
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF10B981).withValues(alpha: _pulseAnim.value * 0.7),
                    blurRadius: 8,
                    spreadRadius: 2,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          const Text(
            'اتصال محلي آمن · v3.0',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: AppColors.slate600,
            ),
          ),
        ],
      ),
    );
  }

  /// Animated Hero Emblem with breathing concentric cosmic rings
  Widget _buildAnimatedHeroEmblem() {
    return AnimatedBuilder(
      animation: _pulseCtrl,
      builder: (context, child) {
        return Stack(
          alignment: Alignment.center,
          children: [
            // Outer atmospheric bloom
            Transform.scale(
              scale: _glowScaleAnim.value,
              child: Container(
                width: 130,
                height: 130,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF0EA5E9)
                          .withValues(alpha: _pulseAnim.value * 0.28),
                      blurRadius: 50,
                      spreadRadius: 10,
                    ),
                    BoxShadow(
                      color: const Color(0xFF06B6D4)
                          .withValues(alpha: _pulseAnim.value * 0.20),
                      blurRadius: 70,
                      spreadRadius: 15,
                    ),
                  ],
                ),
              ),
            ),

            // Middle Frosted Gradient Ring
            Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.95),
                border: Border.all(
                  color: const Color(0xFFE2E8F0),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF0EA5E9).withValues(alpha: 0.12),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: Center(
                child: Container(
                  width: 82,
                  height: 82,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        Color(0xFFE0F2FE), // Sky 100
                        Color(0xFFCFFAFE), // Cyan 100
                      ],
                    ),
                    border: Border.all(
                      color: const Color(0xFF38BDF8).withValues(alpha: 0.5),
                      width: 1.2,
                    ),
                  ),
                  child: const Icon(
                    Icons.smart_toy_outlined,
                    size: 42,
                    color: Color(0xFF0284C7), // Sky 600
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  /// Elevated Form Card with clean white glass aesthetic
  Widget _buildLoginFormCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: const Color(0xFFE2E8F0),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.04),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: const Color(0xFF0EA5E9).withValues(alpha: 0.06),
            blurRadius: 36,
            offset: const Offset(0, 18),
            spreadRadius: -4,
          ),
        ],
      ),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'تسجيل الدخول',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 19,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.lock_outline_rounded, size: 12, color: Color(0xFF0284C7)),
                      SizedBox(width: 4),
                      Text(
                        'إقران مباشر',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0284C7),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            const Text(
              'أدخل رمز الإقران المعروض على شاشة الروبوت للاتصال',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 12,
                color: Color(0xFF64748B),
                height: 1.4,
              ),
            ),

            const SizedBox(height: 22),

            // Pairing Code Input Field
            _buildCustomTextField(
              controller: _codeCtrl,
              label: 'رمز الإقران (Pairing Code)',
              hint: 'XXXX-XXXX-XXXX',
              icon: Icons.vpn_key_outlined,
              isLtr: true,
              letterSpacing: 2.5,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'الرجاء إدخال رمز الإقران'
                  : null,
            ),

            const SizedBox(height: 14),

            // Device Name Input Field
            _buildCustomTextField(
              controller: _deviceCtrl,
              label: 'اسم الجهاز (Device Name)',
              hint: 'هاتف المستخدم',
              icon: Icons.phone_android_outlined,
              isLtr: false,
              validator: (v) => (v == null || v.trim().isEmpty)
                  ? 'الرجاء إدخال اسم الجهاز'
                  : null,
            ),

            const SizedBox(height: 12),

            // Advanced Connection Settings Accordion Toggle
            GestureDetector(
              onTap: () => setState(() => _showAdvanced = !_showAdvanced),
              behavior: HitTestBehavior.opaque,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    const Text(
                      'إعدادات الاتصال المتقدمة',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0284C7), // Sky 600
                      ),
                    ),
                    const SizedBox(width: 4),
                    AnimatedRotation(
                      turns: _showAdvanced ? 0.5 : 0.0,
                      duration: const Duration(milliseconds: 250),
                      curve: Curves.easeOutCubic,
                      child: const Icon(
                        Icons.keyboard_arrow_down_rounded,
                        color: Color(0xFF0284C7),
                        size: 18,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Expandable Server URL Field
            AnimatedSize(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              child: _showAdvanced
                  ? Padding(
                      padding: const EdgeInsets.only(top: 10, bottom: 4),
                      child: _buildCustomTextField(
                        controller: _urlCtrl,
                        label: 'عنوان الخادم (Server URL)',
                        hint: 'http://192.168.1.x:8000',
                        icon: Icons.dns_outlined,
                        isLtr: true,
                      ),
                    )
                  : const SizedBox.shrink(),
            ),

            const SizedBox(height: 24),

            // Primary Action Button
            _buildSubmitButton(),
          ],
        ),
      ),
    );
  }

  /// Custom clean styled text field with refined borders and focus state
  Widget _buildCustomTextField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required IconData icon,
    bool isLtr = false,
    double? letterSpacing,
    String? Function(String?)? validator,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: Color(0xFF334155), // Slate 700
          ),
        ),
        const SizedBox(height: 6),
        TextFormField(
          controller: controller,
          textAlign: isLtr ? TextAlign.left : TextAlign.right,
          textDirection: isLtr ? TextDirection.ltr : TextDirection.rtl,
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: const Color(0xFF0F172A),
            letterSpacing: letterSpacing,
          ),
          decoration: InputDecoration(
            isDense: true,
            filled: true,
            fillColor: const Color(0xFFF8FAFC), // Slate 50
            hintText: hint,
            hintStyle: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              color: Color(0xFF94A3B8), // Slate 400
              letterSpacing: 0,
            ),
            prefixIcon: Container(
              margin: const EdgeInsets.all(8),
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: const Color(0xFFF1F5F9),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, size: 18, color: const Color(0xFF0284C7)),
            ),
            contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFE2E8F0), width: 1.2),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFF0EA5E9), width: 1.8),
            ),
            errorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFEF4444), width: 1.2),
            ),
            focusedErrorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFEF4444), width: 1.8),
            ),
          ),
          validator: validator,
        ),
      ],
    );
  }

  /// Primary action button with smooth gradient & elevation glow
  Widget _buildSubmitButton() {
    return GestureDetector(
      onTap: _loading ? null : _login,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOutCubic,
        height: 52,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0284C7), // Sky 600
              Color(0xFF06B6D4), // Cyan 500
            ],
          ),
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF0284C7).withValues(alpha: 0.35),
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
                    strokeWidth: 2.5,
                    color: Colors.white,
                  ),
                )
              : const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'دخول إلى النظام',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                      ),
                    ),
                    SizedBox(width: 8),
                    Icon(
                      Icons.arrow_back_rounded, // In Arabic RTL, left arrow means forward action
                      color: Colors.white,
                      size: 19,
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  /// Refined footer with privacy & version reassurance
  Widget _buildFooter() {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: const [
            Icon(Icons.shield_outlined, size: 14, color: Color(0xFF94A3B8)),
            SizedBox(width: 6),
            Text(
              'اتصال محلي مشفر · حماية كاملة للخصوصية',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: Color(0xFF94A3B8), // Slate 400
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        const Text(
          'مشروع تخرج نيبولا © 2026',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 10,
            fontWeight: FontWeight.w500,
            color: Color(0xFFCBD5E1), // Slate 300
          ),
        ),
      ],
    );
  }
}
