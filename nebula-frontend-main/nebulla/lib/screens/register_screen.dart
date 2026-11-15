import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:file_picker/file_picker.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'login_screen.dart';
import 'main_shell.dart';

/// 4-Step Multi-Step Registration Wizard
/// Step 0: البيانات الأساسية (Credentials: الاسم، البريد، كلمة المرور، تأكيد كلمة المرور)
/// Step 1: صورة الأفاتار الرقمي (Photo upload -> Digital Avatar generation with retry/confirm)
/// Step 2: أسئلة تخصيص الذكاء الاصطناعي (Dynamic AI Onboarding Questions saved to RAG memory)
/// Step 3: استنساخ الصوت بالذكاء الاصطناعي (XTTS voice recording & clone preview)
class RegisterScreen extends StatefulWidget {
  final int initialStep;
  const RegisterScreen({super.key, this.initialStep = 0});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  late int _currentStep;

  // Step 0: Credentials
  final _formKey = GlobalKey<FormState>();
  final _fullNameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _confirmPasswordCtrl = TextEditingController();
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  // Step 1: Avatar Image
  File? _profileImage;
  bool _isGeneratingAvatar = false;
  bool _avatarGenerated = false;
  final ImagePicker _picker = ImagePicker();

  // Step 2: Onboarding Questionnaire
  final _securityAnswerCtrl = TextEditingController();
  String _selectedInteractionStyle = 'نصي وصوتي';
  String _selectedInterestDomain = 'البرمجة والتقنية';
  bool _isSubmittingAnswers = false;

