import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/avatar_profile.dart';
import '../services/avatar_audio_service.dart';
import '../services/locale_service.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../screens/login_screen.dart';
import '../utils/avatar_photo_picker.dart';
import '../widgets/common_widgets.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';

/// Home screen centered solely around the user's xg-chu/GAGAvatar 3D character.
/// Users upload a portrait photo on Home -> transformed in backend via GAGAvatar ->
/// previewed, tested with face emojis + cloned voice, approved (or regenerated),
/// and set as the app's main speaking character.
class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const DashboardScreen({super.key, this.onNavigate});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with SingleTickerProviderStateMixin {
  final _audioService = AvatarAudioService.instance;
  final _repo = NebulaRepository.instance;
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  AvatarProfileModel? _draftAvatar;
  String _selectedStyle = 'realistic';
  bool _isGenerating = false;
  bool _isApproving = false;
  late final AnimationController _skeletonController;

  @override
  void initState() {
    super.initState();
    _skeletonController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat(reverse: true);
    final user = StorageService.instance.getUser();
    if (user != null && user.fullName.trim().isNotEmpty) {
      _audioService.setPersonaName(user.fullName.trim());
    }
    _audioService.loadActiveAvatar(force: true);
  }

  @override
  void dispose() {
    _skeletonController.dispose();
    super.dispose();
  }

