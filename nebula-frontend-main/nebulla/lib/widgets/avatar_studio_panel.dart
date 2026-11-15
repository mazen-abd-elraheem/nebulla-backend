import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/theme.dart';
import '../models/avatar_profile.dart';
import '../services/avatar_audio_service.dart';
import '../services/nebula_repository.dart';
import '../utils/avatar_photo_picker.dart';
import 'common_widgets.dart';
import 'interactive_animated_avatar.dart';

/// Unified GAGAvatar Creation, Live Preview, Emoji Expression Tester & Approval/Recreate Panel.
/// Matches the Nebula UI seamlessly in both Dark Onboarding (`darkMode: true`) and Light Profile (`darkMode: false`).
class AvatarStudioPanel extends StatefulWidget {
  final bool darkMode;
  final int? personalityId;
  final String? defaultName;
  final ValueChanged<AvatarProfileModel>? onAvatarApproved;

  const AvatarStudioPanel({
    super.key,
    this.darkMode = true,
    this.personalityId,
    this.defaultName,
    this.onAvatarApproved,
  });

  @override
  State<AvatarStudioPanel> createState() => _AvatarStudioPanelState();
}

class _AvatarStudioPanelState extends State<AvatarStudioPanel> {
  final _repo = NebulaRepository.instance;
  final _audioService = AvatarAudioService.instance;
  final _picker = ImagePicker();

  AvatarProfileModel? _previewAvatar;
  String _selectedStyle = 'realistic';
  bool _isGenerating = false;
  bool _isApproving = false;

  @override
  void initState() {
    super.initState();
    _previewAvatar = _audioService.activeAvatar.value;
  }

  Future<void> _pickAndGenerate(ImageSource source) async {
    try {
      final file = await pickAvatarPhotoFile(
        preferCamera: source == ImageSource.camera,
        picker: _picker,
      );
      if (file == null) return;
      if (!mounted) return;
      setState(() => _isGenerating = true);

      final draft = await _repo.createAvatarFromPhoto(
        photoFile: file,
        name: widget.defaultName,
        personalityId: widget.personalityId,
        style: _selectedStyle,
      );
      if (!mounted) return;
      setState(() {
        _previewAvatar = draft;
        _isGenerating = false;
      });
      showSuccessSnackbar(context, 'تم إنشاء الأفاتار! راجع شكله ولو مش عاجبك اعمل واحد جديد.');
    } catch (e) {
      if (mounted) {
        setState(() => _isGenerating = false);
        showErrorSnackbar(context, 'تعذر إنشاء الأفاتار من الصورة: $e');
      }
    }
  }

  Future<void> _recreateCurrent({ImageSource? newPhotoSource}) async {
    final current = _previewAvatar;
    if (current == null) {
      await _pickAndGenerate(newPhotoSource ?? ImageSource.gallery);
      return;
    }

    File? replacement;
    if (newPhotoSource != null) {
      replacement = await pickAvatarPhotoFile(
        preferCamera: newPhotoSource == ImageSource.camera,
        picker: _picker,
      );
      if (replacement == null) return;
    }

    if (!mounted) return;
    setState(() => _isGenerating = true);
    try {
      final nextStyle = replacement != null
          ? _selectedStyle
          : (_selectedStyle == 'realistic' ? 'studio_3d' : 'realistic');
      _selectedStyle = nextStyle;
      final nextDraft = await _repo.recreateAvatar(
        current.id,
        newPhotoFile: replacement,
        style: nextStyle,
        reason: 'المستخدم طلب نسخة جديدة من الأفاتار',
      );
      if (!mounted) return;
      setState(() {
        _previewAvatar = nextDraft;
        _isGenerating = false;
      });
      showSuccessSnackbar(context, 'تم إنشاء نسخة جديدة (#${nextDraft.attemptNumber}) للمراجعة.');
    } catch (e) {
      if (mounted) {
        setState(() => _isGenerating = false);
        showErrorSnackbar(context, 'تعذر إعادة إنشاء الأفاتار: $e');
      }
    }
  }

  Future<void> _approveCurrent() async {
    final current = _previewAvatar;
    if (current == null) return;

    setState(() => _isApproving = true);
    try {
      final approved = await _repo.approveAvatar(current.id);
      _audioService.setActiveAvatar(approved);
      if (!mounted) return;
      setState(() {
        _previewAvatar = approved;
        _isApproving = false;
      });
      showSuccessSnackbar(context, 'تم اعتماد الأفاتار وتفعيله كوجه التوأم الرقمي!');
      widget.onAvatarApproved?.call(approved);
    } catch (e) {
      if (mounted) {
        setState(() => _isApproving = false);
        showErrorSnackbar(context, 'تعذر اعتماد الأفاتار: $e');
      }
    }
  }

