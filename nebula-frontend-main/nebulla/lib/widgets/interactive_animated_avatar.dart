import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';

/// Full interactive animated cybernetic avatar.
/// Supports both male and female robotic characters with:
/// - Audio-driven speech resonance & vocal aura
/// - Holographic voice visualizer and rotating cyber HUD
/// - Natural organic breathing micro-motion
/// - Smooth interactive touch/cursor parallax gaze
/// - Single-tap greeting reaction & double-tap appearance switch
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

  // Safe nullable animation controllers (immune to LateInitializationError on Hot Reload)
  AnimationController? _breathingController;
  Animation<double>? _breathingAnimation;
  AnimationController? _hudRotateController;
  AnimationController? _pulseController;

  // Interactive parallax gaze
  double _panX = 0.0;
  double _panY = 0.0;

  @override
  void initState() {
    super.initState();
    _initControllers();
  }

  void _initControllers() {
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3600),
    )..repeat(reverse: true);

    _breathingAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _breathingController!,
        curve: Curves.easeInOutSine,
      ),
    );

    _hudRotateController ??= AnimationController(
      vsync: this,
      duration: const Duration(seconds: 20),
    )..repeat();

    _pulseController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _breathingController?.dispose();
    _hudRotateController?.dispose();
    _pulseController?.dispose();
    super.dispose();
  }

  void _handlePanUpdate(DragUpdateDetails details, Size size) {
    setState(() {
      _panX = ((details.localPosition.dx / size.width) - 0.5).clamp(-0.5, 0.5);
      _panY = ((details.localPosition.dy / size.height) - 0.5).clamp(-0.5, 0.5);
    });
  }

  void _handlePanEnd(DragEndDetails details) {
    setState(() {
      _panX = 0.0;
      _panY = 0.0;
    });
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
              _breathingAnimation!,
              _hudRotateController!,
              _pulseController!,
            ]),
            builder: (context, child) {
              // Natural organic motion calculation
              final breathVal = _breathingAnimation!.value;
              final breathOffset = breathVal * 3.5;
              final breathScale = 1.0 + (breathVal * 0.012);

              // Speech resonance bobbing (organic subtle vertical speech micro-movements)
              final speechBob = isSpeaking
                  ? sin(_pulseController!.value * pi * 4) * amplitude * 2.8
                  : 0.0;

              // Interactive smooth parallax (gently shifts portrait without geometric distortion)
              final parallaxX = _panX * 14.0;
              final parallaxY = _panY * 10.0;
              final parallaxTilt = _panX * 0.025;

              return Center(
                child: Stack(
                  alignment: Alignment.center,
                  clipBehavior: Clip.none,
                  children: [
                    // 1. Ambient Holographic Glowing Aura
                    _buildAmbientAura(auraColor, isSpeaking, amplitude, w, h),

                    // 2. Rotating Cybernetic HUD Rings behind avatar
                    _buildRotatingHud(auraColor, isSpeaking, amplitude, w, h),

                    // 3. Audio Sonic Wave Rings when speaking
                    if (isSpeaking)
                      _buildSonicWaveRings(auraColor, amplitude, w, h),

                    // 4. Character Portrait with Natural Organic Motion & Parallax
                    Transform.translate(
                      offset: Offset(parallaxX, breathOffset + speechBob + parallaxY),
                      child: Transform.rotate(
                        angle: parallaxTilt,
                        child: Transform.scale(
                          scale: breathScale,
                          child: _buildCharacterCard(
                            assetPath: assetPath,
                            isFemale: isFemale,
                            isSpeaking: isSpeaking,
                            amplitude: amplitude,
                            auraColor: auraColor,
                            width: w,
                            height: h,
                          ),
                        ),
                      ),
                    ),

                    // 5. Sci-Fi Speech Waveform Equalizer (Bottom)
                    if (isSpeaking)
                      Positioned(
                        bottom: widget.fullScreen ? 140 : 20,
                        child: _buildAudioWaveformBar(auraColor, amplitude),
                      ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildAmbientAura(
      Color color, bool isSpeaking, double amplitude, double w, double h) {
    final breathVal = _breathingAnimation?.value ?? 0.5;
    final pulse = isSpeaking ? 0.35 + (amplitude * 0.25) : 0.16 + (breathVal * 0.08);
    final spread = isSpeaking ? 34.0 + (amplitude * 24.0) : 22.0;

    return Container(
      width: min(w * 0.78, 340),
      height: min(h * 0.78, 440),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: pulse),
            blurRadius: spread * 2.2,
            spreadRadius: spread,
          ),
          BoxShadow(
            color: const Color(0xFF00E5FF).withValues(alpha: pulse * 0.6),
            blurRadius: spread * 3.5,
            spreadRadius: spread * 0.4,
          ),
        ],
      ),
    );
  }

  Widget _buildRotatingHud(
      Color color, bool isSpeaking, double amplitude, double w, double h) {
    final hudSize = min(min(w, h) * 0.88, 400.0);
    final rotateVal = _hudRotateController?.value ?? 0.0;
    final breathVal = _breathingAnimation?.value ?? 0.5;

    return Transform.rotate(
      angle: rotateVal * 2 * pi,
      child: CustomPaint(
        size: Size(hudSize, hudSize),
        painter: _CyberHudPainter(
          color: color,
          pulse: isSpeaking ? amplitude : breathVal,
        ),
      ),
    );
  }

  Widget _buildSonicWaveRings(Color color, double amplitude, double w, double h) {
    final pulseVal = _pulseController?.value ?? 0.5;
    final ringScale = 1.0 + (pulseVal * 0.18 * amplitude);
    final opacity = (1.0 - pulseVal).clamp(0.0, 1.0) * amplitude;

    return Transform.scale(
      scale: ringScale,
      child: Container(
        width: min(w * 0.82, 380),
        height: min(h * 0.82, 480),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(40),
          border: Border.all(
            color: color.withValues(alpha: opacity * 0.4),
            width: 2.0,
          ),
        ),
      ),
    );
  }

  Widget _buildCharacterCard({
    required String assetPath,
    required bool isFemale,
    required bool isSpeaking,
    required double amplitude,
    required Color auraColor,
    required double width,
    required double height,
  }) {
    final cardWidth = widget.fullScreen ? width : min(width, 420.0);
    final cardHeight = widget.fullScreen ? height : min(height, 580.0);

    return ClipRRect(
      borderRadius: widget.fullScreen
          ? BorderRadius.zero
          : BorderRadius.circular(28),
      child: Container(
        width: cardWidth,
        height: cardHeight,
        color: Colors.transparent,
        child: Stack(
          alignment: Alignment.center,
          children: [
            // High-Resolution Character Portrait
            Image.asset(
              assetPath,
              width: cardWidth,
              height: cardHeight,
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
              errorBuilder: (_, _, _) => _buildFallback(isFemale),
            ),

            // Cinematic Gradient Lighting Overlay
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      Colors.transparent,
                      Colors.black.withValues(alpha: widget.fullScreen ? 0.35 : 0.15),
                    ],
                    stops: const [0.0, 0.65, 1.0],
                  ),
                ),
              ),
            ),

            // Speaking Glow Border Pulse
            if (isSpeaking)
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: auraColor.withValues(alpha: 0.4 * amplitude),
                      width: 2.5,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildAudioWaveformBar(Color color, double amplitude) {
    final pulseVal = _pulseController?.value ?? 0.5;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: color.withValues(alpha: 0.6),
          width: 1.4,
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.3),
            blurRadius: 18,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(9, (i) {
          final wave = sin((i * 0.5) + (pulseVal * pi * 3)).abs();
          final barHeight = 6.0 + (wave * amplitude * 22.0);

          return Container(
            margin: const EdgeInsets.symmetric(horizontal: 2.2),
            width: 3.2,
            height: barHeight,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(4),
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
    final radius = (min(size.width, size.height) / 2) * 0.94;

    final paintRing = Paint()
      ..color = color.withValues(alpha: 0.16 + (pulse * 0.18))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;

    // Outer circle
    canvas.drawCircle(center, radius, paintRing);

    // Inner dashed orbit
    final paintDashed = Paint()
      ..color = color.withValues(alpha: 0.22 + (pulse * 0.22))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    const segments = 16;
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
      ..color = color.withValues(alpha: 0.45 + (pulse * 0.3))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.4;

    final r = radius * 0.96;
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
