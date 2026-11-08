import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';

/// Full interactive animated cybernetic avatar.
/// - Full-screen edge-to-edge portrait framing for the female & male avatar.
/// - Natural organic eye blinking (periodic realistic eyelid closure).
/// - Dynamic lip-sync and mouth movement driven by backend speech & amplitude.
/// - Living breathing micro-movement and ambient neural energy rings.
/// - Interactive touch / cursor gaze tracking.
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

  // Touch gaze parallax
  double _panX = 0.0;
  double _panY = 0.0;

  @override
  void initState() {
    super.initState();
    _initControllers();
    _scheduleNextBlink();
  }

  void _initControllers() {
    // 1. Slow, subtle living breathing cycle (4.6 seconds, relaxed & steady)
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4600),
    )..repeat(reverse: true);

    _breathingAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _breathingController!,
        curve: Curves.easeInOutSine,
      ),
    );

    // 2. Smooth ambient neural pulse
    _auraPulseController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat(reverse: true);

    // 3. Natural Eye Blinking Controller (180ms organic close & open)
    _blinkController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 180),
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
    // Blinks naturally every 2.8 to 4.8 seconds
    final delayMs = 2800 + _random.nextInt(2000);
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
        final availableW = widget.width ?? constraints.maxWidth;
        final availableH = widget.height ?? constraints.maxHeight;

        // Take full width & height when fullScreen is active
        final portraitW = widget.fullScreen ? availableW : min(availableW, 420.0);
        final portraitH = availableH;

        return GestureDetector(
          onPanUpdate: (d) => _handlePanUpdate(d, Size(portraitW, portraitH)),
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
              _auraPulseController!,
              _blinkAnimation!,
            ]),
            builder: (context, child) {
              // Natural living breathing: 1.6px movement, subtle scale
              final breathVal = _breathingAnimation!.value;
              final breathOffset = breathVal * 1.6;
              final breathScale = 1.0 + (breathVal * 0.006);

              // Smooth gaze parallax
              final parallaxX = _panX * 8.0;
              final parallaxY = _panY * 5.0;

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

                      // 2. Character Portrait + Dynamic Face Motion (Eyes, Mouth, Speech)
                      Transform.translate(
                        offset: Offset(parallaxX, breathOffset + parallaxY),
                        child: Transform.scale(
                          scale: breathScale,
                          child: ClipRRect(
                            borderRadius: widget.fullScreen
                                ? BorderRadius.zero
                                : BorderRadius.circular(28),
                            child: SizedBox(
                              width: portraitW,
                              height: portraitH,
                              child: Stack(
                                alignment: Alignment.center,
                                children: [
                                  // Base Character Image (Elevated top alignment so head fills screen)
                                  Image.asset(
                                    assetPath,
                                    width: portraitW,
                                    height: portraitH,
                                    fit: BoxFit.cover,
                                    alignment: const Alignment(0.0, -0.32),
                                    errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                  ),

                                  // Interactive Facial Expressions: Eye Blinking & Mouth Lip-Sync
                                  Positioned.fill(
                                    child: CustomPaint(
                                      painter: _FaceFeaturePainter(
                                        isFemale: isFemale,
                                        blinkProgress: _blinkAnimation?.value ?? 0.0,
                                        mouthOpenProgress: isSpeaking ? amplitude : 0.0,
                                        gazeX: _panX,
                                        gazeY: _panY,
                                        emotion: emotion,
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
                                            Colors.white.withValues(alpha: 0.82),
                                          ],
                                          stops: const [0.0, 0.76, 1.0],
                                        ),
                                      ),
                                    ),
                                  ),

                                  // Audio Reactive Speech Energy Ring around throat/collar
                                  if (isSpeaking)
                                    Positioned(
                                      bottom: portraitH * 0.28,
                                      child: _buildAcousticPulse(auraColor, amplitude),
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

  Widget _buildAcousticPulse(Color color, double amplitude) {
    final pulseVal = _auraPulseController?.value ?? 0.5;
    final size = 48.0 + (amplitude * 32.0);

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: color.withValues(alpha: (0.4 + (pulseVal * 0.3)) * amplitude),
          width: 2.0,
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.35 * amplitude),
            blurRadius: 18,
            spreadRadius: 4,
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

/// Custom painter for organic eye blinking, gaze tracking, and speech lip-sync
class _FaceFeaturePainter extends CustomPainter {
  final bool isFemale;
  final double blinkProgress; // 0.0 = eyes open, 1.0 = eyes closed
  final double mouthOpenProgress; // 0.0 = closed, 1.0 = fully open
  final double gazeX;
  final double gazeY;
  final String emotion;

  _FaceFeaturePainter({
    required this.isFemale,
    required this.blinkProgress,
    required this.mouthOpenProgress,
    required this.gazeX,
    required this.gazeY,
    required this.emotion,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // ── Eye Feature Positioning & Blinking ─────────────────────────────────────
    final eyeY = size.height * (isFemale ? 0.355 : 0.320);
    final leftEyeX = size.width * (isFemale ? 0.405 : 0.380);
    final rightEyeX = size.width * (isFemale ? 0.595 : 0.620);
    final eyeW = size.width * (isFemale ? 0.082 : 0.088);
    final eyeH = size.height * (isFemale ? 0.024 : 0.026);

    // Natural skin / eyelid palette
    final lidSkinColor = isFemale ? const Color(0xFFF1DDD0) : const Color(0xFFE5C8B4);
    final lidShadowColor = isFemale ? const Color(0xFFD4B39F) : const Color(0xFFC7A28A);
    final lashLineColor = const Color(0xFF251A16);

    if (blinkProgress > 0.04) {
      _paintEyelid(canvas, Offset(leftEyeX, eyeY), eyeW, eyeH, blinkProgress, lidSkinColor, lidShadowColor, lashLineColor);
      _paintEyelid(canvas, Offset(rightEyeX, eyeY), eyeW, eyeH, blinkProgress, lidSkinColor, lidShadowColor, lashLineColor);
    }

    // ── Mouth Feature Positioning & Lip-Sync ───────────────────────────────────
    final mouthY = size.height * (isFemale ? 0.465 : 0.445);
    final mouthX = size.width * 0.50;
    final mouthW = size.width * (isFemale ? 0.115 : 0.130);
    final mouthH = size.height * 0.028;

    if (mouthOpenProgress > 0.08) {
      _paintLipSync(canvas, Offset(mouthX, mouthY), mouthW, mouthH, mouthOpenProgress);
    }
  }

  void _paintEyelid(
    Canvas canvas,
    Offset center,
    double w,
    double h,
    double progress,
    Color skin,
    Color shadow,
    Color lash,
  ) {
    final rect = Rect.fromCenter(center: center, width: w, height: h);
    final dropHeight = h * progress * 1.15;

    // Eyelid skin fold
    final lidPaint = Paint()
      ..color = skin
      ..style = PaintingStyle.fill;

    final shadowPaint = Paint()
      ..color = shadow.withValues(alpha: 0.7 * progress)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;

    final lashPaint = Paint()
      ..color = lash.withValues(alpha: 0.85 * progress)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round;

    final path = Path();
    path.moveTo(rect.left, center.dy - (h * 0.3));
    path.quadraticBezierTo(
      center.dx,
      center.dy - (h * 0.5) + dropHeight,
      rect.right,
      center.dy - (h * 0.3),
    );
    path.lineTo(rect.right, center.dy - (h * 0.35));
    path.quadraticBezierTo(
      center.dx,
      center.dy - (h * 0.5),
      rect.left,
      center.dy - (h * 0.35),
    );
    path.close();

    canvas.drawPath(path, lidPaint);
    canvas.drawPath(path, shadowPaint);

    // Eyelash crease line
    final lashPath = Path();
    lashPath.moveTo(rect.left - 1.0, center.dy - (h * 0.28) + dropHeight);
    lashPath.quadraticBezierTo(
      center.dx,
      center.dy - (h * 0.22) + dropHeight,
      rect.right + 1.0,
      center.dy - (h * 0.28) + dropHeight,
    );
    canvas.drawPath(lashPath, lashPaint);
  }

  void _paintLipSync(
    Canvas canvas,
    Offset center,
    double w,
    double h,
    double openProgress,
  ) {
    final openH = (h * 0.55 * openProgress).clamp(2.0, 15.0);
    final mouthRect = Rect.fromCenter(
      center: center,
      width: w * (1.0 - (openProgress * 0.08)), // Slight narrowing when opening
      height: openH,
    );

    // Inner mouth cavity
    final cavityPaint = Paint()
      ..color = const Color(0xFF381515)
      ..style = PaintingStyle.fill;

    final cavityRRect = RRect.fromRectAndRadius(mouthRect, Radius.circular(openH * 0.6));
    canvas.drawRRect(cavityRRect, cavityPaint);

    // Upper teeth hint
    if (openH > 4.5) {
      final teethPaint = Paint()
        ..color = const Color(0xFFFAF9F6)
        ..style = PaintingStyle.fill;
      final teethRect = Rect.fromLTWH(
        mouthRect.left + (mouthRect.width * 0.25),
        mouthRect.top,
        mouthRect.width * 0.50,
        min(3.0, openH * 0.38),
      );
      canvas.drawRRect(RRect.fromRectAndRadius(teethRect, const Radius.circular(1.5)), teethPaint);
    }

    // Dynamic Lower Lip
    final lipColor = isFemale ? const Color(0xFFD67878) : const Color(0xFFBE7868);
    final lipPaint = Paint()
      ..color = lipColor.withValues(alpha: 0.95)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.4
      ..strokeCap = StrokeCap.round;

    final lowerLipPath = Path();
    lowerLipPath.moveTo(mouthRect.left, center.dy);
    lowerLipPath.quadraticBezierTo(
      center.dx,
      center.dy + (openH * 0.55) + 1.8,
      mouthRect.right,
      center.dy,
    );
    canvas.drawPath(lowerLipPath, lipPaint);
  }

  @override
  bool shouldRepaint(covariant _FaceFeaturePainter old) {
    return old.blinkProgress != blinkProgress ||
        old.mouthOpenProgress != mouthOpenProgress ||
        old.isFemale != isFemale ||
        old.gazeX != gazeX ||
        old.gazeY != gazeY ||
        old.emotion != emotion;
  }
}
