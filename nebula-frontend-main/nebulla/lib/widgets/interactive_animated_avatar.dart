import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';

/// Full interactive animated cybernetic avatar.
/// - Full-screen edge-to-edge portrait framing for the female & male avatar.
/// - The base character portrait stays steady and firmly grounded (no sliding/shaking of the photo).
/// - Natural organic eye blinking on the actual eye sockets.
/// - Dynamic lip-sync and mouth articulation directly on the character's lips when speaking.
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
    // 1. Ambient living pulse (4 seconds)
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4000),
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
      duration: const Duration(milliseconds: 1400),
    )..repeat(reverse: true);

    // 3. Natural Eye Blinking Controller (150ms organic eyelid close & open)
    _blinkController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 150),
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
    // Blinks naturally every 2.6 to 4.2 seconds
    final delayMs = 2600 + _random.nextInt(1600);
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
                return ValueListenableBuilder<String>(
                  valueListenable: _audioService.currentEmotion,
                  builder: (context, emotion, _) {
                    return _buildAvatarContent(
                      assetPath: assetPath,
                      isFemale: isFemale,
                      isSpeaking: isSpeaking,
                      amplitude: amplitude,
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
  }

  Widget _buildAvatarContent({
    required String assetPath,
    required bool isFemale,
    required bool isSpeaking,
    required double amplitude,
    required String emotion,
  }) {
    final auraColor = _getEmotionColor(emotion, isSpeaking);

    return LayoutBuilder(
      builder: (context, constraints) {
        final availableW = widget.width ?? constraints.maxWidth;
        final availableH = widget.height ?? constraints.maxHeight;

        // Take full width & height when fullScreen is active
        final portraitW = widget.fullScreen ? availableW : min(availableW, 420.0);
        final portraitH = availableH;

        return GestureDetector(
          onTap: () {
            _triggerTapFeedback();
            widget.onAvatarTapped?.call();
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
              _blinkAnimation!,
            ]),
            builder: (context, child) {
              final imgW = isFemale ? 418.0 : 448.0;
              const imgH = 1024.0;

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

                      // 2. Character Portrait: Solidly Framed & Grounded (Base Image is Stationary)
                      ClipRRect(
                        borderRadius: widget.fullScreen
                            ? BorderRadius.zero
                            : BorderRadius.circular(28),
                        child: SizedBox(
                          width: portraitW,
                          height: portraitH,
                          child: FittedBox(
                            fit: BoxFit.cover,
                            alignment: isFemale
                                ? const Alignment(0.0, -0.10)
                                : const Alignment(0.0, -0.22),
                            child: SizedBox(
                              width: imgW,
                              height: imgH,
                              child: Stack(
                                alignment: Alignment.center,
                                children: [
                                  // Base Character Image (Solid, Clean, Stationary)
                                  Image.asset(
                                    assetPath,
                                    width: imgW,
                                    height: imgH,
                                    fit: BoxFit.fill,
                                    errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                  ),

                                  // Natural Organic Eye Blinking (Positioned exactly on eye sockets in 1:1 image space)
                                  Positioned.fill(
                                    child: CustomPaint(
                                      painter: _RealisticEyelidPainter(
                                        isFemale: isFemale,
                                        blinkProgress: _blinkAnimation?.value ?? 0.0,
                                      ),
                                    ),
                                  ),

                                  // Dynamic Lip-Sync Mouth Movement (Positioned exactly on lips when speaking)
                                  Positioned.fill(
                                    child: CustomPaint(
                                      painter: _NaturalMouthSpeakingPainter(
                                        isFemale: isFemale,
                                        mouthOpenProgress: isSpeaking ? amplitude : 0.0,
                                      ),
                                    ),
                                  ),

                                  // Subtle bottom gradient fade to white
                                  Positioned.fill(
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        gradient: LinearGradient(
                                          begin: Alignment.topCenter,
                                          end: Alignment.bottomCenter,
                                          colors: [
                                            Colors.transparent,
                                            Colors.transparent,
                                            Colors.white.withValues(alpha: 0.85),
                                          ],
                                          stops: const [0.0, 0.78, 1.0],
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

/// Organic, photorealistic eye blinking painter matching the avatar's eye positions in 1:1 image coordinates
class _RealisticEyelidPainter extends CustomPainter {
  final bool isFemale;
  final double blinkProgress; // 0.0 = open, 1.0 = fully closed

  _RealisticEyelidPainter({
    required this.isFemale,
    required this.blinkProgress,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (blinkProgress < 0.04) return;

    // Exact center coordinates in 1:1 image pixel space (1024h)
    final leftCenter = isFemale
        ? const Offset(166.0, 422.0)
        : const Offset(160.0, 368.0);
    final rightCenter = isFemale
        ? const Offset(252.0, 422.0)
        : const Offset(290.0, 368.0);

    final eyeW = isFemale ? 42.0 : 48.0;
    final eyeH = isFemale ? 18.0 : 20.0;

    final lidColor = isFemale ? const Color(0xFFE8D4C8) : const Color(0xFFD6B5A2);
    final shadowColor = isFemale ? const Color(0xFFC49F8E) : const Color(0xFFAC8775);

    _paintSingleEye(canvas, leftCenter, eyeW, eyeH, lidColor, shadowColor);
    _paintSingleEye(canvas, rightCenter, eyeW, eyeH, lidColor, shadowColor);
  }

  void _paintSingleEye(
    Canvas canvas,
    Offset center,
    double w,
    double h,
    Color lid,
    Color shadow,
  ) {
    final drop = h * blinkProgress * 1.05;
    final rect = Rect.fromCenter(center: center, width: w, height: h);

    final path = Path();
    path.moveTo(rect.left, center.dy - (h * 0.35));
    path.quadraticBezierTo(
      center.dx,
      center.dy - (h * 0.35) + drop,
      rect.right,
      center.dy - (h * 0.35),
    );
    path.quadraticBezierTo(
      center.dx,
      center.dy - (h * 0.35) + (drop * 0.78),
      rect.left,
      center.dy - (h * 0.35),
    );
    path.close();

    final paint = Paint()
      ..color = lid.withValues(alpha: (0.95 * blinkProgress).clamp(0.0, 1.0))
      ..style = PaintingStyle.fill;
    canvas.drawPath(path, paint);

    final linePaint = Paint()
      ..color = shadow.withValues(alpha: (0.75 * blinkProgress).clamp(0.0, 1.0))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(path, linePaint);
  }

  @override
  bool shouldRepaint(covariant _RealisticEyelidPainter old) {
    return old.blinkProgress != blinkProgress || old.isFemale != isFemale;
  }
}

/// Organic, photorealistic mouth speaking painter directly on lips in 1:1 image coordinates
class _NaturalMouthSpeakingPainter extends CustomPainter {
  final bool isFemale;
  final double mouthOpenProgress; // 0.0 = closed, 1.0 = fully open

  _NaturalMouthSpeakingPainter({
    required this.isFemale,
    required this.mouthOpenProgress,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (mouthOpenProgress < 0.06) return;

    // Exact center coordinates in 1:1 image pixel space (1024h)
    final mouthCenter = isFemale
        ? const Offset(209.0, 554.0)
        : const Offset(224.0, 598.0);

    final mouthW = isFemale ? 66.0 : 78.0;
    final maxOpenH = isFemale ? 10.5 : 12.0;
    final openH = (mouthOpenProgress * maxOpenH).clamp(1.5, maxOpenH);

    final mouthRect = Rect.fromCenter(
      center: mouthCenter,
      width: mouthW * (1.0 - (mouthOpenProgress * 0.06)),
      height: openH,
    );

    // 1. Inner mouth cavity
    final cavityPaint = Paint()
      ..color = const Color(0xFF2E0E12)
      ..style = PaintingStyle.fill;
    final cavityRRect = RRect.fromRectAndRadius(mouthRect, Radius.circular(openH * 0.55));
    canvas.drawRRect(cavityRRect, cavityPaint);

    // 2. Upper teeth hint when open
    if (openH > 3.8) {
      final teethPaint = Paint()
        ..color = const Color(0xFFF7F5F2).withValues(alpha: 0.95)
        ..style = PaintingStyle.fill;
      final teethRect = Rect.fromLTWH(
        mouthRect.left + (mouthRect.width * 0.24),
        mouthRect.top,
        mouthRect.width * 0.52,
        min(2.8, openH * 0.36),
      );
      canvas.drawRRect(RRect.fromRectAndRadius(teethRect, const Radius.circular(1.2)), teethPaint);
    }

    // 3. Lower Lip highlight
    final lipColor = isFemale ? const Color(0xFFDC8484) : const Color(0xFFC68272);
    final lowerLipPaint = Paint()
      ..color = lipColor.withValues(alpha: 0.92)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;

    final lowerLipPath = Path();
    lowerLipPath.moveTo(mouthRect.left, mouthCenter.dy);
    lowerLipPath.quadraticBezierTo(
      mouthCenter.dx,
      mouthCenter.dy + (openH * 0.52) + 1.2,
      mouthRect.right,
      mouthCenter.dy,
    );
    canvas.drawPath(lowerLipPath, lowerLipPaint);
  }

  @override
  bool shouldRepaint(covariant _NaturalMouthSpeakingPainter old) {
    return old.mouthOpenProgress != mouthOpenProgress || old.isFemale != isFemale;
  }
}
