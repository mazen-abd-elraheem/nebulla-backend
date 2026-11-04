import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';

/// Full interactive animated cybernetic avatar.
/// Supports both male and female robotic characters with:
/// - Audio-driven lip-sync and jaw movements
/// - Emotion-based facial aura and cybernetic HUD
/// - Micro-animations: breathing, natural randomized blinking
/// - Interactive touch tracking (3D perspective tilt following user touch/cursor)
/// - Single-tap greeting reaction & double-tap character switch
class InteractiveAnimatedAvatar extends StatefulWidget {
  final String? avatarType; // 'male' or 'female' (defaults to service's active)
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
  late AnimationController _breathingController;
  late Animation<double> _breathingAnimation;

  late AnimationController _blinkController;
  late Animation<double> _blinkAnimation;

  late AnimationController _hudRotateController;

  // Touch tracking 3D tilt
  double _tiltX = 0.0;
  double _tiltY = 0.0;
  Timer? _blinkTimer;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();

    // 1. Breathing motion controller (3.8 second relaxed cycle)
    _breathingController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3800),
    )..repeat(reverse: true);

    _breathingAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _breathingController,
        curve: Curves.easeInOutSine,
      ),
    );

    // 2. Blinking controller (140 ms rapid natural blink)
    _blinkController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 140),
    );

    _blinkAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _blinkController,
        curve: Curves.easeInOutQuad,
      ),
    );

    _scheduleNextBlink();

    // 3. Holographic HUD slow rotation
    _hudRotateController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 16),
    )..repeat();
  }

  void _scheduleNextBlink() {
    _blinkTimer?.cancel();
    final delayMs = 2600 + _random.nextInt(3200);
    _blinkTimer = Timer(Duration(milliseconds: delayMs), () {
      if (!mounted) return;
      _blinkController.forward().then((_) {
        if (mounted) {
          _blinkController.reverse().then((_) {
            if (mounted) _scheduleNextBlink();
          });
        }
      });
    });
  }

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _breathingController.dispose();
    _blinkController.dispose();
    _hudRotateController.dispose();
    super.dispose();
  }

  void _handlePanUpdate(DragUpdateDetails details, Size size) {
    setState(() {
      _tiltY = ((details.localPosition.dx / size.width) - 0.5)
          .clamp(-0.4, 0.4) *
          0.35;
      _tiltX = -((details.localPosition.dy / size.height) - 0.5)
          .clamp(-0.4, 0.4) *
          0.35;
    });
  }

  void _handlePanEnd(DragEndDetails details) {
    setState(() {
      _tiltX = 0.0;
      _tiltY = 0.0;
    });
  }

  @override
  Widget build(BuildContext context) {
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
                    return _buildAvatarScaffold(
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

  Widget _buildAvatarScaffold({
    required String assetPath,
    required bool isFemale,
    required bool isSpeaking,
    required double amplitude,
    required String emotion,
  }) {
    final auraColor = _getEmotionColor(emotion, isSpeaking);

    return LayoutBuilder(
      builder: (context, constraints) {
        final w = widget.width ?? constraints.maxWidth;
        final h = widget.height ?? constraints.maxHeight;

        return GestureDetector(
          onPanUpdate: (d) => _handlePanUpdate(d, Size(w, h)),
          onPanEnd: _handlePanEnd,
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
              _breathingAnimation,
              _blinkAnimation,
              _hudRotateController,
            ]),
            builder: (context, child) {
              final breathOffset = _breathingAnimation.value * 4.0;
              final breathScale = 1.0 + (_breathingAnimation.value * 0.012);

              // 3D perspective matrix
              final transform = Matrix4.identity()
                ..setEntry(3, 2, 0.0012)
                ..rotateX(_tiltX)
                ..rotateY(_tiltY);

              return Center(
                child: Transform(
                  alignment: Alignment.center,
                  transform: transform,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // 1. Ambient Holographic Aura
                      _buildAuraGlow(auraColor, isSpeaking, amplitude, w, h),

                      // 2. Cybernetic HUD Rotating Rings
                      _buildHudRings(auraColor, isSpeaking, amplitude, w, h),

                      // 3. Avatar Body & Moving Head
                      Transform.translate(
                        offset: Offset(0, breathOffset),
                        child: Transform.scale(
                          scale: breathScale,
                          child: _buildAvatarBody(
                            assetPath: assetPath,
                            isFemale: isFemale,
                            isSpeaking: isSpeaking,
                            amplitude: amplitude,
                            width: w,
                            height: h,
                          ),
                        ),
                      ),

                      // 4. Interactive Eyelid Blink Overlay
                      if (_blinkAnimation.value > 0.01)
                        _buildEyelidOverlay(
                          isFemale: isFemale,
                          blinkProgress: _blinkAnimation.value,
                          width: w,
                          height: h,
                        ),

                      // 5. Holographic Speech Waveform Overlay
                      if (isSpeaking)
                        _buildSpeechWaveVisualizer(auraColor, amplitude, w, h),
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

  Widget _buildAuraGlow(
      Color color, bool isSpeaking, double amplitude, double w, double h) {
    final spread = isSpeaking ? 28.0 + (amplitude * 24.0) : 18.0;
    final alpha = isSpeaking ? 0.35 + (amplitude * 0.25) : 0.18;

    return Container(
      width: min(w * 0.85, 360),
      height: min(h * 0.85, 480),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: alpha),
            blurRadius: spread * 2,
            spreadRadius: spread,
          ),
          BoxShadow(
            color: const Color(0xFF00E5FF).withValues(alpha: alpha * 0.5),
            blurRadius: spread * 3,
            spreadRadius: spread * 0.5,
          ),
        ],
      ),
    );
  }

  Widget _buildHudRings(
      Color color, bool isSpeaking, double amplitude, double w, double h) {
    final ringSize = min(w * 0.9, 420.0);

    return Transform.rotate(
      angle: _hudRotateController.value * 2 * pi,
      child: CustomPaint(
        size: Size(ringSize, ringSize),
        painter: _CyberHudPainter(
          color: color,
          pulse: isSpeaking ? amplitude : _breathingAnimation.value,
        ),
      ),
    );
  }

  Widget _buildAvatarBody({
    required String assetPath,
    required bool isFemale,
    required bool isSpeaking,
    required double amplitude,
    required double width,
    required double height,
  }) {
    // Lip-sync & jaw displacement: lower jaw moves down by up to 5 pixels with speech amplitude
    final jawDisplacement = isSpeaking ? amplitude * 4.5 : 0.0;

    return ClipRRect(
      borderRadius: widget.fullScreen
          ? BorderRadius.zero
          : BorderRadius.circular(28),
      child: SizedBox(
        width: width,
        height: height,
        child: Stack(
          alignment: Alignment.center,
          children: [
            // Base Character Portrait
            Image.asset(
              assetPath,
              width: width,
              height: height,
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
              errorBuilder: (_, _, _) => _buildFallbackGraphic(isFemale),
            ),

            // Dynamic Animated Mouth & Lip-Sync Layer
            if (isSpeaking)
              Positioned(
                top: isFemale ? height * 0.54 : height * 0.51,
                child: Transform.translate(
                  offset: Offset(0, jawDisplacement * 0.8),
                  child: _buildLipSyncMouth(amplitude, isFemale),
                ),
              ),

            // Cybernetic Chest Core Reactor Pulse
            Positioned(
              bottom: height * 0.14,
              child: _buildCoreReactor(isSpeaking, amplitude),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLipSyncMouth(double amplitude, bool isFemale) {
    // Subtle realistic lip aperture modulation
    final mouthWidth = isFemale ? 28.0 + (amplitude * 10.0) : 34.0 + (amplitude * 12.0);
    final mouthHeight = 3.0 + (amplitude * 9.0);

    return Container(
      width: mouthWidth,
      height: mouthHeight,
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2C).withValues(alpha: 0.85),
        borderRadius: BorderRadius.all(
          Radius.elliptical(mouthWidth / 2, mouthHeight / 2),
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF00E5FF).withValues(alpha: 0.25 * amplitude),
            blurRadius: 6,
            spreadRadius: 1,
          ),
        ],
      ),
      child: Center(
        child: Container(
          width: mouthWidth * 0.6,
          height: max(1.0, mouthHeight * 0.35),
          decoration: BoxDecoration(
            color: const Color(0xFF381A22).withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
      ),
    );
  }

  Widget _buildCoreReactor(bool isSpeaking, double amplitude) {
    final pulseScale = 1.0 + (isSpeaking ? amplitude * 0.35 : _breathingAnimation.value * 0.15);
    final glowColor = isSpeaking ? const Color(0xFF00E5FF) : const Color(0xFF38BDF8);

    return Transform.scale(
      scale: pulseScale,
      child: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              Colors.white,
              glowColor,
              glowColor.withValues(alpha: 0.0),
            ],
          ),
          boxShadow: [
            BoxShadow(
              color: glowColor.withValues(alpha: 0.6),
              blurRadius: 16,
              spreadRadius: 4,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEyelidOverlay({
    required bool isFemale,
    required double blinkProgress,
    required double width,
    required double height,
  }) {
    // Eyelid position aligned to eyes
    final eyeTop = isFemale ? height * 0.385 : height * 0.345;
    final eyeHeight = 16.0 * blinkProgress;

    return Positioned(
      top: eyeTop,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Left eye lid
          Container(
            width: 36,
            height: eyeHeight,
            decoration: BoxDecoration(
              color: const Color(0xFFE2E8F0),
              borderRadius: BorderRadius.circular(8),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 2,
                ),
              ],
            ),
          ),
          const SizedBox(width: 32),
          // Right eye lid
          Container(
            width: 36,
            height: eyeHeight,
            decoration: BoxDecoration(
              color: const Color(0xFFE2E8F0),
              borderRadius: BorderRadius.circular(8),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 2,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSpeechWaveVisualizer(Color color, double amplitude, double w, double h) {
    return Positioned(
      bottom: h * 0.04,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.88),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: color.withValues(alpha: 0.5),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.25),
              blurRadius: 16,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(7, (i) {
            final barAmp = sin((i * 0.6) + (amplitude * pi)).abs();
            final barHeight = 8.0 + (barAmp * 20.0);
            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 2.5),
              width: 3.5,
              height: barHeight,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(4),
              ),
            );
          }),
        ),
      ),
    );
  }

  Widget _buildFallbackGraphic(bool isFemale) {
    return Container(
      color: const Color(0xFFF1F5F9),
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
    _blinkController.forward().then((_) => _blinkController.reverse());
    // Friendly speech greeting on tap
    final name = _audioService.activePersonaName.value;
    final greeting = 'مرحباً بك! أنا $name. كيف يمكنني مساعدتك؟';
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

/// Custom painter for glowing sci-fi holographic HUD rings
class _CyberHudPainter extends CustomPainter {
  final Color color;
  final double pulse;

  _CyberHudPainter({required this.color, required this.pulse});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (min(size.width, size.height) / 2) * 0.92;

    final paintRing = Paint()
      ..color = color.withValues(alpha: 0.15 + (pulse * 0.2))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;

    // Outer circle
    canvas.drawCircle(center, radius, paintRing);

    // Inner dashed orbit
    final paintDashed = Paint()
      ..color = color.withValues(alpha: 0.25 + (pulse * 0.25))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    const segments = 12;
    for (int i = 0; i < segments; i++) {
      if (i % 2 == 0) {
        final startAngle = (i * 2 * pi / segments);
        const sweepAngle = (pi / segments);
        canvas.drawArc(
          Rect.fromCircle(center: center, radius: radius * 0.88),
          startAngle,
          sweepAngle,
          false,
          paintDashed,
        );
      }
    }

    // Four cardinal HUD brackets
    final bracketPaint = Paint()
      ..color = color.withValues(alpha: 0.5 + (pulse * 0.3))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;

    final r = radius * 0.95;
    for (int i = 0; i < 4; i++) {
      final angle = i * (pi / 2);
      final p1 = Offset(center.dx + r * cos(angle - 0.08), center.dy + r * sin(angle - 0.08));
      final p2 = Offset(center.dx + r * cos(angle + 0.08), center.dy + r * sin(angle + 0.08));
      canvas.drawLine(p1, p2, bracketPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _CyberHudPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.pulse != pulse;
}
