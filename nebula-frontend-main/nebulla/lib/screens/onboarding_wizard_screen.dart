import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/theme.dart';
import '../services/avatar_audio_service.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import '../widgets/interactive_animated_avatar.dart';
import 'main_shell.dart';

class OnboardingWizardScreen extends StatefulWidget {
  const OnboardingWizardScreen({super.key});

  @override
  State<OnboardingWizardScreen> createState() => _OnboardingWizardScreenState();
}

class _PersonEntry {
  String name;
  String relationship;
  String tone;
  String notes;
  File? photo;
  File? voiceSample;

  _PersonEntry({
    this.name = '',
    this.relationship = '',
    this.tone = 'حنين وودود',
    this.notes = '',
  });
}

class _OnboardingWizardScreenState extends State<OnboardingWizardScreen> {
  final _pageCtrl = PageController();
  final _repo = NebulaRepository.instance;
  final _audioService = AvatarAudioService.instance;
  final _picker = ImagePicker();

  int _currentStep = 0; // 0: Voice Clone, 1: Relatives/Knowledge, 2: Meet Avatar
  bool _isLoading = false;

  // Step 1: Voice Clone State
  File? _voiceSampleFile;
  String? _voiceSampleName;
  bool _isUploadingVoice = false;

  // Step 2: Relatives & Knowledge State
  final List<_PersonEntry> _persons = [
    _PersonEntry(
      name: '',
      relationship: 'أمي',
      tone: 'حنين وودود',
      notes: '',
    ),
  ];

  final List<String> _suggestedRelationships = [
    'أمي',
    'أبويا',
    'أخويا / أختي',
    'صاحبي المقرب',
    'شريك حياتي',
    'مديري في الشغل',
    'زميل عمل',
  ];

  final List<Map<String, String>> _suggestedTones = [
    {'label': 'حنين وودود', 'emoji': '❤️', 'desc': 'كلام دافئ ومحب'},
    {'label': 'هزار وقفشات ونكش', 'emoji': '😂', 'desc': 'ضحك ومزاح مستمر'},
    {'label': 'أخوي وعفوي', 'emoji': '🫂', 'desc': 'طبيعي وبدون تكلف'},
    {'label': 'احترام وتقدير', 'emoji': '🤝', 'desc': 'أدب ووقار واهتمام'},
    {'label': 'رسمي وجاد', 'emoji': '💼', 'desc': 'مهني ومباشر ومحدد'},
  ];

  @override
  void dispose() {
    _pageCtrl.dispose();
    super.dispose();
  }

  void _goToStep(int step) {
    setState(() => _currentStep = step);
    _pageCtrl.animateToPage(
      step,
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOutCubic,
    );
  }

  // ── Step 1: Voice Sample Actions ──────────────────────────────────────────

  Future<void> _pickVoiceSample() async {
    try {
      final res = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['wav', 'mp3', 'm4a', 'aac', 'ogg', 'mp4'],
      );
      if (res.isNotEmpty && res.first.path != null) {
        setState(() {
          _voiceSampleFile = File(res.first.path!);
          _voiceSampleName = res.first.name;
        });
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الملف الصوتي: $e');
    }
  }

  Future<void> _submitVoiceClone() async {
    if (_voiceSampleFile == null) {
      showErrorSnackbar(context, 'من فضلك اختر أو سجل عينة صوتية أولاً');
      return;
    }

    setState(() => _isUploadingVoice = true);
    try {
      // 1. Upload to voice clone engine (VoiceTut Studio)
      await _repo.uploadVoiceSample(1, _voiceSampleFile!);

      // 2. Enroll in Speaker Verification
      try {
        await _repo.enrollSpeaker(
          speakerName: 'المالك الأصلي',
          audioFile: _voiceSampleFile!,
        );
      } catch (_) {}

      if (!mounted) return;
      setState(() {
        _isUploadingVoice = false;
      });

      showSuccessSnackbar(
        context,
        'تم استنساخ صوتك بنجاح! نيبولا جاهز يتكلم بنبرتك.',
      );

      // Move to step 2 automatically after 1 second
      await Future.delayed(const Duration(milliseconds: 900));
      if (mounted) _goToStep(1);
    } catch (e) {
      if (mounted) {
        setState(() => _isUploadingVoice = false);
        showErrorSnackbar(context, 'فشل استنساخ الصوت: $e');
      }
    }
  }

