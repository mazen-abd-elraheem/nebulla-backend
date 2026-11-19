import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/locale_service.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../utils/avatar_photo_picker.dart';
import '../widgets/common_widgets.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';
import 'main_shell.dart';

/// Clean Home Screen matching user reference design 100%:
/// - Full-height centered avatar on a clean light background.
/// - Top bar with circular Menu button (left) and Notification Bell button (right).
/// - Bottom navigation handled by GlobalNebulaFooter in MainShell.
/// - Direct backend binding: when user enters/uploads their photo, it is converted
///   to a speaking 3D avatar with 13 FLAME / local_face_animator expressions & 36 visemes.
/// - LLM dialogue synchronization: avatar reacts live to dialogue emotion, face emojis & speech.
class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const DashboardScreen({super.key, this.onNavigate});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _audioService = AvatarAudioService.instance;
  final _repo = NebulaRepository.instance;
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  bool _isGenerating = false;

  @override
  void initState() {
    super.initState();
    final user = StorageService.instance.getUser();
    if (user != null && user.fullName.trim().isNotEmpty) {
      _audioService.setPersonaName(user.fullName.trim());
    }
    _audioService.loadActiveAvatar(force: true);
  }

  void _openMenu() {
    try {
      MainShell.openSideMenu(context);
    } catch (_) {
      NebulaSideMenu.show(
        context,
        activeIndex: 2,
        onNavigate: (idx) {
          if (widget.onNavigate != null && idx >= 0) {
            widget.onNavigate!(idx);
          }
        },
      );
    }
  }

  void _handleNotificationsTap() {
    final t = LocaleService.instance.tr;
    showSuccessSnackbar(
      context,
      t(
        'لا توجد تنبيهات جديدة، الأفاتار جاهز للتواصل والتفاعل معك.',
        'No new notifications. The avatar is ready to interact with you.',
      ),
    );
  }

  Future<void> _triggerAvatarGreeting() async {
    final pid = _audioService.activePersonalityId.value;
    try {
      final data = await _repo.chat(
        LocaleService.instance.tr(
          'رحب بالمستخدم بجملة قصيرة ودودة ومبهجة',
          'Greet the user with a short friendly sentence',
        ),
        personalityId: pid,
      );
      final reply =
          (data['reply'] as String?) ?? (data['response'] as String?) ?? '';
      if (reply.trim().isNotEmpty) {
        final faceEmoji = data['face_emoji'] as String?;
        final expression = data['expression'] as String?;
        final emotion = data['emotion'] as String?;
        final avatarAction = data['avatar_action'] is Map<String, dynamic>
            ? data['avatar_action'] as Map<String, dynamic>
            : null;
        await _audioService.speak(
          reply,
          emotion: emotion,
          faceEmoji: faceEmoji,
          expression: expression,
          avatarAction: avatarAction,
          personalityId: pid,
        );
        return;
      }
    } catch (_) {}

    final name = _audioService.activePersonaName.value;
    await _audioService.speak(
      LocaleService.instance.tr(
        'أهلاً بك! أنا $name، جاهز لمساعدتك بالصوت والتعبيرات الحية.',
        'Welcome! I am $name, ready to help you.',
      ),
      faceEmoji: '😊',
      expression: 'happy',
      personalityId: pid,
    );
  }

  Future<void> _uploadAndTransform({bool preferCamera = false}) async {
    try {
      final file = await pickAvatarPhotoFile(preferCamera: preferCamera);
      if (file == null || !mounted) return;
      setState(() => _isGenerating = true);

      try {
        await _repo.generateAvatar(file);
        if (!mounted) return;
        setState(() => _isGenerating = false);
        showSuccessSnackbar(
          context,
          LocaleService.instance.tr(
            'تم تحويل صورتك إلى أفاتار ناطق وتفعيله بنجاح ✨',
            'Your photo was transformed into your speaking avatar ✨',
          ),
        );
        _triggerAvatarGreeting();
      } catch (e) {
        if (!mounted) return;
        setState(() => _isGenerating = false);
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر تحويل الصورة إلى أفاتار حالياً، يرجى المحاولة مرة أخرى.',
            'Could not transform photo into avatar right now. Please try again.',
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isGenerating = false);
    }
  }

  void _showAvatarOptionsSheet() {
    final t = LocaleService.instance.tr;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE2E8F0),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  t('تخصيص الأفاتار الشخصي', 'Customize Personal Avatar'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  t(
                    'ارفع صورتك وسيقوم النظام بتحويلها لأفاتار ناطق يتفاعل مع الحوار',
                    'Upload your photo and it will be converted into a speaking avatar that reacts to dialogue',
                  ),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12.5,
                    color: Color(0xFF64748B),
                  ),
                ),
                const SizedBox(height: 18),
                ListTile(
                  leading: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFECFEFF),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.camera_alt_rounded,
                      color: Color(0xFF00B4D8),
                    ),
                  ),
                  title: Text(
                    t('التقاط بالكاميرا', 'Take Photo with Camera'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    _uploadAndTransform(preferCamera: true);
                  },
                ),
                ListTile(
                  leading: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEFF6FF),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.photo_library_rounded,
                      color: Color(0xFF3B82F6),
                    ),
                  ),
                  title: Text(
                    t('اختيار من المعرض', 'Choose from Gallery'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    _uploadAndTransform(preferCamera: false);
                  },
                ),
                const SizedBox(height: 8),
                const Divider(),
                ValueListenableBuilder<bool>(
                  valueListenable: _audioService.use3DModel,
                  builder: (context, use3D, _) {
                    return ListTile(
                      leading: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF0FDF4),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(
                          Icons.view_in_ar_rounded,
                          color: Color(0xFF10B981),
                        ),
                      ),
                      title: Text(
                        t('مجسم الأفاتار ثلاثي الأبعاد (3D Model)', '3D Avatar Model'),
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      subtitle: Text(
                        use3D
                            ? t('مفعل: شخصية 3D حية تتنفس وتنطق', 'Active: Live 3D speaking character')
                            : t('معطل: استخدام صورة الوجه المولدة', 'Inactive: Using generated face photo'),
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF64748B),
                        ),
                      ),
                      trailing: Switch(
                        value: use3D,
                        activeThumbColor: const Color(0xFF10B981),
                        onChanged: (val) {
                          _audioService.setUse3DModel(val);
                          Navigator.of(ctx).pop();
                        },
                      ),
                    );
                  },
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _onAvatarTapped() {
    final avatar = _audioService.activeAvatar.value;
    if (avatar != null && avatar.isGagAvatar) {
      _triggerAvatarGreeting();
    } else {
      _showFirstTimeOrGreetingDialog();
    }
  }

  void _showFirstTimeOrGreetingDialog() {
    final t = LocaleService.instance.tr;
    showDialog(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Row(
            children: [
              const Icon(
                Icons.face_retouching_natural_rounded,
                color: Color(0xFF00B4D8),
              ),
              const SizedBox(width: 8),
              Text(
                t('الأفاتار الذكي', 'Smart Avatar'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w800,
                  fontSize: 17,
                  color: Color(0xFF0F172A),
                ),
              ),
            ],
          ),
          content: Text(
            t(
              'يمكنك التحدث مباشرة مع المساعد، أو تحويل صورتك الشخصية لتصبح أنت الأفاتار الناطق المتفاعل!',
              'You can speak directly with the assistant, or convert your own photo into the animated speaking avatar!',
            ),
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13.5,
              color: Color(0xFF475569),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                _triggerAvatarGreeting();
              },
              child: Text(
                t('تحدث الآن 💬', 'Speak Now 💬'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF00B4D8),
                ),
              ),
            ),
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0F172A),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              onPressed: () {
                Navigator.of(ctx).pop();
                _showAvatarOptionsSheet();
              },
              icon: const Icon(Icons.add_a_photo_rounded, size: 16),
              label: Text(
                t('تحويل صورتي 📸', 'Transform My Photo 📸'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _topCircleBtn({
    required IconData icon,
    required VoidCallback? onTap,
    required String tooltip,
  }) {
    return Tooltip(
      message: tooltip,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.90),
          shape: BoxShape.circle,
          border: Border.all(
            color: Colors.black.withValues(alpha: 0.08),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.08),
              blurRadius: 10,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            customBorder: const CircleBorder(),
            child: Center(
              child: Icon(
                icon,
                color: const Color(0xFF0F172A),
                size: 22,
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: Colors.white,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Full-screen Interactive Avatar Stage
          Positioned.fill(
            child: InteractiveAnimatedAvatar(
              fullScreen: true,
              onAvatarTapped: _onAvatarTapped,
              onAvatarDoubleTapped: _showAvatarOptionsSheet,
              onAvatarLongPress: _showAvatarOptionsSheet,
            ),
          ),

          // 2. Top bar matching user reference image exactly
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Directionality(
                  textDirection: TextDirection.ltr,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Circular Menu Button (Left)
                      _topCircleBtn(
                        icon: Icons.menu_rounded,
                        onTap: _openMenu,
                        tooltip: LocaleService.instance.tr('القائمة', 'Menu'),
                      ),

                      // Circular Notification Bell Button (Right)
                      _topCircleBtn(
                        icon: Icons.notifications_none_rounded,
                        onTap: _handleNotificationsTap,
                        tooltip:
                            LocaleService.instance.tr('الإشعارات', 'Notifications'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // 3. Elegant Loading Overlay during photo transformation
          if (_isGenerating)
            Positioned.fill(
              child: Container(
                color: Colors.black.withValues(alpha: 0.35),
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 20,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.15),
                          blurRadius: 20,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircularProgressIndicator(
                          strokeWidth: 3,
                          valueColor:
                              AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
                        ),
                        const SizedBox(height: 14),
                        Text(
                          LocaleService.instance.tr(
                            'جاري تحويل صورتك إلى أفاتار ناطق...',
                            'Transforming photo to animated avatar...',
                          ),
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
