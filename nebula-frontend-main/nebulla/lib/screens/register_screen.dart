import 'dart:io';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';
import 'login_screen.dart';

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
  final _securityAnswerCtrl = TextEditingController();

  File? _profileImage;
  final ImagePicker _picker = ImagePicker();

  bool _loading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _showQuestions = false;

  String _selectedInteractionStyle = 'نصي وصوتي';
  String _selectedInterestDomain = 'البرمجة والتقنية';

  @override
  void dispose() {
    _fullNameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmPasswordCtrl.dispose();
    _securityAnswerCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickProfileImage() async {
    try {
      final picked = await _picker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 600,
        maxHeight: 600,
        imageQuality: 85,
      );
      if (picked != null && mounted) {
        setState(() => _profileImage = File(picked.path));
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(context, 'تعذر اختيار الصورة: $e');
      }
    }
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
        MaterialPageRoute(builder: (_) => const MainShell()),
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
                                    // Profile Picture Picker
                                    Center(
                                      child: GestureDetector(
                                        onTap: _pickProfileImage,
                                        child: Stack(
                                          children: [
                                            Container(
                                              width: 84,
                                              height: 84,
                                              decoration: BoxDecoration(
                                                shape: BoxShape.circle,
                                                color: const Color(0xFFF1F5F9),
                                                border: Border.all(
                                                  color: const Color(0xFF00B4D8),
                                                  width: 2.2,
                                                ),
                                                boxShadow: [
                                                  BoxShadow(
                                                    color: const Color(0xFF00B4D8)
                                                        .withValues(alpha: 0.2),
                                                    blurRadius: 10,
                                                    offset: const Offset(0, 4),
                                                  ),
                                                ],
                                              ),
                                              child: ClipOval(
                                                child: _profileImage != null
                                                    ? Image.file(
                                                        _profileImage!,
                                                        fit: BoxFit.cover,
                                                      )
                                                    : const Icon(
                                                        Icons.person_rounded,
                                                        size: 46,
                                                        color: Color(0xFF94A3B8),
                                                      ),
                                              ),
                                            ),
                                            Positioned(
                                              bottom: 0,
                                              right: 0,
                                              child: Container(
                                                width: 28,
                                                height: 28,
                                                decoration: BoxDecoration(
                                                  shape: BoxShape.circle,
                                                  color: const Color(0xFF00B4D8),
                                                  border: Border.all(
                                                    color: Colors.white,
                                                    width: 2,
                                                  ),
                                                ),
                                                child: const Icon(
                                                  Icons.camera_alt_rounded,
                                                  size: 14,
                                                  color: Colors.white,
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 6),
                                    Center(
                                      child: Text(
                                        _profileImage != null
                                            ? 'تم اختيار الصورة الشخصية'
                                            : 'إضافة صورة شخصية',
                                        style: const TextStyle(
                                          fontFamily: 'Cairo',
                                          fontSize: 12,
                                          fontWeight: FontWeight.bold,
                                          color: Color(0xFF0284C7),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 18),

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
                                    const SizedBox(height: 16),

                                    // 5. Expandable Onboarding Questionnaire (أسئلة التخصيص والذكاء الاصطناعي)
                                    Container(
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFF8FAFC),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: _showQuestions
                                              ? const Color(0xFF00B4D8)
                                              : const Color(0xFFE2E8F0),
                                          width: 1.4,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.stretch,
                                        children: [
                                          InkWell(
                                            onTap: () {
                                              setState(() => _showQuestions = !_showQuestions);
                                            },
                                            borderRadius: BorderRadius.circular(16),
                                            child: Padding(
                                              padding: const EdgeInsets.symmetric(
                                                horizontal: 14,
                                                vertical: 12,
                                              ),
                                              child: Row(
                                                children: [
                                                  Container(
                                                    width: 34,
                                                    height: 34,
                                                    decoration: BoxDecoration(
                                                      color: const Color(0xFFE0F2FE),
                                                      borderRadius: BorderRadius.circular(10),
                                                    ),
                                                    child: const Icon(
                                                      Icons.psychology_rounded,
                                                      color: Color(0xFF0284C7),
                                                      size: 20,
                                                    ),
                                                  ),
                                                  const SizedBox(width: 10),
                                                  Expanded(
                                                    child: Column(
                                                      crossAxisAlignment: CrossAxisAlignment.start,
                                                      children: [
                                                        const Text(
                                                          'أسئلة تخصيص الذكاء الاصطناعي',
                                                          style: TextStyle(
                                                            fontFamily: 'Cairo',
                                                            fontSize: 13,
                                                            fontWeight: FontWeight.bold,
                                                            color: Color(0xFF0F172A),
                                                          ),
                                                        ),
                                                        Text(
                                                          _showQuestions
                                                              ? 'اضغط للإغلاق'
                                                              : 'اضغط للإجابة عن أسئلة التخصيص',
                                                          style: const TextStyle(
                                                            fontFamily: 'Cairo',
                                                            fontSize: 11,
                                                            color: Color(0xFF64748B),
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                  Icon(
                                                    _showQuestions
                                                        ? Icons.keyboard_arrow_up_rounded
                                                        : Icons.keyboard_arrow_down_rounded,
                                                    color: const Color(0xFF0284C7),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ),
                                          if (_showQuestions) ...[
                                            const Divider(height: 1, color: Color(0xFFE2E8F0)),
                                            Padding(
                                              padding: const EdgeInsets.all(14),
                                              child: Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  // Q1: أسلوب التفاعل
                                                  const Text(
                                                    '1. ما هو أسلوب التفاعل المفضل لديك؟',
                                                    style: TextStyle(
                                                      fontFamily: 'Cairo',
                                                      fontSize: 12,
                                                      fontWeight: FontWeight.bold,
                                                      color: Color(0xFF1E293B),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 8),
                                                  Wrap(
                                                    spacing: 8,
                                                    runSpacing: 6,
                                                    children: [
                                                      'نصي وصوتي',
                                                      'صوتي تفاعلي',
                                                      'نصي فقط',
                                                      'موجز وسريع',
                                                    ].map((opt) {
                                                      final sel = _selectedInteractionStyle == opt;
                                                      return ChoiceChip(
                                                        label: Text(
                                                          opt,
                                                          style: TextStyle(
                                                            fontFamily: 'Cairo',
                                                            fontSize: 11.5,
                                                            fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                                                            color: sel ? Colors.white : const Color(0xFF334155),
                                                          ),
                                                        ),
                                                        selected: sel,
                                                        selectedColor: const Color(0xFF00B4D8),
                                                        backgroundColor: Colors.white,
                                                        shape: RoundedRectangleBorder(
                                                          borderRadius: BorderRadius.circular(10),
                                                          side: BorderSide(
                                                            color: sel ? const Color(0xFF00B4D8) : const Color(0xFFCBD5E1),
                                                          ),
                                                        ),
                                                        onSelected: (_) {
                                                          setState(() => _selectedInteractionStyle = opt);
                                                        },
                                                      );
                                                    }).toList(),
                                                  ),
                                                  const SizedBox(height: 14),

                                                  // Q2: مجال الاهتمام
                                                  const Text(
                                                    '2. ما هو مجال اهتمامك الأساسي؟',
                                                    style: TextStyle(
                                                      fontFamily: 'Cairo',
                                                      fontSize: 12,
                                                      fontWeight: FontWeight.bold,
                                                      color: Color(0xFF1E293B),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 8),
                                                  Wrap(
                                                    spacing: 8,
                                                    runSpacing: 6,
                                                    children: [
                                                      'البرمجة والتقنية',
                                                      'الأكاديميا والبحث',
                                                      'الأعمال والإدارة',
                                                      'مساعد شخصي عام',
                                                    ].map((opt) {
                                                      final sel = _selectedInterestDomain == opt;
                                                      return ChoiceChip(
                                                        label: Text(
                                                          opt,
                                                          style: TextStyle(
                                                            fontFamily: 'Cairo',
                                                            fontSize: 11.5,
                                                            fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                                                            color: sel ? Colors.white : const Color(0xFF334155),
                                                          ),
                                                        ),
                                                        selected: sel,
                                                        selectedColor: const Color(0xFF00B4D8),
                                                        backgroundColor: Colors.white,
                                                        shape: RoundedRectangleBorder(
                                                          borderRadius: BorderRadius.circular(10),
                                                          side: BorderSide(
                                                            color: sel ? const Color(0xFF00B4D8) : const Color(0xFFCBD5E1),
                                                          ),
                                                        ),
                                                        onSelected: (_) {
                                                          setState(() => _selectedInterestDomain = opt);
                                                        },
                                                      );
                                                    }).toList(),
                                                  ),
                                                  const SizedBox(height: 14),

                                                  // Q3: معلومة أو سؤال للذاكرة
                                                  const Text(
                                                    '3. معلومة شخصية تريد من المساعد حفظها بذاكرته:',
                                                    style: TextStyle(
                                                      fontFamily: 'Cairo',
                                                      fontSize: 12,
                                                      fontWeight: FontWeight.bold,
                                                      color: Color(0xFF1E293B),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 6),
                                                  TextFormField(
                                                    controller: _securityAnswerCtrl,
                                                    style: const TextStyle(
                                                      fontFamily: 'Cairo',
                                                      fontSize: 12,
                                                      color: Color(0xFF1E293B),
                                                    ),
                                                    decoration: InputDecoration(
                                                      hintText: 'مثال: مشروعي الأساسي هو تخرج روبوت نيبولا',
                                                      hintStyle: const TextStyle(
                                                        fontFamily: 'Cairo',
                                                        fontSize: 11,
                                                        color: Color(0xFF94A3B8),
                                                      ),
                                                      filled: true,
                                                      fillColor: Colors.white,
                                                      contentPadding: const EdgeInsets.symmetric(
                                                        horizontal: 12,
                                                        vertical: 10,
                                                      ),
                                                      border: OutlineInputBorder(
                                                        borderRadius: BorderRadius.circular(10),
                                                        borderSide: const BorderSide(color: Color(0xFFCBD5E1)),
                                                      ),
                                                      enabledBorder: OutlineInputBorder(
                                                        borderRadius: BorderRadius.circular(10),
                                                        borderSide: const BorderSide(color: Color(0xFFCBD5E1)),
                                                      ),
                                                      focusedBorder: OutlineInputBorder(
                                                        borderRadius: BorderRadius.circular(10),
                                                        borderSide: const BorderSide(color: Color(0xFF00B4D8), width: 1.5),
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(height: 10),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                                    decoration: BoxDecoration(
                                                      color: const Color(0xFFEFF6FF),
                                                      borderRadius: BorderRadius.circular(8),
                                                    ),
                                                    child: const Row(
                                                      children: [
                                                        Icon(Icons.info_outline_rounded, size: 14, color: Color(0xFF2563EB)),
                                                        SizedBox(width: 6),
                                                        Expanded(
                                                          child: Text(
                                                            'سيتم ربط ومزامنة هذه الإجابات تلقائياً مع نموذج الباك إند والذاكرة الدائمة.',
                                                            style: TextStyle(
                                                              fontFamily: 'Cairo',
                                                              fontSize: 10.5,
                                                              color: Color(0xFF1E40AF),
                                                            ),
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
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