  void _testEmojiSpeech(Map<String, String> item) {
    final emoji = item['emoji']!;
    final expr = item['expr']!;
    final sample = item['sample']!;
    _audioService.speak(
      '$sample $emoji',
      faceEmoji: emoji,
      expression: expr,
      personalityId: widget.personalityId ?? _audioService.activePersonalityId.value,
    );
  }

  @override
  Widget build(BuildContext context) {
    final cardColor = widget.darkMode ? AppColors.card : Colors.white;
    final surfaceColor = widget.darkMode ? AppColors.surface : const Color(0xFFF8FAFC);
    final borderColor = widget.darkMode ? AppColors.cardBorder : const Color(0xFFE2E8F0);
    final titleColor = widget.darkMode ? AppColors.textPrimary : const Color(0xFF0F172A);
    final subColor = widget.darkMode ? AppColors.textSecondary : const Color(0xFF475569);
    final accent = widget.darkMode ? AppColors.teal : const Color(0xFF006677);

    final draft = _previewAvatar;
    final isDraftPending = draft != null && !draft.isActive;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: widget.darkMode ? 0.25 : 0.05),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Top Status Header
          Row(
            children: [
              Icon(Icons.face_retouching_natural_rounded, color: accent, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'توليد الأفاتار بتقنية GAGAvatar',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: titleColor,
                  ),
                ),
              ),
              if (draft != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: (draft.isActive ? const Color(0xFF10B981) : accent)
                        .withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    draft.isActive ? 'معتمد ✓' : 'معاينة #${draft.attemptNumber}',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: draft.isActive ? const Color(0xFF10B981) : accent,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),

          // Live Animated Preview Frame
          Center(
            child: Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: 176,
                  height: 176,
                  child: InteractiveAnimatedAvatar(
                    width: 176,
                    height: 176,
                    overrideAvatar: draft,
                  ),
                ),
                if (_isGenerating)
                  Container(
                    width: 176,
                    height: 176,
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.55),
                      borderRadius: BorderRadius.circular(28),
                    ),
                    child: const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CircularProgressIndicator(strokeWidth: 2.5, color: Color(0xFF00E5FF)),
                          SizedBox(height: 8),
                          Text(
                            'جاري بناء الأفاتار...',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11,
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Style Selector Chips
          Wrap(
            alignment: WrapAlignment.center,
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
                    color: selected
                        ? (widget.darkMode ? Colors.black : Colors.white)
                        : subColor,
                  ),
                ),
                selected: selected,
                selectedColor: accent,
                backgroundColor: surfaceColor,
                side: BorderSide(color: selected ? accent : borderColor),
                onSelected: _isGenerating
                    ? null
                    : (_) => setState(() => _selectedStyle = s['id']!),
              );
            }).toList(),
          ),
          const SizedBox(height: 12),

          // Photo Source Buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isGenerating ? null : () => _pickAndGenerate(ImageSource.camera),
                  icon: Icon(Icons.camera_alt_outlined, size: 17, color: accent),
                  label: Text(
                    'التقاط صورة',
                    style: TextStyle(fontFamily: 'Cairo', fontSize: 12, color: titleColor),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: borderColor),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isGenerating ? null : () => _pickAndGenerate(ImageSource.gallery),
                  icon: Icon(Icons.photo_library_outlined, size: 17, color: accent),
                  label: Text(
                    'رفع صورة',
                    style: TextStyle(fontFamily: 'Cairo', fontSize: 12, color: titleColor),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: borderColor),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          ),

          // Approve / Reject-Recreate Review Actions
          if (draft != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _isGenerating ? null : () => _recreateCurrent(),
                    icon: const Icon(Icons.refresh_rounded, size: 17, color: Color(0xFFF59E0B)),
                    label: Text(
                      'مش عاجبني، إنشاء جديد',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: widget.darkMode ? const Color(0xFFFBBF24) : const Color(0xFFD97706),
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Color(0xFFF59E0B)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
                if (isDraftPending) ...[
                  const SizedBox(width: 8),
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: _isApproving ? null : _approveCurrent,
                      icon: _isApproving
                          ? const SizedBox(
                              width: 15,
                              height: 15,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Icon(
                              Icons.check_circle_outline_rounded,
                              size: 17,
                              color: widget.darkMode ? Colors.black : Colors.white,
                            ),
                      label: Text(
                        'اعتماد الأفاتار',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: widget.darkMode ? Colors.black : Colors.white,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: accent,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],

          // Face Emoji Expression + Voice Test Strip
          const SizedBox(height: 14),
          Text(
            'جرّب تعبيرات الوش بالإيموجي مع الصوت المستنسخ:',
            style: TextStyle(fontFamily: 'Cairo', fontSize: 11, color: subColor),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 6,
            runSpacing: 6,
            children: kAvatarEmojiTests.map((item) {
              return InkWell(
                onTap: () => _testEmojiSpeech(item),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: surfaceColor,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: borderColor),
                  ),
                  child: Text(
                    item['emoji']!,
                    style: const TextStyle(fontSize: 18),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

