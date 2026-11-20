import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/avatar_profile.dart';
import '../services/api_service.dart';
import '../services/avatar_audio_service.dart';
import '../services/audio_viseme_analyzer.dart';
import '../services/storage_service.dart';

/// Interactive neural avatar powered solely by xg-chu/GAGAvatar.
///
/// Renders backend-generated 3D Gaussian Splatting frames driven by FLAME
/// expression codes, neural eye-blink states, and neural jaw-opening levels
/// synced to VoiceTut cloned speech (zero synthetic Canvas mouth/eyelid overlays).
class InteractiveAnimatedAvatar extends StatefulWidget {
  final String? avatarType;
  final AvatarProfileModel? overrideAvatar;
  final bool fullScreen;
  final double? width;
  final double? height;
  final VoidCallback? onAvatarTapped;
  final VoidCallback? onAvatarDoubleTapped;
  final VoidCallback? onAvatarLongPress;

  const InteractiveAnimatedAvatar({
    super.key,
    this.avatarType,
    this.overrideAvatar,
    this.fullScreen = false,
    this.width,
    this.height,
    this.onAvatarTapped,
    this.onAvatarDoubleTapped,
    this.onAvatarLongPress,
  });

  @override
  State<InteractiveAnimatedAvatar> createState() =>
      _InteractiveAnimatedAvatarState();
}

