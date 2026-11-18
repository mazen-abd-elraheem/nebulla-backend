import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/avatar_profile.dart';
import '../services/api_service.dart';
import '../services/avatar_audio_service.dart';
import '../services/audio_viseme_analyzer.dart';

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

  const InteractiveAnimatedAvatar({
    super.key,
    this.avatarType,
    this.overrideAvatar,
    this.fullScreen = false,
    this.width,
    this.height,
    this.onAvatarTapped,
    this.onAvatarDoubleTapped,
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
    unawaited(_audioService.loadActiveAvatar());
  }

  void _initControllers() {
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4200),
    )..repeat(reverse: true);

    _breathingAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _breathingController!,
        curve: Curves.easeInOutSine,
      ),
    );

    _auraPulseController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat(reverse: true);

    _headMotionController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    )..repeat(reverse: true);

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
        final portraitW = widget.fullScreen ? availableW : min(availableW, 420.0);
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
          child: AnimatedBuilder(
            animation: Listenable.merge([
              _breathingAnimation!,
              _auraPulseController!,
              _headMotionController!,
              _blinkAnimation!,
            ]),
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

              final headT = (_headMotionController?.value ?? 0.5) * 2 * pi;
              final breathVal = _breathingAnimation?.value ?? 0.0;
              final speakBoost = isSpeaking ? (1.0 + amplitude * 0.85) : 1.0;
              final yaw = sin(headT * 0.7) * 0.045 * speakBoost;
              final pitch = (cos(headT * 0.9) * 0.025) +
                  (isSpeaking ? sin(headT * 4.2) * (0.018 + amplitude * 0.022) : 0.0);
              final roll = sin(headT * 0.5) * 0.018;
              final floatY = (breathVal - 0.5) * -5.0 -
                  (isSpeaking ? amplitude * 3.5 : 0.0);

              return Center(
                child: SizedBox(
                  width: portraitW,
                  height: portraitH,
                  child: Stack(
                    alignment: Alignment.center,
                    clipBehavior: Clip.none,
                    children: [
                      _buildAmbientGlow(auraColor, isSpeaking, amplitude, portraitW, portraitH),
                      Transform.translate(
                        offset: Offset(0, floatY),
                        child: Transform(
                          alignment: const Alignment(0.0, -0.12), // Pivot on neck base
                          transform: Matrix4.identity()
                            ..setEntry(3, 2, 0.0012)
                            ..rotateY(yaw)
                            ..rotateX(pitch)
                            ..rotateZ(roll),
                          child: ClipRRect(
                            borderRadius: widget.fullScreen
                                ? BorderRadius.zero
                                : BorderRadius.circular(24),
                            child: SizedBox(
                              width: portraitW,
                              height: portraitH,
                              child: frameUrl != null
                                  ? Transform.scale(
                                      scale: 1.02 +
                                          (0.018 * breathVal) +
                                          (isSpeaking ? amplitude * 0.022 : 0.0),
                                      alignment: const Alignment(0.0, 0.1),
                                      child: Stack(
                                        fit: StackFit.expand,
                                        children: [
                                          Image.network(
                                            frameUrl,
                                            fit: BoxFit.cover,
                                            alignment: Alignment.center,
                                            gaplessPlayback: true,
                                            errorBuilder: (_, _, _) =>
                                                _buildNoAvatarPlaceholder(auraColor),
                                          ),
                                          if (widget.fullScreen)
                                            DecoratedBox(
                                              decoration: BoxDecoration(
                                                gradient: LinearGradient(
                                                  begin: Alignment.topCenter,
                                                  end: Alignment.bottomCenter,
                                                  colors: [
                                                    Colors.transparent,
                                                    Colors.transparent,
                                                    AppColors.bg.withValues(alpha: 0.88),
                                                  ],
                                                  stops: const [0.0, 0.68, 1.0],
                                                ),
                                              ),
                                            ),
                                        ],
                                      ),
                                    )
                                  : _buildNoAvatarPlaceholder(auraColor),
                            ),
                          ),
                        ),
                      ),
                      if (isSpeaking && hasGagAvatar)
                        Positioned(
                          bottom: widget.fullScreen ? 210 : 14,
                          child: _buildSpeechWaveform(auraColor, amplitude),
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

  Widget _buildAmbientGlow(
      Color color, bool isSpeaking, double amplitude, double w, double h) {
    final pulseVal = _auraPulseController?.value ?? 0.5;
    final pulse = isSpeaking ? 0.32 + (amplitude * 0.22) : 0.10 + (pulseVal * 0.06);

    return Container(
      width: w * 0.82,
      height: h * 0.62,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: pulse),
            blurRadius: isSpeaking ? 64 : 40,
            spreadRadius: isSpeaking ? 16 : 6,
          ),
        ],
      ),
    );
  }

  Widget _buildSpeechWaveform(Color color, double amplitude) {
    final pulseVal = _auraPulseController?.value ?? 0.5;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A).withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.14),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.28),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(7, (i) {
          final wave = sin((i * 0.7) + (pulseVal * pi * 2.5)).abs();
          final barHeight = 5.0 + (wave * amplitude * 18.0);
          return Container(
            margin: const EdgeInsets.symmetric(horizontal: 2.0),
            width: 3.0,
            height: barHeight,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(3),
            ),
          );
        }),
      ),
    );
  }

  Widget _buildNoAvatarPlaceholder(Color auraColor) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF090D16),
            const Color(0xFF0F172A),
            auraColor.withValues(alpha: 0.14),
          ],
        ),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 92,
                height: 92,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF1E293B).withValues(alpha: 0.85),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
                    width: 1.2,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: auraColor.withValues(alpha: 0.22),
                      blurRadius: 28,
                    ),
                  ],
                ),
                child: Icon(
                  Icons.face_retouching_natural_rounded,
                  size: 42,
                  color: auraColor,
                ),
              ),
              const SizedBox(height: 16),
              ValueListenableBuilder<String>(
                valueListenable: _audioService.activePersonaName,
                builder: (context, name, _) => Text(
                  name,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                'ارفع صورتك لتحويلها لشخصية 3D بنموذج GAGAvatar',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12.5,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
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