  // ── Step 2: Person / Relatives Actions ─────────────────────────────────────

  void _addPerson() {
    setState(() {
      _persons.add(
        _PersonEntry(
          name: '',
          relationship: 'صاحبي المقرب',
          tone: 'هزار وقفشات ونكش',
          notes: '',
        ),
      );
    });
  }

  void _removePerson(int index) {
    if (_persons.length > 1) {
      setState(() => _persons.removeAt(index));
    }
  }

  Future<void> _pickPersonPhoto(int index) async {
    try {
      final img = await _picker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 85,
      );
      if (img != null) {
        setState(() => _persons[index].photo = File(img.path));
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الصورة: $e');
    }
  }

  Future<void> _pickPersonVoice(int index) async {
    try {
      final res = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['wav', 'mp3', 'm4a', 'aac', 'ogg'],
      );
      if (res.isNotEmpty && res.first.path != null) {
        setState(() => _persons[index].voiceSample = File(res.first.path!));
        if (mounted) {
          showSuccessSnackbar(context, 'تم إضافة عينة صوت: ${res.first.name}');
        }
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار عينة الصوت: $e');
    }
  }

  Future<void> _saveAllPersonsAndProceed() async {
    // Filter non-empty persons
    final validPersons = _persons.where((p) => p.name.trim().isNotEmpty).toList();

    setState(() => _isLoading = true);
    try {
      for (final p in validPersons) {
        await _repo.saveKnowledgePerson(
          name: p.name.trim(),
          relationship: p.relationship,
          tone: p.tone,
          notes: p.notes,
          photo: p.photo,
          voiceSample: p.voiceSample,
        );
      }

      if (!mounted) return;
      setState(() => _isLoading = false);
      _goToStep(2);
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        showErrorSnackbar(context, 'تعذر حفظ بعض البيانات: $e');
        _goToStep(2); // Still allow proceeding
      }
    }
  }

  // ── Step 3: Avatar Greeting ───────────────────────────────────────────────

  void _finishOnboarding() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const MainShell()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: AppColors.bg,
        body: Container(
          decoration: const BoxDecoration(
            gradient: AppColors.bgGradient,
          ),
          child: SafeArea(
            child: Column(
              children: [
                _buildHeader(),
                _buildStepIndicator(),
                Expanded(
                  child: PageView(
                    controller: _pageCtrl,
                    physics: const NeverScrollableScrollPhysics(),
                    children: [
                      _buildStep1VoiceClone(),
                      _buildStep2RelativesKnowledge(),
                      _buildStep3MeetAvatar(),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Header & Stepper ───────────────────────────────────────────────────────

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  gradient: AppColors.tealGradient,
                  borderRadius: BorderRadius.circular(12),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.teal.withValues(alpha: 0.3),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Icon(Icons.auto_awesome, color: Colors.black, size: 20),
              ),
              const SizedBox(width: 12),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'نيبولا • تهيئة توأمك الرقمي',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Text(
                    'خطوات بسيطة لتخصيص صوتك وذكرياتك',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ],
          ),
          if (_currentStep < 2)
            TextButton(
              onPressed: () {
                if (_currentStep == 0) {
                  _goToStep(1);
                } else if (_currentStep == 1) {
                  _goToStep(2);
                }
              },
              child: const Text(
                'تخطي الآن',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  color: AppColors.textMuted,
                  fontSize: 13,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildStepIndicator() {
    final stepTitles = ['استنساخ الصوت', 'المعارف والنبرة', 'توأمك الرقمي'];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      child: Row(
        children: List.generate(3, (index) {
          final isCompleted = _currentStep > index;
          final isCurrent = _currentStep == index;

          return Expanded(
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    children: [
                      Container(
                        height: 4,
                        decoration: BoxDecoration(
                          color: isCompleted || isCurrent
                              ? AppColors.teal
                              : AppColors.cardBorder,
                          borderRadius: BorderRadius.circular(2),
                          boxShadow: isCurrent
                              ? [
                                  BoxShadow(
                                    color: AppColors.teal.withValues(alpha: 0.5),
                                    blurRadius: 8,
                                  ),
                                ]
                              : null,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        stepTitles[index],
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 10,
                          fontWeight:
                              isCurrent ? FontWeight.bold : FontWeight.w500,
                          color: isCurrent
                              ? AppColors.teal
                              : (isCompleted
                                  ? AppColors.textSecondary
                                  : AppColors.textMuted),
                        ),
                      ),
                    ],
                  ),
                ),
                if (index < 2) const SizedBox(width: 8),
              ],
            ),
          );
        }),
      ),
    );
  }

  // ── Step 1: Voice Clone UI ─────────────────────────────────────────────────

  Widget _buildStep1VoiceClone() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppColors.teal.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.record_voice_over,
                          color: AppColors.teal, size: 24),
                    ),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'المرحلة الأولى: استنساخ صوتك',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          Text(
                            'VoiceTuT Zero-Shot AI Cloner',
                            style: TextStyle(
                              fontSize: 12,
                              color: AppColors.teal,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                const Text(
                  'عشان نيبولا يتكلم بنفس صوتك الطبيعي ونبرتك العامية المصرية، ارفع أو سجل مقطع صوتي واضح ليك مدته من 5 لـ 15 ثانية.',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    color: AppColors.textSecondary,
                    height: 1.6,
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppColors.cardBorder),
                  ),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.format_quote_rounded,
                              color: AppColors.teal, size: 18),
                          SizedBox(width: 6),
                          Text(
                            'نص مقترح تقرأه بصوتك الطبيعي:',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: AppColors.teal,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 8),
                      Text(
                        '"أهلاً بيك، أنا بسجل المقطع ده بصوتي العادي عشان نيبولا يتعلم طريقتي في الكلام ونبرتي، ونبدأ نشتغل سوا."',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textPrimary,
                          fontStyle: FontStyle.italic,
                          height: 1.5,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          _buildCard(
            child: Column(
              children: [
                if (_voiceSampleFile != null) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.teal.withValues(alpha: 0.5)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.audio_file_rounded,
                            color: AppColors.teal, size: 28),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _voiceSampleName ?? 'عينة صوتية مسجلة',
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textPrimary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const Text(
                                'جاهز للاستنساخ والتحقق البيومتري',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 11,
                                  color: AppColors.success,
                                ),
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, color: AppColors.textMuted),
                          onPressed: () => setState(() {
                            _voiceSampleFile = null;
                            _voiceSampleName = null;
                          }),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _isUploadingVoice ? null : _pickVoiceSample,
                        icon: const Icon(Icons.folder_open_rounded, size: 20),
                        label: Text(
                          _voiceSampleFile == null
                              ? 'اختيار تسجيل من الجهاز'
                              : 'تغيير الملف',
                          style: const TextStyle(fontFamily: 'Cairo', fontSize: 13),
                        ),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.teal,
                          side: const BorderSide(color: AppColors.teal),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                ElevatedButton(
                  onPressed: _isUploadingVoice || _voiceSampleFile == null
                      ? null
                      : _submitVoiceClone,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                    elevation: 4,
                  ),
                  child: _isUploadingVoice
                      ? const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.black,
                              ),
                            ),
                            SizedBox(width: 12),
                            Text(
                              'جاري استنساخ الصوت عبر VoiceTuT GPU...',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        )
                      : const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.bolt, size: 20),
                            SizedBox(width: 8),
                            Text(
                              'تأكيد واستنساخ الصوت الآن',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Step 2: Relatives & Knowledge Questionnaire ────────────────────────────

  Widget _buildStep2RelativesKnowledge() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppColors.purple.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.people_alt_rounded,
                          color: AppColors.purpleGlow, size: 24),
                    ),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'المرحلة الثانية: دايرة معارفك',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          Text(
                            'تحديد نبرة الكلام والذكريات المتبادلة',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              color: AppColors.purpleGlow,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                const Text(
                  'ضيف الأشخاص المقربين منك (صورهم، أصواتهم، ونبرة كلامك معاهم) عشان الـ LLM يعرفهم ويتعامل بنفس أسلوبك الطبيعي.',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: AppColors.textSecondary,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Persons Dynamic List
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _persons.length,
            separatorBuilder: (ctx, idx) => const SizedBox(height: 16),
            itemBuilder: (context, index) {
              return _buildPersonCard(index);
            },
          ),
          const SizedBox(height: 16),
          // Add Person Button
          OutlinedButton.icon(
            onPressed: _addPerson,
            icon: const Icon(Icons.person_add_rounded, color: AppColors.teal),
            label: const Text(
              '+ إضافة شخص آخر لدايرة المعارف',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: AppColors.teal,
              ),
            ),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              side: BorderSide(color: AppColors.teal.withValues(alpha: 0.5)),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
              ),
            ),
          ),
          const SizedBox(height: 24),
          // Save and Proceed Button
          ElevatedButton(
            onPressed: _isLoading ? null : _saveAllPersonsAndProceed,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.teal,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
              ),
              elevation: 4,
            ),
            child: _isLoading
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                  )
                : const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        'حفظ المعارف ومقابلة التوأم الرقمي',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      SizedBox(width: 8),
                      Icon(Icons.arrow_forward_rounded, size: 20),
                    ],
                  ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _buildPersonCard(int index) {
    final p = _persons[index];

    return _buildCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'الشخص #${index + 1}',
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: AppColors.teal,
                ),
              ),
              if (_persons.length > 1)
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: AppColors.error, size: 20),
                  onPressed: () => _removePerson(index),
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Photo & Name Row
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                onTap: () => _pickPersonPhoto(index),
                child: Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.cardBorder),
                    image: p.photo != null
                        ? DecorationImage(
                            image: FileImage(p.photo!),
                            fit: BoxFit.cover,
                          )
                        : null,
                  ),
                  child: p.photo == null
                      ? const Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.add_a_photo_outlined,
                                color: AppColors.teal, size: 22),
                            SizedBox(height: 2),
                            Text('صورة',
                                style: TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 9,
                                    color: AppColors.textMuted)),
                          ],
                        )
                      : null,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  children: [
                    TextFormField(
                      initialValue: p.name,
                      onChanged: (val) => p.name = val,
                      style: const TextStyle(
                          fontFamily: 'Cairo', color: AppColors.textPrimary, fontSize: 13),
                      decoration: InputDecoration(
                        labelText: 'الاسم أو اللقب (مثال: ماما سناء)',
                        labelStyle: const TextStyle(
                            fontFamily: 'Cairo', color: AppColors.textMuted, fontSize: 11),
                        filled: true,
                        fillColor: AppColors.surface,
                        contentPadding:
                            const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                          borderSide: const BorderSide(color: AppColors.cardBorder),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      initialValue: _suggestedRelationships.contains(p.relationship)
                          ? p.relationship
                          : null,
                      hint: const Text('صلة القرابة / العلاقة',
                          style: TextStyle(
                              fontFamily: 'Cairo', color: AppColors.textMuted, fontSize: 11)),
                      dropdownColor: AppColors.card,
                      style: const TextStyle(
                          fontFamily: 'Cairo', color: AppColors.textPrimary, fontSize: 12),
                      items: _suggestedRelationships
                          .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                          .toList(),
                      onChanged: (val) =>
                          setState(() => p.relationship = val ?? p.relationship),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: AppColors.surface,
                        contentPadding:
                            const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                          borderSide: const BorderSide(color: AppColors.cardBorder),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // Tone selector
          const Text(
            'نبرة وأسلوب كلامك المعتاد معاه:',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _suggestedTones.map((t) {
              final isSelected = p.tone == t['label'];
              return ChoiceChip(
                label: Text('${t['emoji']} ${t['label']!}'),
                selected: isSelected,
                onSelected: (selected) {
                  if (selected) setState(() => p.tone = t['label']!);
                },
                selectedColor: AppColors.teal.withValues(alpha: 0.25),
                backgroundColor: AppColors.surface,
                side: BorderSide(
                  color: isSelected ? AppColors.teal : AppColors.cardBorder,
                ),
                labelStyle: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                  color: isSelected ? AppColors.teal : AppColors.textSecondary,
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 14),
          // Voice Sample of Person (Optional)
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _pickPersonVoice(index),
                  icon: Icon(
                    p.voiceSample != null ? Icons.check_circle : Icons.mic_none_rounded,
                    color: p.voiceSample != null ? AppColors.success : AppColors.purpleGlow,
                    size: 18,
                  ),
                  label: Text(
                    p.voiceSample != null
                        ? 'تم إرفاق بصمة صوته ✓'
                        : 'إضافة تسجيل صوته (اختياري)',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: p.voiceSample != null ? AppColors.success : AppColors.textSecondary,
                    ),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(
                      color: p.voiceSample != null
                          ? AppColors.success
                          : AppColors.cardBorder,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          // Memories / Notes
          TextFormField(
            initialValue: p.notes,
            onChanged: (val) => p.notes = val,
            maxLines: 2,
            style: const TextStyle(
                fontFamily: 'Cairo', color: AppColors.textPrimary, fontSize: 12),
            decoration: InputDecoration(
              labelText: 'ذكريات أو ملاحظات يحفظها الـ LLM (اختياري)',
              labelStyle: const TextStyle(
                  fontFamily: 'Cairo', color: AppColors.textMuted, fontSize: 11),
              hintText: 'مثلاً: بيحب القهوة سادة، بنروح النادي سوا كل جمعة...',
              hintStyle: const TextStyle(
                  fontFamily: 'Cairo', color: AppColors.textMuted, fontSize: 11),
              filled: true,
              fillColor: AppColors.surface,
              contentPadding: const EdgeInsets.all(12),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: AppColors.cardBorder),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── Step 3: Meet Avatar UI ─────────────────────────────────────────────────

  Widget _buildStep3MeetAvatar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(
            width: 180,
            height: 180,
            child: InteractiveAnimatedAvatar(
              width: 180,
              height: 180,
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'أهلاً بيك! أنا نيبولا توأمك الرقمي',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppColors.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          const Text(
            'استنسخت صوتك وحفظت دايرة معارفك وذكرياتك.\nدلوقتي جاهز أتكلم معاك بنفس نبرتك وصوتك الطبيعي!',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              color: AppColors.textSecondary,
              height: 1.6,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          ElevatedButton.icon(
            onPressed: () {
              _audioService.speak(
                'أهلاً بيك، أنا نيبولا توأمك الرقمي، بتكلم بنفس صوتك وجاهز أساعدك في أي وقت!',
                personalityId: 1,
              );
            },
            icon: const Icon(Icons.volume_up_rounded, color: Colors.black, size: 22),
            label: const Text(
              'اسمع ترحيبي بصوتك المستنسخ (0ms)',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: Colors.black,
              ),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.teal,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              elevation: 4,
            ),
          ),
          const SizedBox(height: 20),
          OutlinedButton(
            onPressed: _finishOnboarding,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.textPrimary,
              side: const BorderSide(color: AppColors.cardBorder),
              padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
              ),
            ),
            child: const Text(
              'الدخول للتطبيق وبدء المحادثة',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── Helper Card ────────────────────────────────────────────────────────────

  Widget _buildCard({required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.08),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