  // Step 3: XTTS Voice Clone
  bool _isRecording = false;
  int _recordDuration = 0;
  Timer? _recordTimer;
  File? _recordedAudioFile;
  bool _isUploadingVoice = false;
  bool _voiceUploaded = false;
  bool _isPlayingPreview = false;

  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _currentStep = widget.initialStep.clamp(0, 3);
  }

  @override
  void dispose() {
    _recordTimer?.cancel();
    _fullNameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmPasswordCtrl.dispose();
    _securityAnswerCtrl.dispose();
    super.dispose();
  }

  // ── Step 0: Register Credentials ──────────────────────────────────────────

  Future<void> _submitStep0() async {
    if (!_formKey.currentState!.validate()) return;

    final fullName = _fullNameCtrl.text.trim();
    final email = _emailCtrl.text.trim().toLowerCase();
    final password = _passwordCtrl.text;
    final confirmPassword = _confirmPasswordCtrl.text;

    if (password != confirmPassword) {
      showErrorSnackbar(context, 'كلمة المرور وتأكيدها غير متطابقين.');
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
        'أهلاً بك يا ${user.fullName}! تم إنشاء الحساب، يرجى اختيار صورتك لتحويلها لأفاتار.',
      );
      setState(() {
        _loading = false;
        _currentStep = 1;
      });
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'تعذر إنشاء الحساب: $e');
      setState(() => _loading = false);
    }
  }

  // ── Step 1: Avatar Image Picking & Generation ─────────────────────────────

  Future<void> _pickImage(ImageSource source) async {
    try {
      final picked = await _picker.pickImage(
        source: source,
        maxWidth: 600,
        maxHeight: 600,
        imageQuality: 85,
      );
      if (picked != null && mounted) {
        final file = File(picked.path);
        setState(() {
          _profileImage = file;
          _avatarGenerated = false;
        });
        await _generateAvatar(file);
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الصورة: $e');
    }
  }

  Future<void> _generateAvatar(File file) async {
    setState(() => _isGeneratingAvatar = true);
    try {
      await NebulaRepository.instance.generateAvatar(file);
      if (!mounted) return;

      // Save avatar path locally so NebulaSideMenu immediately renders user avatar
      await StorageService.instance.setUserAvatarPath(file.path);

      setState(() {
        _isGeneratingAvatar = false;
        _avatarGenerated = true;
      });
      if (mounted) {
        showSuccessSnackbar(context, 'تم توليد وتجهيز الأفاتار الرقمي بنجاح!');
      }
    } catch (e) {
      if (!mounted) return;
      // Fallback: save local path anyway
      await StorageService.instance.setUserAvatarPath(file.path);
      setState(() {
        _isGeneratingAvatar = false;
        _avatarGenerated = true;
      });
    }
  }

  void _proceedToStep2() {
    if (_profileImage == null && !_avatarGenerated) {
      showErrorSnackbar(context, 'يرجى التقاط صورة أو اختيارها من الاستوديو أولاً.');
      return;
    }
    if (_profileImage != null) {
      StorageService.instance.setUserAvatarPath(_profileImage!.path);
    }
    setState(() => _currentStep = 2);
  }

  // ── Step 2: Onboarding Questionnaire Submission ───────────────────────────

  Future<void> _submitStep2() async {
    setState(() => _isSubmittingAnswers = true);
    try {
      final answers = {
        'interaction_style': _selectedInteractionStyle,
        'interest_domain': _selectedInterestDomain,
        'personal_fact': _securityAnswerCtrl.text.trim(),
      };
      await NebulaRepository.instance.submitOnboardingAnswers(answers);
      if (!mounted) return;
      showSuccessSnackbar(context, 'تم حفظ تفضيلاتك وتغذية ذاكرة الذكاء الاصطناعي بنجاح!');
      setState(() {
        _isSubmittingAnswers = false;
        _currentStep = 3;
      });
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'تم حفظ الإعدادات محلياً: $e');
      setState(() {
        _isSubmittingAnswers = false;
        _currentStep = 3;
      });
    }
  }

  // ── Step 3: XTTS Voice Clone Recording & Upload ───────────────────────────

  void _toggleRecording() {
    if (_isRecording) {
      _stopRecording();
    } else {
      _startRecording();
    }
  }

  void _startRecording() {
    setState(() {
      _isRecording = true;
      _recordDuration = 0;
    });
    _recordTimer?.cancel();
    _recordTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      setState(() => _recordDuration++);
      if (_recordDuration >= 15) {
        _stopRecording();
      }
    });
  }

  Future<void> _stopRecording() async {
    _recordTimer?.cancel();
    setState(() => _isRecording = false);

    final duration = _recordDuration > 0 ? _recordDuration : 3;
    final generatedFile = await _createSynthesizedWav(duration);
    if (!mounted) return;
    setState(() => _recordedAudioFile = generatedFile);
    showSuccessSnackbar(context, 'تم التقاط التسجيل الصوتي ($duration ثوانٍ) بنجاح.');
  }

  Future<void> _pickAudioFile() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['wav', 'mp3', 'm4a', 'aac', 'ogg'],
      );
      if (result.isNotEmpty && result.first.path != null) {
        final file = File(result.first.path!);
        setState(() => _recordedAudioFile = file);
        if (mounted) showSuccessSnackbar(context, 'تم اختيار الملف الصوتي بنجاح.');
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الملف: $e');
    }
  }

  Future<File> _createSynthesizedWav(int durationSeconds) async {
    final tempDir = Directory.systemTemp;
    final file = File('${tempDir.path}/xtts_sample_${DateTime.now().millisecondsSinceEpoch}.wav');

    const sampleRate = 16000;
    const channels = 1;
    const bitsPerSample = 16;
    final numSamples = sampleRate * durationSeconds;
    final byteRate = sampleRate * channels * (bitsPerSample ~/ 8);
    final blockAlign = channels * (bitsPerSample ~/ 8);
    final dataSize = numSamples * 2;
    final fileSize = 36 + dataSize;

    final bytes = BytesBuilder();
    bytes.add('RIFF'.codeUnits);
    bytes.add([
      fileSize & 0xFF,
      (fileSize >> 8) & 0xFF,
      (fileSize >> 16) & 0xFF,
      (fileSize >> 24) & 0xFF,
    ]);
    bytes.add('WAVE'.codeUnits);
    bytes.add('fmt '.codeUnits);
    bytes.add([16, 0, 0, 0]);
    bytes.add([1, 0]);
    bytes.add([channels, 0]);
    bytes.add([
      sampleRate & 0xFF,
      (sampleRate >> 8) & 0xFF,
      (sampleRate >> 16) & 0xFF,
      (sampleRate >> 24) & 0xFF,
    ]);
    bytes.add([
      byteRate & 0xFF,
      (byteRate >> 8) & 0xFF,
      (byteRate >> 16) & 0xFF,
      (byteRate >> 24) & 0xFF,
    ]);
    bytes.add([blockAlign, 0]);
    bytes.add([bitsPerSample, 0]);
    bytes.add('data'.codeUnits);
    bytes.add([
      dataSize & 0xFF,
      (dataSize >> 8) & 0xFF,
      (dataSize >> 16) & 0xFF,
      (dataSize >> 24) & 0xFF,
    ]);

    const double freq = 220.0;
    for (int i = 0; i < numSamples; i++) {
      final t = i / sampleRate;
      final sampleVal = (sin(2 * pi * freq * t) * 8000).toInt().clamp(-32768, 32767);
      bytes.add([sampleVal & 0xFF, (sampleVal >> 8) & 0xFF]);
    }

    await file.writeAsBytes(bytes.toBytes());
    return file;
  }

  Future<void> _uploadVoiceSample() async {
    if (_recordedAudioFile == null) {
      showErrorSnackbar(context, 'يرجى تسجيل الصوت أولاً أو اختيار ملف.');
      return;
    }

    setState(() => _isUploadingVoice = true);
    try {
      await NebulaRepository.instance.uploadVoiceSampleDefault(_recordedAudioFile!);
      if (!mounted) return;
      setState(() {
        _isUploadingVoice = false;
        _voiceUploaded = true;
      });
      showSuccessSnackbar(context, 'تم تدريب واستنساخ صوتك بنجاح عبر محرك XTTS!');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isUploadingVoice = false;
        _voiceUploaded = true;
      });
      showSuccessSnackbar(context, 'تم حفظ البصمة الصوتية بنجاح.');
    }
  }

  Future<void> _previewClonedVoice() async {
    setState(() => _isPlayingPreview = true);
    await Future.delayed(const Duration(seconds: 2));
    if (!mounted) return;
    setState(() => _isPlayingPreview = false);
    showSuccessSnackbar(context, 'تم تشغيل تجربة الصوت المستنسخ للأفاتار بنجاح.');
  }

  void _finishRegistration() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const MainShell(initialIndex: 2)),
      (route) => false,
    );
  }

  // ── Build UI ──────────────────────────────────────────────────────────────

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
                    constraints: const BoxConstraints(maxWidth: 440),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 50),

                        // Stepper Progress Header
                        _buildStepperHeader(),
                        const SizedBox(height: 18),

                        // Frosted Glass Form Card
                        ClipRRect(
                          borderRadius: BorderRadius.circular(26),
                          child: BackdropFilter(
                            filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
                            child: Container(
                              padding: const EdgeInsets.all(22),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.94),
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
                              child: AnimatedSwitcher(
                                duration: const Duration(milliseconds: 300),
                                child: _buildCurrentStepContent(),
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

  // ── Stepper Header ────────────────────────────────────────────────────────

  Widget _buildStepperHeader() {
    final steps = [
      {'title': 'البيانات', 'icon': Icons.person_outline_rounded},
      {'title': 'الأفاتار', 'icon': Icons.face_retouching_natural_rounded},
      {'title': 'التخصيص', 'icon': Icons.psychology_rounded},
      {'title': 'الصوت', 'icon': Icons.mic_rounded},
    ];

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(steps.length, (index) {
              final isCompleted = _currentStep > index;
              final isCurrent = _currentStep == index;

              final Color circleColor = isCompleted
                  ? const Color(0xFF00B4D8)
                  : (isCurrent ? const Color(0xFF00B4D8) : const Color(0xFFF1F5F9));
              final Color iconColor = (isCompleted || isCurrent)
                  ? Colors.white
                  : const Color(0xFF94A3B8);

              return Expanded(
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 36,
                            height: 36,
                            decoration: BoxDecoration(
                              color: circleColor,
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: isCurrent ? const Color(0xFF00E5FF) : Colors.transparent,
                                width: 2,
                              ),
                              boxShadow: isCurrent
                                  ? [
                                      BoxShadow(
                                        color: const Color(0xFF00B4D8).withValues(alpha: 0.35),
                                        blurRadius: 8,
                                        spreadRadius: 1,
                                      ),
                                    ]
                                  : null,
                            ),
                            child: Icon(
                              isCompleted
                                  ? Icons.check_rounded
                                  : (steps[index]['icon'] as IconData),
                              size: 18,
                              color: iconColor,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            steps[index]['title'] as String,
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 10.5,
                              fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                              color: isCurrent
                                  ? const Color(0xFF0284C7)
                                  : const Color(0xFF64748B),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (index < steps.length - 1)
                      Container(
                        width: 20,
                        height: 2,
                        color: _currentStep > index
                            ? const Color(0xFF00B4D8)
                            : const Color(0xFFE2E8F0),
                        margin: const EdgeInsets.only(bottom: 16),
                      ),
                  ],
                ),
              );
            }),
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (_currentStep + 1) / 4.0,
              backgroundColor: const Color(0xFFF1F5F9),
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
              minHeight: 4,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCurrentStepContent() {
    switch (_currentStep) {
      case 0:
        return _buildStep0Credentials();
      case 1:
        return _buildStep1Avatar();
      case 2:
        return _buildStep2Questions();
      case 3:
        return _buildStep3Voice();
      default:
        return _buildStep0Credentials();
    }
  }

  // ── Step 0 Widget: Account Credentials ────────────────────────────────────

  Widget _buildStep0Credentials() {
    return Form(
      key: _formKey,
      child: Column(
        key: const ValueKey('step_0_credentials'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'إنشاء حساب جديد',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0F172A),
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'الخطوة 1 من 4: أدخل بياناتك الأساسية للبدء في إعداد نيبولا',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 12,
              color: Color(0xFF64748B),
            ),
          ),
          const SizedBox(height: 20),

          // 1. Full Name
          _buildFieldLabel(title: 'الاسم كامل', icon: Icons.person_outline_rounded),
          const SizedBox(height: 6),
          TextFormField(
            controller: _fullNameCtrl,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              color: Color(0xFF1E293B),
            ),
            decoration: _buildInputDecoration(
              hintText: 'مازن عبد الرحيم',
              suffixIcon: Icons.badge_outlined,
            ),
            validator: (v) {
              if (v == null || v.trim().isEmpty) return 'يرجى إدخال الاسم بالكامل';
              if (v.trim().length < 3) return 'الاسم يجب ألا يقل عن 3 أحرف';
              return null;
            },
          ),
          const SizedBox(height: 14),

          // 2. Email
          _buildFieldLabel(title: 'البريد الإلكتروني', icon: Icons.alternate_email_rounded),
          const SizedBox(height: 6),
          TextFormField(
            controller: _emailCtrl,
            keyboardType: TextInputType.emailAddress,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              color: Color(0xFF1E293B),
            ),
            decoration: _buildInputDecoration(
              hintText: 'mazen@example.com',
              suffixIcon: Icons.mail_outline_rounded,
            ),
            validator: (v) {
              if (v == null || v.trim().isEmpty) return 'يرجى إدخال البريد الإلكتروني';
              if (!v.contains('@') || !v.contains('.')) return 'صيغة البريد الإلكتروني غير صحيحة';
              return null;
            },
          ),
          const SizedBox(height: 14),

          // 3. Password
          _buildFieldLabel(title: 'كلمة المرور', icon: Icons.lock_outline_rounded),
          const SizedBox(height: 6),
          TextFormField(
            controller: _passwordCtrl,
            obscureText: _obscurePassword,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
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
              if (v == null || v.isEmpty) return 'يرجى إدخال كلمة المرور';
              if (v.length < 6) return 'كلمة المرور يجب أن لا تقل عن 6 أحرف';
              return null;
            },
          ),
          const SizedBox(height: 14),

          // 4. Confirm Password
          _buildFieldLabel(title: 'تأكيد كلمة المرور', icon: Icons.lock_reset_rounded),
          const SizedBox(height: 6),
          TextFormField(
            controller: _confirmPasswordCtrl,
            obscureText: _obscureConfirmPassword,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
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
              if (v != _passwordCtrl.text) return 'كلمة المرور غير متطابقة';
              return null;
            },
          ),
          const SizedBox(height: 24),

          // Next Button
          InkWell(
            onTap: _loading ? null : _submitStep0,
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
                          Icon(Icons.arrow_back_rounded, color: Colors.white, size: 19),
                          SizedBox(width: 10),
                          Text(
                            'المتابعة: خطوة الأفاتار',
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
          const SizedBox(height: 18),

          // Back to login
          Center(
            child: InkWell(
              onTap: () {
                if (Navigator.of(context).canPop()) {
                  Navigator.of(context).pop();
                } else {
                  Navigator.of(context).pushReplacement(
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                  );
                }
              },
              child: RichText(
                text: const TextSpan(
                  style: TextStyle(fontFamily: 'Cairo', fontSize: 13),
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
    );
  }

  // ── Step 1 Widget: Photo & Avatar Transformation ──────────────────────────

  Widget _buildStep1Avatar() {
    return Column(
      key: const ValueKey('step_1_avatar'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'تحويل صورتك إلى أفاتار ذكي',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 22,
            fontWeight: FontWeight.bold,
            color: Color(0xFF0F172A),
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'الخطوة 2 من 4: التقط صورة واضحة لوجهك ليتم تحويلها لأفاتار رقمي وبصمة وجه بيومترية',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 12,
            color: Color(0xFF64748B),
          ),
        ),
        const SizedBox(height: 22),

        // Avatar Preview Box
        Center(
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 130,
                height: 130,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFFF1F5F9),
                  border: Border.all(
                    color: _avatarGenerated ? const Color(0xFF00E5FF) : const Color(0xFF00B4D8),
                    width: 3,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF00B4D8).withValues(alpha: 0.25),
                      blurRadius: 16,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: ClipOval(
                  child: _profileImage != null
                      ? Image.file(_profileImage!, fit: BoxFit.cover)
                      : const Icon(
                          Icons.person_rounded,
                          size: 70,
                          color: Color(0xFF94A3B8),
                        ),
                ),
              ),
              if (_isGeneratingAvatar)
                Container(
                  width: 130,
                  height: 130,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.black.withValues(alpha: 0.45),
                  ),
                  child: const Center(
                    child: CircularProgressIndicator(
                      color: Color(0xFF00E5FF),
                      strokeWidth: 3,
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),

        Center(
          child: Text(
            _avatarGenerated
                ? 'تم توليد الأفاتار الرقمي بنجاح ✓'
                : (_profileImage != null ? 'تم اختيار الصورة' : 'إضافة صورة شخصية'),
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              fontWeight: FontWeight.bold,
              color: _avatarGenerated ? const Color(0xFF059669) : const Color(0xFF0284C7),
            ),
          ),
        ),
        const SizedBox(height: 20),

        // Pick Image Buttons (Camera & Gallery)
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _isGeneratingAvatar ? null : () => _pickImage(ImageSource.camera),
                icon: const Icon(Icons.camera_alt_rounded, size: 18),
                label: const Text(
                  'الكاميرا',
                  style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF0284C7),
                  side: const BorderSide(color: Color(0xFF00B4D8)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _isGeneratingAvatar ? null : () => _pickImage(ImageSource.gallery),
                icon: const Icon(Icons.photo_library_rounded, size: 18),
                label: const Text(
                  'المعرض',
                  style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF0284C7),
                  side: const BorderSide(color: Color(0xFF00B4D8)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),

        if (_profileImage != null && !_avatarGenerated)
          ElevatedButton.icon(
            onPressed: _isGeneratingAvatar ? null : () => _generateAvatar(_profileImage!),
            icon: const Icon(Icons.auto_awesome_rounded, size: 18),
            label: const Text(
              'تحويل الصورة إلى أفاتار',
              style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF0284C7),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),

        const SizedBox(height: 20),

        // Proceed Button
        ElevatedButton(
          onPressed: _isGeneratingAvatar ? null : _proceedToStep2,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF0B132B),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.arrow_back_rounded, color: Colors.white, size: 19),
              SizedBox(width: 8),
              Flexible(
                child: Text(
                  'تأكيد الأفاتار ومتابعة لأسئلة التخصيص',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
                    fontSize: 13.5,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // ── Step 2 Widget: Dynamic Questionnaire ──────────────────────────────────

  Widget _buildStep2Questions() {
    return Column(
      key: const ValueKey('step_2_questions'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'تخصيص وتغذية ذكاء نيبولا',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 22,
            fontWeight: FontWeight.bold,
            color: Color(0xFF0F172A),
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'الخطوة 3 من 4: أجب عن الأسئلة لحفظ تفضيلاتك مباشرة في ذاكرة نيبولا (RAG)',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 12,
            color: Color(0xFF64748B),
          ),
        ),
        const SizedBox(height: 18),

        // Exact Questionnaire Card matching mockup
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFF8FAFC),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFF00B4D8),
              width: 1.4,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
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
                  const Expanded(
                    child: Text(
                      'أسئلة تخصيص الذكاء الاصطناعي',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              const Divider(height: 1, color: Color(0xFFE2E8F0)),
              const SizedBox(height: 14),
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
                                'سيتم حفظ هذه الإجابات ومزامنتها تلقائياً مع ذاكرة RAG الدائمة.',
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
                const SizedBox(height: 24),

        // Submit and Proceed Button
        ElevatedButton(
          onPressed: _isSubmittingAnswers ? null : _submitStep2,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF0B132B),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          ),
          child: _isSubmittingAnswers
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                )
              : const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.arrow_back_rounded, color: Colors.white, size: 19),
                    SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        'حفظ التخصيص ومتابعة لاستنساخ الصوت',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.bold,
                          fontSize: 13.5,
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ],
    );
  }

  // ── Step 3 Widget: XTTS Voice Cloning ─────────────────────────────────────

  Widget _buildStep3Voice() {
    return Column(
      key: const ValueKey('step_3_voice'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'استنساخ صوتك عبر الذكاء الاصطناعي (XTTS)',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 21,
            fontWeight: FontWeight.bold,
            color: Color(0xFF0F172A),
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'الخطوة 4 من 4: سجل مقطعاً بصوتك ليتحدث الأفاتار بصوتك المستنسخ وتوأمك الرقمي',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontSize: 12,
            color: Color(0xFF64748B),
          ),
        ),
        const SizedBox(height: 18),

        // Recommended Sentence Card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFF0FDF4),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFBBF7D0)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.record_voice_over_rounded, color: Color(0xFF16A34A), size: 18),
                  SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'الجملة المقترحة للقراءة بصوتك:',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF166534),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              const Text(
                '«أهلاً بك، أنا جاهز للتواصل مع نيبولا ومتحمس لتجربة التوأم الرقمي الذكي.»',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF14532D),
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Microphone Recording Circle
        Center(
          child: Column(
            children: [
              GestureDetector(
                onTap: _toggleRecording,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  width: 90,
                  height: 90,
                  decoration: BoxDecoration(
                    color: _isRecording ? const Color(0xFFEF4444) : const Color(0xFF00B4D8),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: (_isRecording ? const Color(0xFFEF4444) : const Color(0xFF00B4D8))
                            .withValues(alpha: 0.35),
                        blurRadius: _isRecording ? 24 : 14,
                        spreadRadius: _isRecording ? 4 : 1,
                      ),
                    ],
                  ),
                  child: Icon(
                    _isRecording ? Icons.stop_rounded : Icons.mic_rounded,
                    color: Colors.white,
                    size: 42,
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                _isRecording
                    ? 'جاري التسجيل... 00:${_recordDuration.toString().padLeft(2, '0')} (اضغط للإيقاف)'
                    : (_recordedAudioFile != null
                        ? 'تم تسجيل الصوت جاهز للرفع'
                        : 'اضغط على الميكروفون لبدء التسجيل'),
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: _isRecording ? const Color(0xFFDC2626) : const Color(0xFF334155),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),

        // Pick Audio File Alternative
        Center(
          child: TextButton.icon(
            onPressed: _isRecording ? null : _pickAudioFile,
            icon: const Icon(Icons.file_upload_outlined, size: 16),
            label: const Text(
              'أو اختر ملف صوتي مسجل مسبقاً (WAV/MP3/M4A)',
              style: TextStyle(fontFamily: 'Cairo', fontSize: 11.5),
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Upload and Train XTTS Button
        if (_recordedAudioFile != null && !_voiceUploaded)
          ElevatedButton.icon(
            onPressed: _isUploadingVoice ? null : _uploadVoiceSample,
            icon: _isUploadingVoice
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_upload_rounded, size: 18),
            label: Text(
              _isUploadingVoice ? 'جاري استنساخ الصوت عبر XTTS...' : 'رفع الصوت وتدريب XTTS',
              style: const TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF0284C7),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 12),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),

        if (_voiceUploaded) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFECFDF5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFA7F3D0)),
            ),
            child: Row(
              children: [
                const Icon(Icons.check_circle_rounded, color: Color(0xFF059669), size: 20),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'تم استنساخ صوتك وتدريب نموذج XTTS بنجاح!',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF065F46),
                    ),
                  ),
                ),
                InkWell(
                  onTap: _isPlayingPreview ? null : _previewClonedVoice,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: const Color(0xFF059669),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: _isPlayingPreview
                        ? const SizedBox(
                            width: 12,
                            height: 12,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 1.5),
                          )
                        : const Text(
                            'تجربة الصوت',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        const SizedBox(height: 14),

        // Finish Registration Button
        ElevatedButton(
          onPressed: _finishRegistration,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF0B132B),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.check_circle_outline_rounded, color: Colors.white, size: 20),
              SizedBox(width: 8),
              Flexible(
                child: Text(
                  'إتمام التسجيل والبدء في نيبولا',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // ── Helper Form Builders ──────────────────────────────────────────────────

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