  void _openMenu() {
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

  Future<void> _handleLogout() async {
    final t = LocaleService.instance.translate;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Text(
            t('logout'),
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontWeight: FontWeight.w800,
              fontSize: 18,
              color: Color(0xFF0F172A),
            ),
          ),
          content: Text(
            LocaleService.instance.isArabic
                ? 'هل أنت متأكد من تسجيل الخروج من حسابك؟'
                : 'Are you sure you want to sign out from your account?',
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 14,
              color: Color(0xFF475569),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                t('cancel'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFF64748B),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0F172A),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                elevation: 0,
              ),
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(
                t('logout'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w800,
                  color: Color(0xFFEF4444),
                ),
              ),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && mounted) {
      await StorageService.instance.clearToken();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const LoginScreen()),
          (route) => false,
        );
      }
    }
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
        final draft = await _repo.createAvatarFromPhoto(
          photoFile: file,
          name: _audioService.activePersonaName.value,
          personalityId: _audioService.activePersonalityId.value,
          style: _selectedStyle,
        );
        if (!mounted) return;
        setState(() {
          _draftAvatar = draft;
          _isGenerating = false;
        });
        showSuccessSnackbar(
          context,
          'تم تحويل صورتك إلى أفاتار ثلاثي الأبعاد! جرّب التعبيرات واعتمدها.',
        );
        return;
      } catch (_) {
        // Fallback to unified backend user avatar pipeline (creates, activates & binds to user persona)
        await _repo.generateAvatar(file);
        if (!mounted) return;
        setState(() {
          _draftAvatar = null;
          _isGenerating = false;
        });
        showSuccessSnackbar(
          context,
          'تم تحويل صورتك لأفاتار متحرك وتفعيلها كشخصيتك بنجاح ✨',
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isGenerating = false);
      showErrorSnackbar(context, 'تعذر تحويل الصورة: $e');
    }
  }

  Future<void> _recreateDraft({bool pickNewPhoto = false}) async {
    final target = _draftAvatar ?? _audioService.activeAvatar.value;
    if (target == null) {
      await _uploadAndTransform();
      return;
    }

    if (pickNewPhoto) {
      await _uploadAndTransform();
      return;
    }

    setState(() => _isGenerating = true);
    try {
      final nextStyle =
          _selectedStyle == 'realistic' ? 'studio_3d' : 'realistic';
      _selectedStyle = nextStyle;
      final nextDraft = await _repo.recreateAvatar(
        target.id,
        style: nextStyle,
        reason: 'المستخدم طلب نسخة GAGAvatar جديدة من الرئيسية',
      );
      if (!mounted) return;
      setState(() {
        _draftAvatar = nextDraft;
        _isGenerating = false;
      });
      showSuccessSnackbar(
        context,
        'تم إنشاء نسخة GAGAvatar جديدة (#${nextDraft.attemptNumber}) للمراجعة.',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _isGenerating = false);
      showErrorSnackbar(context, 'تعذر إعادة إنشاء الأفاتار: $e');
    }
  }

  Future<void> _approveDraft() async {
    final draft = _draftAvatar;
    if (draft == null) return;

    setState(() => _isApproving = true);
    try {
      final approved = await _repo.approveAvatar(draft.id);
      _audioService.setActiveAvatar(approved);
      if (!mounted) return;
      setState(() {
        _draftAvatar = null;
        _isApproving = false;
      });
      showSuccessSnackbar(
        context,
        LocaleService.instance.tr(
          'تم اعتماد الأفاتار كشخصيتك الرئيسية في التطبيق!',
          'Avatar approved as your main character!',
        ),
      );
      _triggerAvatarGreeting();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isApproving = false);
      showErrorSnackbar(
        context,
        LocaleService.instance.tr('تعذر اعتماد الأفاتار: $e', 'Could not approve avatar: $e'),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: const Color(0xFF090D16),
      drawer: Drawer(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: NebulaSideMenu(
          activeIndex: 2,
          onNavigate: (idx) {
            _scaffoldKey.currentState?.closeDrawer();
            if (widget.onNavigate != null && idx >= 0) {
              widget.onNavigate!(idx);
            }
          },
          onClose: () => _scaffoldKey.currentState?.closeDrawer(),
        ),
      ),
      body: ValueListenableBuilder<AvatarProfileModel?>(
        valueListenable: _audioService.activeAvatar,
        builder: (context, activeAvatar, _) {
          final displayAvatar = _draftAvatar ?? activeAvatar;
          final hasActive = activeAvatar != null && activeAvatar.isGagAvatar;
          final isReviewingDraft =
              _draftAvatar != null && !_draftAvatar!.isActive;

          return Stack(
            fit: StackFit.expand,
            children: [
              // 1. Subtle radial ambient backdrop behind the 3D character
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    center: const Alignment(0, -0.25),
                    radius: 1.1,
                    colors: [
                      const Color(0xFF6366F1).withValues(alpha: 0.14),
                      const Color(0xFF0F172A),
                      const Color(0xFF090D16),
                    ],
                  ),
                ),
              ),

              // 2. Full-screen GAGAvatar character stage
              Positioned.fill(
                child: InteractiveAnimatedAvatar(
                  fullScreen: true,
                  overrideAvatar: displayAvatar,
                  onAvatarTapped:
                      displayAvatar != null ? _triggerAvatarGreeting : () => _uploadAndTransform(),
                ),
              ),

              // 3. Top Glass Header Bar
              SafeArea(
                child: Align(
                  alignment: Alignment.topCenter,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    child: Directionality(
                      textDirection: TextDirection.ltr,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          _topIconBtn(
                            icon: Icons.menu_rounded,
                            onTap: _openMenu,
                            tooltip: 'القائمة',
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                            decoration: BoxDecoration(
                              color: const Color(0xFF0F172A).withValues(alpha: 0.85),
                              borderRadius: BorderRadius.circular(24),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.08),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                    color: hasActive
                                        ? AppColors.success
                                        : (isReviewingDraft
                                            ? AppColors.warning
                                            : AppColors.teal),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  isReviewingDraft
                                      ? LocaleService.instance.tr(
                                          'معاينة الأفاتار #${_draftAvatar!.attemptNumber}',
                                          'Avatar Preview #${_draftAvatar!.attemptNumber}',
                                        )
                                      : (hasActive
                                          ? LocaleService.instance.tr(
                                              'الأفاتار التفاعلي • الشخصية الرئيسية',
                                              '3D Avatar • Main Character',
                                            )
                                          : LocaleService.instance.tr(
                                              'استوديو الأفاتار',
                                              'Avatar Studio',
                                            )),
                                  style: const TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              _topIconBtn(
                                icon: Icons.add_a_photo_rounded,
                                onTap: _isGenerating ? null : () => _uploadAndTransform(),
                                tooltip: 'رفع صورة جديدة',
                              ),
                              const SizedBox(width: 8),
                              _topIconBtn(
                                icon: Icons.notifications_none_rounded,
                                onTap: () {
                                  showSuccessSnackbar(
                                    context,
                                    hasActive
                                        ? 'أفاتار GAGAvatar نشط ومرتبط بالصوت المستنسخ وتعبيرات الإيموجي.'
                                        : 'ارفع صورتك الآن لبناء شخصيتك بنموذج GAGAvatar.',
                                  );
                                },
                                tooltip: 'الحالة',
                              ),
                              const SizedBox(width: 8),
                              _topIconBtn(
                                icon: Icons.logout_rounded,
                                onTap: _handleLogout,
                                tooltip: 'تسجيل الخروج',
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              // 4. Bottom GAGAvatar Studio / Review / Expression Dock (clears GlobalNebulaFooter)
              SafeArea(
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 90),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 540),
                      child: _buildBottomDock(
                        hasActive: hasActive,
                        isReviewingDraft: isReviewingDraft,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _topIconBtn({
    required IconData icon,
    required VoidCallback? onTap,
    required String tooltip,
  }) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: const Color(0xFF0F172A).withValues(alpha: 0.85),
        shape: CircleBorder(
          side: BorderSide(color: Colors.white.withValues(alpha: 0.10)),
        ),
        child: InkWell(
          onTap: onTap,
          customBorder: const CircleBorder(),
          child: SizedBox(
            width: 44,
            height: 44,
            child: Icon(icon, color: AppColors.textPrimary, size: 22),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomDock({
    required bool hasActive,
    required bool isReviewingDraft,
  }) {
    if (_isGenerating) {
      return AnimatedBuilder(
        animation: _skeletonController,
        builder: (context, _) {
          final pulse = 0.35 + (_skeletonController.value * 0.45);
          return _dockContainer(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.auto_awesome_rounded,
                      color: AppColors.teal.withValues(alpha: pulse + 0.2),
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'جاري تتبع الملامح وبناء الشخصية بـ GAGAvatar...',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    height: 10,
                    color: const Color(0xFF1E293B),
                    child: FractionallySizedBox(
                      alignment: Alignment.centerLeft,
                      widthFactor: 0.35 + (_skeletonController.value * 0.55),
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              AppColors.teal.withValues(alpha: 0.6),
                              const Color(0xFF818CF8),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'تجهيز التعبيرات الـ 12 وحركات الفم الثلاثية الأبعاد...',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          );
        },
      );
    }

    if (isReviewingDraft) {
      return _dockContainer(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.verified_user_outlined, color: AppColors.teal, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    LocaleService.instance.tr(
                      'راجع الأفاتار (#${_draftAvatar!.attemptNumber}) قبل الاعتماد',
                      'Review Avatar (#${_draftAvatar!.attemptNumber}) before approving',
                    ),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _recreateDraft(),
                    icon: const Icon(Icons.refresh_rounded, size: 17, color: AppColors.warning),
                    label: const Text(
                      'مش عاجبني، جديد',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: AppColors.warning,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(color: AppColors.warning.withValues(alpha: 0.65)),
                      padding: const EdgeInsets.symmetric(vertical: 11),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: ElevatedButton.icon(
                    onPressed: _isApproving ? null : _approveDraft,
                    icon: const Icon(Icons.check_circle_rounded, size: 18, color: Colors.black),
                    label: Text(
                      _isApproving ? 'جاري الاعتماد...' : 'اعتماد كشخصية رئيسية',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.black,
                      ),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.teal,
                      padding: const EdgeInsets.symmetric(vertical: 11),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      );
    }

    if (hasActive) {
      return _dockContainer(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _uploadAndTransform(),
                icon: const Icon(Icons.photo_library_outlined, size: 16, color: AppColors.teal),
                label: Text(
                  LocaleService.instance.tr('رفع صورة جديدة', 'Upload New Photo'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: AppColors.textPrimary,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  side: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
                  padding: const EdgeInsets.symmetric(vertical: 9),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _triggerAvatarGreeting,
                icon: const Icon(Icons.record_voice_over_rounded, size: 16, color: Colors.black),
                label: Text(
                  LocaleService.instance.tr('تحدث الآن', 'Speak Now'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: Colors.black,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.teal,
                  padding: const EdgeInsets.symmetric(vertical: 9),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
          ],
        ),
      );
    }

    // Empty State: Guide user right on Home Screen to upload their photo
    return _dockContainer(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Row(
            children: [
              Icon(Icons.face_retouching_natural_rounded, color: AppColors.teal, size: 20),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'أنشئ شخصيتك الرئيسية بنموذج GAGAvatar',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'ارفع صورة واضحة لوجهك، وهنحولها لأفاتار 3D ناطق بيتفاعل بتعبيرات الإيموجي وحركة الشفايف.',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 11.5,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: kAvatarStyles.map((s) {
              final selected = _selectedStyle == s['id'];
              return ChoiceChip(
                label: Text(
                  s['label']!,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                    color: selected ? Colors.black : AppColors.textSecondary,
                  ),
                ),
                selected: selected,
                selectedColor: AppColors.teal,
                backgroundColor: const Color(0xFF1E293B),
                side: BorderSide(
                  color: selected ? AppColors.teal : Colors.white.withValues(alpha: 0.10),
                ),
                onSelected: (_) => setState(() => _selectedStyle = s['id']!),
              );
            }).toList(),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                flex: 2,
                child: ElevatedButton.icon(
                  onPressed: () => _uploadAndTransform(),
                  icon: const Icon(Icons.upload_rounded, size: 18, color: Colors.black),
                  label: const Text(
                    'ارفع صورتك وحوّلها الآن',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: Colors.black,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _uploadAndTransform(preferCamera: true),
                icon: const Icon(Icons.camera_alt_outlined, size: 18, color: AppColors.teal),
                label: const Text(
                  'كاميرا',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: AppColors.textPrimary,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  side: BorderSide(color: Colors.white.withValues(alpha: 0.14)),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _dockContainer({
    required Widget child,
    EdgeInsetsGeometry padding = const EdgeInsets.all(16),
  }) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A).withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.10),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF6366F1).withValues(alpha: 0.12),
            blurRadius: 28,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
