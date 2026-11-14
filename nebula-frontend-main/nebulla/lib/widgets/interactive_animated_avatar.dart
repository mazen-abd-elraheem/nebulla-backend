import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/audio_viseme_analyzer.dart';

/// Photorealistic Video-Style Talking 3D Cybernetic Avatar.
/// - The avatar stays firmly grounded with natural living video presence.
/// - Organic idle motion: looks gently left and right, subtle breathing, natural speech nods.
/// - Realistic jaw articulation: her ACTUAL lower lip and chin part and move down with speech
///   (no painted or artificial mouth overlay on top of the face!).
/// - Natural organic eye blinking on the actual eye sockets.
/// - Tap to speak greeting; double-tap to switch character appearance.
class InteractiveAnimatedAvatar extends StatefulWidget {
  final String? avatarType; // 'male' or 'female'
  final bool fullScreen;
  final double? width;
  final double? height;
  final VoidCallback? onAvatarTapped;
  final VoidCallback? onAvatarDoubleTapped;

  const InteractiveAnimatedAvatar({
    super.key,
    this.avatarType,
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

  // Animation controllers
  AnimationController? _breathingController;
  Animation<double>? _breathingAnimation;
  AnimationController? _auraPulseController;
  AnimationController? _headMotionController;
  AnimationController? _blinkController;
  Animation<double>? _blinkAnimation;

  Timer? _blinkTimer;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _initControllers();
    _scheduleNextBlink();
  }

  void _initControllers() {
    // 1. Ambient living breathing cycle (4.2 seconds)
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

    // 2. Ambient neural glow pulse
    _auraPulseController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat(reverse: true);

    // 3. Living Video Head Motion (looks right and left, natural subtle nods)
    _headMotionController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    )..repeat(reverse: true);

    // 4. Natural Eye Blinking Controller (130ms quick natural blink)
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
    // Blinks naturally every 2.5 to 4.2 seconds
    final delayMs = 2500 + _random.nextInt(1700);
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

    return ValueListenableBuilder<String>(
      valueListenable: _audioService.activeAvatarType,
      builder: (context, activeType, _) {
        final currentType = widget.avatarType ?? activeType;
        final isFemale = currentType == 'female';
        final assetPath = isFemale
            ? 'assets/images/avatar_female.png'
            : 'assets/images/avatar_male.jpg';

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
                          assetPath: assetPath,
                          isFemale: isFemale,
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
    required String assetPath,
    required bool isFemale,
    required bool isSpeaking,
    required double amplitude,
    required VisemeFrame viseme,
    required String emotion,
  }) {
    final auraColor = _getEmotionColor(emotion, isSpeaking);

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
          onDoubleTap: () {
            final nextType = isFemale ? 'male' : 'female';
            _audioService.switchAvatar(nextType);
            widget.onAvatarDoubleTapped?.call();
          },
          child: AnimatedBuilder(
            animation: Listenable.merge([
              _breathingAnimation!,
              _auraPulseController!,
              _headMotionController!,
              _blinkAnimation!,
            ]),
            builder: (context, child) {
              final imgW = isFemale ? 418.0 : 448.0;
              const imgH = 1024.0;

              // Video-like natural head motion: looks left/right and nods naturally when speaking
              final headT = (_headMotionController?.value ?? 0.5) * 2 * pi;
              final yaw = sin(headT * 0.55) * 0.032; // Smoothly looks right and left
              final pitch = (cos(headT * 0.75) * 0.014) +
                  (isSpeaking ? sin(headT * 3.8) * 0.010 : 0.0); // Natural speech nod
              final roll = sin(headT * 0.35) * 0.006; // Subtle natural head cant

              // Anatomical Lip Seam coordinates where the real lips meet
              final splitY = isFemale ? 553.0 : 562.0;
              final mouthX = isFemale ? 209.0 : 224.0;
              final baseW = isFemale ? 58.0 : 66.0;
              final mouthW = (baseW * viseme.widthRatio).clamp(38.0, 74.0);

              // Downward displacement of her ACTUAL lower lip & chin when speaking
              final jawDrop = isSpeaking
                  ? ((viseme.openness * 4.6) + (amplitude * 2.4)).clamp(0.0, 6.2)
                  : 0.0;

              return Center(
                child: SizedBox(
                  width: portraitW,
                  height: portraitH,
                  child: Stack(
                    alignment: Alignment.center,
                    clipBehavior: Clip.none,
                    children: [
                      // 1. Ambient Cybernetic Energy Glow
                      _buildAmbientGlow(auraColor, isSpeaking, amplitude, portraitW, portraitH),

                      // 2. Character Portrait with 3D Head Tilt & Natural Video-Style Articulation
                      Transform(
                        alignment: const Alignment(0.0, -0.12), // Pivot on neck base
                        transform: Matrix4.identity()
                          ..setEntry(3, 2, 0.0012)
                          ..rotateY(yaw)
                          ..rotateX(pitch)
                          ..rotateZ(roll),
                        child: ClipRRect(
                          borderRadius: widget.fullScreen
                              ? BorderRadius.zero
                              : BorderRadius.circular(28),
                          child: SizedBox(
                            width: portraitW,
                            height: portraitH,
                            child: FittedBox(
                              fit: BoxFit.cover,
                              alignment: isFemale
                                  ? const Alignment(0.0, -0.06)
                                  : const Alignment(0.0, -0.16),
                              child: SizedBox(
                                width: imgW,
                                height: imgH,
                                child: Stack(
                                  alignment: Alignment.center,
                                  children: [
                                    // 2A. Oral Cavity background (Revealed only when real lips part)
                                    if (jawDrop > 0.4)
                                      Positioned(
                                        left: mouthX - (mouthW / 2),
                                        top: splitY - 1.2,
                                        child: Container(
                                          width: mouthW,
                                          height: jawDrop + 2.4,
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF1E070B),
                                            borderRadius: BorderRadius.circular(jawDrop * 0.45),
                                          ),
                                          child: (viseme.teethVisible > 0.15 && jawDrop > 2.0)
                                              ? Align(
                                                  alignment: Alignment.topCenter,
                                                  child: Container(
                                                    margin: const EdgeInsets.only(top: 0.6),
                                                    width: mouthW * 0.62,
                                                    height: min(2.0, jawDrop * 0.38),
                                                    decoration: BoxDecoration(
                                                      color: const Color(0xFFFAF7F4).withValues(
                                                        alpha: (viseme.teethVisible * 0.95)
                                                            .clamp(0.0, 1.0),
                                                      ),
                                                      borderRadius: BorderRadius.circular(1.0),
                                                    ),
                                                  ),
                                                )
                                              : null,
                                        ),
                                      ),

                                    // 2B. Real Upper Face & Lips (From top down to lip seam y=splitY)
                                    // Her real upper lip stays in place
                                    Transform.scale(
                                      scale: 1.0 + (0.008 * (_breathingAnimation?.value ?? 0.0)),
                                      alignment: const Alignment(0.0, 0.25),
                                      child: ClipRect(
                                        clipper: _UpperFaceClipper(splitY: splitY),
                                        child: Image.asset(
                                          assetPath,
                                          width: imgW,
                                          height: imgH,
                                          fit: BoxFit.fill,
                                          errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                        ),
                                      ),
                                    ),

                                    // 2C. Real Lower Jaw & Chin (From lip seam y=splitY down to bottom)
                                    // Displaces downward naturally with speech volume at 50 FPS
                                    Transform.translate(
                                      offset: Offset(0, jawDrop),
                                      child: Transform.scale(
                                        scale: 1.0 + (0.008 * (_breathingAnimation?.value ?? 0.0)),
                                        alignment: const Alignment(0.0, 0.25),
                                        child: ClipRect(
                                          clipper: _LowerFaceClipper(splitY: splitY),
                                          child: Image.asset(
                                            assetPath,
                                            width: imgW,
                                            height: imgH,
                                            fit: BoxFit.fill,
                                            errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                          ),
                                        ),
                                      ),
                                    ),

                                    // 2D. 3D Specular Light Sheen (Shifts across face when looking right/left)
                                    Positioned.fill(
                                      child: IgnorePointer(
                                        child: DecoratedBox(
                                          decoration: BoxDecoration(
                                            gradient: RadialGradient(
                                              center: Alignment(
                                                (-0.18 - yaw * 2.2).clamp(-0.85, 0.85),
                                                (-0.28 - pitch * 1.6).clamp(-0.85, 0.85),
                                              ),
                                              radius: 0.80,
                                              colors: [
                                                Colors.white.withValues(alpha: 0.16),
                                                Colors.white.withValues(alpha: 0.04),
                                                Colors.transparent,
                                              ],
                                              stops: const [0.0, 0.38, 1.0],
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),

                                    // 2E. Natural Eye Blinking (Pure eyelid closure on real eyes, no drawn sticker)
                                    Positioned.fill(
                                      child: CustomPaint(
                                        painter: _NaturalEyeBlinkPainter(
                                          isFemale: isFemale,
                                          blinkProgress: _blinkAnimation?.value ?? 0.0,
                                          yaw: yaw,
                                          pitch: pitch,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),

                      // 3. Sci-Fi Floating Waveform Equalizer when speaking
                      if (isSpeaking)
                        Positioned(
                          bottom: widget.fullScreen ? 94 : 20,
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
    final pulse = isSpeaking ? 0.35 + (amplitude * 0.25) : 0.12 + (pulseVal * 0.08);

    return Container(
      width: w * 0.85,
      height: h * 0.65,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: pulse),
            blurRadius: isSpeaking ? 60 : 35,
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
        color: Colors.white.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: color.withValues(alpha: 0.5),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.25),
            blurRadius: 14,
            offset: const Offset(0, 3),
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

  Widget _buildFallback(bool isFemale) {
    return Container(
      color: const Color(0xFFF8FAFC),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isFemale ? Icons.face_3_rounded : Icons.face_rounded,
              size: 80,
              color: const Color(0xFF00E5FF),
            ),
            const SizedBox(height: 8),
            ValueListenableBuilder<String>(
              valueListenable: _audioService.activePersonaName,
              builder: (context, name, _) => Text(
                name,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF1E293B),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _triggerTapFeedback() {
    final name = _audioService.activePersonaName.value;
    final isFemale = _audioService.activeAvatarType.value == 'female';
    final greeting = isFemale
        ? 'أهلاً بك! أنا $name، جاهزة لمساعدتك في أي استفسار.'
        : 'أهلاً بك! أنا $name، مستعد لمساعدتك وإنجاز مهامك فوراً.';
    _audioService.speak(greeting, emotion: 'happy');
  }

  Color _getEmotionColor(String emotion, bool isSpeaking) {
    switch (emotion) {
      case 'happy':
        return const Color(0xFF00E5FF); // Vibrant Cyan
      case 'curious':
        return const Color(0xFF38BDF8); // Sky Blue
      case 'confident':
        return const Color(0xFF2563EB); // Royal Sapphire
      case 'serious':
        return const Color(0xFF0284C7); // Deep Ocean Blue
      case 'neutral':
      default:
        return const Color(0xFF0EA5E9); // Electric Tech Blue
    }
  }
}

/// Clips the character portrait from top down to the lip seam y=splitY
class _UpperFaceClipper extends CustomClipper<Rect> {
  final double splitY;
  const _UpperFaceClipper({required this.splitY});

  @override
  Rect getClip(Size size) => Rect.fromLTWH(0, 0, size.width, splitY);

  @override
  bool shouldReclip(_UpperFaceClipper oldClipper) => oldClipper.splitY != splitY;
}

/// Clips the character portrait from the lip seam y=splitY down to the bottom
class _LowerFaceClipper extends CustomClipper<Rect> {
  final double splitY;
  const _LowerFaceClipper({required this.splitY});

  @override
  Rect getClip(Size size) => Rect.fromLTWH(0, splitY, size.width, size.height - splitY);

  @override
  bool shouldReclip(_LowerFaceClipper oldClipper) => oldClipper.splitY != splitY;
}

/// Organic, photorealistic eye blinking painter positioned accurately on actual eye sockets
class _NaturalEyeBlinkPainter extends CustomPainter {
  final bool isFemale;
  final double blinkProgress; // 0.0 = open, 1.0 = fully closed
  final double yaw;
  final double pitch;

  _NaturalEyeBlinkPainter({
    required this.isFemale,
    required this.blinkProgress,
    this.yaw = 0.0,
    this.pitch = 0.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (blinkProgress < 0.04) return;

    final parallax = Offset(yaw * 10.0, pitch * 6.0);
    final leftCenter = (isFemale
        ? const Offset(166.0, 416.0)
        : const Offset(158.0, 370.0)) + parallax;
    final rightCenter = (isFemale
        ? const Offset(252.0, 416.0)
        : const Offset(290.0, 370.0)) + parallax;

    final eyeW = isFemale ? 38.0 : 42.0;
    final eyeH = isFemale ? 14.0 : 15.0;

    _paintEyelid(canvas, leftCenter, eyeW, eyeH, blinkProgress, isFemale);
    _paintEyelid(canvas, rightCenter, eyeW, eyeH, blinkProgress, isFemale);
  }

  void _paintEyelid(
    Canvas canvas,
    Offset center,
    double w,
    double h,
    double progress,
    bool female,
  ) {
    final drop = h * progress;
    final topY = center.dy - (h * 0.45);
    final bottomY = topY + drop;

    final rect = Rect.fromLTRB(center.dx - (w / 2), topY, center.dx + (w / 2), bottomY);

    // Natural skin-toned eyelid dome matching real eyelid tone
    final lidPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: female
            ? [
                const Color(0xFFE5D1C3).withValues(alpha: (0.96 * progress).clamp(0.0, 1.0)),
                const Color(0xFFD2B5A5).withValues(alpha: (0.96 * progress).clamp(0.0, 1.0)),
              ]
            : [
                const Color(0xFFD4B8A6).withValues(alpha: (0.96 * progress).clamp(0.0, 1.0)),
                const Color(0xFFBF9C88).withValues(alpha: (0.96 * progress).clamp(0.0, 1.0)),
              ],
      ).createShader(rect)
      ..style = PaintingStyle.fill;

    final path = Path();
    path.moveTo(center.dx - (w * 0.48), topY);
    path.quadraticBezierTo(center.dx, bottomY, center.dx + (w * 0.48), topY);
    path.close();

    canvas.drawPath(path, lidPaint);

    // Subtle natural eyelash line along the lower edge of the closing eyelid
    if (progress > 0.35) {
      final lashPaint = Paint()
        ..color = (female ? const Color(0xFF382A26) : const Color(0xFF281E1C))
            .withValues(alpha: (progress * 0.75).clamp(0.0, 1.0))
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..strokeCap = StrokeCap.round;

      final lashPath = Path();
      lashPath.moveTo(center.dx - (w * 0.46), topY + (drop * 0.85));
      lashPath.quadraticBezierTo(center.dx, bottomY, center.dx + (w * 0.46), topY + (drop * 0.85));
      canvas.drawPath(lashPath, lashPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _NaturalEyeBlinkPainter old) {
    return old.blinkProgress != blinkProgress ||
        old.isFemale != isFemale ||
        old.yaw != yaw ||
        old.pitch != pitch;
  }
}