class _InteractiveAnimatedAvatarState extends State<InteractiveAnimatedAvatar>
    with TickerProviderStateMixin {
  final _audioService = AvatarAudioService.instance;

  AnimationController? _breathingController;
  Animation<double>? _breathingAnimation;
  AnimationController? _auraPulseController;
  AnimationController? _headMotionController;
  AnimationController? _blinkController;
  Animation<double>? _blinkAnimation;

  Timer? _blinkTimer;
  final Random _random = Random();
  String? _precachedKey;

  @override
  void initState() {
    super.initState();
    _initControllers();
    _scheduleNextBlink();
    _audioService.initializeFromStorage();
    unawaited(_audioService.loadActiveAvatar(force: true));
  }

  void _initControllers() {
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4200),
    );

    _breathingAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _breathingController!,
        curve: Curves.easeInOutSine,
      ),
    );

    _auraPulseController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );

    _headMotionController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    );

    _blinkController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 130),
    );

    _blinkAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _blinkController!,
        curve: Curves.easeInOutQuad,
      ),
    );
  }

  void _scheduleNextBlink() {
    _blinkTimer?.cancel();
    final delayMs = 2400 + _random.nextInt(1600);
    _blinkTimer = Timer(Duration(milliseconds: delayMs), () {
      if (!mounted || _blinkController == null) return;
      _blinkController!.forward(from: 0.0).then((_) {
        if (!mounted || _blinkController == null) return;
        _blinkController!.reverse().then((_) {
          if (mounted) _scheduleNextBlink();
        });
      });
    });
  }

  /// Precache GAGAvatar expression, blink, and mouth-level frames for gapless 60fps animation.
  void _ensurePrecached(AvatarProfileModel avatar) {
    final key = '${avatar.id}_${avatar.updatedAt ?? ""}_${avatar.attemptNumber}';
    if (_precachedKey == key) return;
    _precachedKey = key;

    final urls = <String>{
      if (avatar.previewUrl.isNotEmpty) avatar.withCacheBust(avatar.previewUrl),
      if (avatar.blinkSpriteUrl != null && avatar.blinkSpriteUrl!.isNotEmpty)
        avatar.withCacheBust(avatar.blinkSpriteUrl!),
      for (final s in avatar.sprites.values) avatar.withCacheBust(s),
      for (final list in avatar.mouthFrames.values)
        for (final m in list) avatar.withCacheBust(m),
    };

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      for (final rel in urls) {
        if (rel.isEmpty) continue;
        final resolved = ApiService.instance.resolveUrl(rel);
        unawaited(precacheImage(NetworkImage(resolved), context).catchError((_) {}));
      }
    });
  }

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _breathingController?.dispose();
    _auraPulseController?.dispose();
    _headMotionController?.dispose();
    _blinkController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _initControllers();

    return ValueListenableBuilder<AvatarProfileModel?>(
      valueListenable: _audioService.activeAvatar,
      builder: (context, globalAvatar, _) {
        final effectiveAvatar = widget.overrideAvatar ?? globalAvatar;
        if (effectiveAvatar != null && effectiveAvatar.isGagAvatar) {
          _ensurePrecached(effectiveAvatar);
        }

        return ValueListenableBuilder<bool>(
          valueListenable: _audioService.isSpeaking,
          builder: (context, isSpeaking, _) {
            return ValueListenableBuilder<double>(
              valueListenable: _audioService.speechAmplitude,
              builder: (context, amplitude, _) {
                return ValueListenableBuilder<VisemeFrame>(
                  valueListenable: _audioService.currentViseme,
                  builder: (context, viseme, _) {
                    return ValueListenableBuilder<String>(
                      valueListenable: _audioService.currentEmotion,
                      builder: (context, emotion, _) {
                        return _buildAvatarContent(
                          avatar: effectiveAvatar,
                          isSpeaking: isSpeaking,
                          amplitude: amplitude,
                          viseme: viseme,
                          emotion: emotion,
                        );
                      },
                    );
                  },
                );
              },
            );
          },
        );
      },
    );
  }

  Widget _buildAvatarContent({
    AvatarProfileModel? avatar,
    required bool isSpeaking,
    required double amplitude,
    required VisemeFrame viseme,
    required String emotion,
  }) {
    final auraColor = _getEmotionColor(emotion);
    final hasGagAvatar =
        avatar != null && avatar.isGagAvatar && avatar.previewUrl.isNotEmpty;

    final effOpen = isSpeaking ? max(viseme.openness, amplitude * 0.95) : 0.0;
    final int mouthLevel = !isSpeaking
        ? 0
        : (effOpen >= 0.65
            ? 3
            : (effOpen >= 0.34 ? 2 : (effOpen >= 0.10 ? 1 : 0)));

    return LayoutBuilder(
      builder: (context, constraints) {
        final availableW = widget.width ?? constraints.maxWidth;
        final availableH = widget.height ?? constraints.maxHeight;
        final isWide = availableW > 540;
        final portraitW = widget.fullScreen
            ? (isWide ? min(availableW, 500.0) : availableW)
            : min(availableW, 420.0);
        final portraitH = availableH;

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            if (widget.onAvatarTapped != null) {
              widget.onAvatarTapped!();
            } else {
              _triggerTapFeedback();
            }
          },
          onDoubleTap: widget.onAvatarDoubleTapped,
          onLongPress: widget.onAvatarLongPress,
          child: AnimatedBuilder(
            animation: _blinkAnimation!,
            builder: (context, _) {
              String? frameUrl;
              if (hasGagAvatar) {
                final blinkVal = _blinkAnimation?.value ?? 0.0;
                final isBlinking =
                    !isSpeaking &&
                    blinkVal > 0.32 &&
                    (avatar.blinkSpriteUrl?.isNotEmpty ?? false);
                final relPath = avatar.frameForState(
                  emotion: emotion,
                  mouthLevel: mouthLevel,
                  blinking: isBlinking,
                );
                frameUrl = ApiService.instance.resolveUrl(relPath);
              }

              return Center(
                child: SizedBox(
                  width: portraitW,
                  height: portraitH,
                  child: Stack(
                    alignment: Alignment.center,
                    clipBehavior: Clip.none,
                    children: [
                      // Completely locked, stationary avatar portrait and background
                      ClipRRect(
                        borderRadius: widget.fullScreen
                            ? BorderRadius.zero
                            : BorderRadius.circular(24),
                        child: SizedBox(
                          width: portraitW,
                          height: portraitH,
                          child: Stack(
                            fit: StackFit.expand,
                            children: [
                              if (frameUrl != null)
                                Image.network(
                                  frameUrl,
                                  fit: BoxFit.cover,
                                  alignment: Alignment.center,
                                  gaplessPlayback: true,
                                  errorBuilder: (_, _, _) =>
                                      _buildNoAvatarPlaceholder(auraColor),
                                )
                              else
                                _buildNoAvatarPlaceholder(auraColor),
                              if (widget.fullScreen)
                                DecoratedBox(
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: [
                                        Colors.transparent,
                                        Colors.transparent,
                                        Colors.white.withValues(alpha: 0.20),
                                      ],
                                      stops: const [0.0, 0.75, 1.0],
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildNoAvatarPlaceholder(Color auraColor) {
    // 1. If backend avatar URL exists or default to backend avatar 7
    final userAvatarUrl = StorageService.instance.getUserAvatarUrl() ?? '/api/v1/avatar/7/preview';
    final resolved = ApiService.instance.resolveUrl(userAvatarUrl);
    return ColoredBox(
      color: Colors.white,
      child: Image.network(
        resolved,
        fit: BoxFit.cover,
        alignment: Alignment.center,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) {
          // 2. If network image fails, fallback to local saved photo
          final userAvatarPath = StorageService.instance.getUserAvatarPath();
          if (userAvatarPath != null && File(userAvatarPath).existsSync()) {
            return Image.file(
              File(userAvatarPath),
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
            );
          }
          return const ColoredBox(color: Colors.white);
        },
      ),
    );
  }

  void _triggerTapFeedback() {
    final name = _audioService.activePersonaName.value;
    _audioService.speak(
      'أهلاً بك! أنا $name، جاهز لمساعدتك بالصوت والتعبيرات الحية.',
      faceEmoji: '😊',
      expression: 'happy',
    );
  }

  Color _getEmotionColor(String emotion) {
    switch (emotion) {
      case 'happy':
      case 'wave':
      case 'like':
        return const Color(0xFF00E5FF);
      case 'laugh':
        return const Color(0xFF10B981);
      case 'love':
        return const Color(0xFFF472B6);
      case 'surprised':
        return const Color(0xFFF59E0B);
      case 'angry':
        return const Color(0xFFEF4444);
      case 'sad':
      case 'sleepy':
        return const Color(0xFF818CF8);
      case 'thinking':
        return const Color(0xFF38BDF8);
      default:
        return AppColors.teal;
    }
  }
}

/// Shared circular/rounded thumbnail displaying the active GAGAvatar character.
class ActiveAvatarThumb extends StatelessWidget {
  final double size;
  final double radius;
  final bool showBorder;
  final Color? borderColor;

  const ActiveAvatarThumb({
    super.key,
    this.size = 44,
    this.radius = 22,
    this.showBorder = true,
    this.borderColor,
  });

  @override
  Widget build(BuildContext context) {
    final audio = AvatarAudioService.instance;
    return ValueListenableBuilder<AvatarProfileModel?>(
      valueListenable: audio.activeAvatar,
      builder: (context, avatar, _) {
        final hasAvatar =
            avatar != null && avatar.isGagAvatar && avatar.previewUrl.isNotEmpty;
        final imgUrl =
            hasAvatar ? ApiService.instance.resolveUrl(avatar.previewUrl) : null;

        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(radius),
            color: const Color(0xFF0F172A),
            border: showBorder
                ? Border.all(
                    color: borderColor ?? AppColors.teal.withValues(alpha: 0.6),
                    width: 1.4,
                  )
                : null,
          ),
          clipBehavior: Clip.antiAlias,
          child: imgUrl != null
              ? Image.network(
                  imgUrl,
                  fit: BoxFit.cover,
                  gaplessPlayback: true,
                  errorBuilder: (_, _, _) => Icon(
                    Icons.face_retouching_natural_rounded,
                    color: AppColors.teal,
                    size: size * 0.55,
                  ),
                )
              : Icon(
                  Icons.face_retouching_natural_rounded,
                  color: AppColors.teal,
                  size: size * 0.55,
                ),
        );
      },
    );
  }
}
