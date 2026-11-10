import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/audio_viseme_analyzer.dart';

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
  AnimationController? _headMotionController;
  AnimationController? _blinkController;
  Animation<double>? _blinkAnimation;

  // 3D Orbit Interaction & Perspective State
  double _userRotationX = 0.0;
  double _userRotationY = 0.0;
  Offset? _lastPanPos;
  AnimationController? _recenterController;
  Animation<double>? _recenterAnimX;
  Animation<double>? _recenterAnimY;

  Timer? _blinkTimer;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _initControllers();
    _scheduleNextBlink();
  }

  void _initControllers() {
    // 0. Recenter spring-back controller for 3D orbit
    _recenterController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 650),
    )..addListener(() {
        if (_recenterAnimX != null && _recenterAnimY != null) {
          setState(() {
            _userRotationX = _recenterAnimX!.value;
            _userRotationY = _recenterAnimY!.value;
          });
        }
      });
    // 1. Ambient living breathing pulse (4 seconds)
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

    // 3. Filter-Style 3D Micro-Head Parallax Sway (5.5 seconds organic cycle)
    _headMotionController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 5500),
    )..repeat(reverse: true);

    // 4. Natural Eye Blinking Controller (140ms organic eyelid close & open)
    _blinkController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 140),
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
    // Blinks naturally every 2.4 to 4.0 seconds
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

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _recenterController?.dispose();
    _breathingController?.dispose();
    _auraPulseController?.dispose();
    _headMotionController?.dispose();
    _blinkController?.dispose();
    super.dispose();
  }

  void _onPanStart(DragStartDetails details) {
    _recenterController?.stop();
    _lastPanPos = details.localPosition;
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_lastPanPos == null) return;
    final delta = details.localPosition - _lastPanPos!;
    _lastPanPos = details.localPosition;
    setState(() {
      _userRotationY += delta.dx * 0.007; // Orbit horizontally in 3D
      _userRotationX = (_userRotationX - delta.dy * 0.005).clamp(-0.35, 0.35); // Orbit vertically in 3D
    });
  }

  void _onPanEnd(DragEndDetails details) {
    _lastPanPos = null;
    if (_recenterController == null) return;
    _recenterAnimX = Tween<double>(begin: _userRotationX, end: 0.0).animate(
      CurvedAnimation(parent: _recenterController!, curve: Curves.easeOutCubic),
    );
    _recenterAnimY = Tween<double>(begin: _userRotationY, end: 0.0).animate(
      CurvedAnimation(parent: _recenterController!, curve: Curves.easeOutCubic),
    );
    _recenterController!.forward(from: 0.0);
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

        // Take full width & height when fullScreen is active
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
          onPanStart: _onPanStart,
          onPanUpdate: _onPanUpdate,
          onPanEnd: _onPanEnd,
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

              // Filter-Style 3D Micro-Head Parallax & Idle Sway combined with 3D User Orbit
              final headT = (_headMotionController?.value ?? 0.5) * 2 * pi;
              final idleYaw = sin(headT * 0.7) * 0.024; // ±1.4° horizontal sway
              final idlePitch = (cos(headT * 0.9) * 0.016) +
                  (isSpeaking ? sin(headT * 3.5) * 0.008 : 0.0); // subtle speech nod
              final idleRoll = sin(headT * 0.5) * 0.010; // ±0.6° gentle head tilt

              final totalYaw = _userRotationY + idleYaw;
              final totalPitch = _userRotationX + idlePitch;
              final totalRoll = idleRoll;

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

                      // 2. Character Portrait: 3D Orbit Perspective + Filter Parallax + Organic Respiration
                      Transform(
                        alignment: const Alignment(0.0, -0.15),
                        transform: Matrix4.identity()
                          ..setEntry(3, 2, 0.0012) // 3D depth perspective
                          ..rotateY(totalYaw)
                          ..rotateX(totalPitch)
                          ..rotateZ(totalRoll),
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
                                    // Base Character Image with subtle organic micro-breathing & speech resonance
                                    Transform.scale(
                                      scale: 1.0 +
                                          (0.012 * (_breathingAnimation?.value ?? 0.0)) +
                                          (isSpeaking ? amplitude * 0.015 : 0.0),
                                      alignment: const Alignment(0.0, 0.25),
                                      child: Image.asset(
                                        assetPath,
                                        width: imgW,
                                        height: imgH,
                                        fit: BoxFit.fill,
                                        errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                      ),
                                    ),

                                    // Natural Organic Eye Blinking (Positioned accurately on actual eye sockets)
                                    Positioned.fill(
                                      child: CustomPaint(
                                        painter: _NaturalEyeBlinkPainter(
                                          isFemale: isFemale,
                                          blinkProgress: _blinkAnimation?.value ?? 0.0,
                                        ),
                                      ),
                                    ),

                                    // Dynamic Audio-Driven Lip-Sync (Viseme based mouth morph directly on lips)
                                    Positioned.fill(
                                      child: CustomPaint(
                                        painter: _RealisticMouthLipSyncPainter(
                                          isFemale: isFemale,
                                          viseme: viseme,
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

/// Organic, photorealistic eye blinking painter positioned accurately on actual eye sockets
class _NaturalEyeBlinkPainter extends CustomPainter {
  final bool isFemale;
  final double blinkProgress; // 0.0 = open, 1.0 = fully closed

  _NaturalEyeBlinkPainter({
    required this.isFemale,
    required this.blinkProgress,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (blinkProgress < 0.04) return;

    // Exact center coordinates in 1:1 image pixel space (1024h)
    final leftCenter = isFemale
        ? const Offset(166.0, 416.0)
        : const Offset(158.0, 370.0);
    final rightCenter = isFemale
        ? const Offset(252.0, 416.0)
        : const Offset(290.0, 370.0);

    final eyeW = isFemale ? 42.0 : 44.0;
    final eyeH = isFemale ? 18.0 : 18.0;

    final lidColor = isFemale ? const Color(0xFFE4CEBF) : const Color(0xFFD2B29F);
    final shadowColor = isFemale ? const Color(0xFF382A26) : const Color(0xFF281E1C);

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
  bool shouldRepaint(covariant _NaturalEyeBlinkPainter old) {
    return old.blinkProgress != blinkProgress || old.isFemale != isFemale;
  }
}

/// Dynamic Audio-Driven Viseme Lip-Sync Painter positioned accurately directly on lips
class _RealisticMouthLipSyncPainter extends CustomPainter {
  final bool isFemale;
  final VisemeFrame viseme;

  _RealisticMouthLipSyncPainter({
    required this.isFemale,
    required this.viseme,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (viseme.openness < 0.05 && viseme.type != VisemeType.mbp) return;

    // Exact center coordinates on actual lips
    final mouthCenter = isFemale
        ? const Offset(209.0, 554.0)
        : const Offset(224.0, 562.0);

    final baseW = isFemale ? 56.0 : 68.0;
    // Viseme pucker narrows width (oo/u), widthRatio expands width (ee/smile)
    final mouthW = (baseW * viseme.widthRatio * (1.0 - (viseme.pucker * 0.28))).clamp(28.0, 84.0);

    final maxH = isFemale ? 9.5 : 11.0;
    final openH = (viseme.openness * maxH).clamp(1.2, maxH);

    final mouthRect = Rect.fromCenter(
      center: Offset(mouthCenter.dx, mouthCenter.dy + (viseme.jawDrop * 2.2)),
      width: mouthW,
      height: openH,
    );

    // 1. Inner mouth cavity (curved based on viseme pucker & openness)
    final cornerRadius = viseme.pucker > 0.4 ? openH * 0.78 : openH * 0.52;
    final cavityPaint = Paint()
      ..color = const Color(0xFF22090C)
      ..style = PaintingStyle.fill;
    final cavityRRect = RRect.fromRectAndRadius(mouthRect, Radius.circular(cornerRadius));
    canvas.drawRRect(cavityRRect, cavityPaint);

    // 2. Upper teeth hint based on viseme.teethVisible
    if (openH > 2.8 && viseme.teethVisible > 0.15) {
      final teethAlpha = (viseme.teethVisible * 0.95).clamp(0.0, 1.0);
      final teethPaint = Paint()
        ..color = const Color(0xFFFAF7F4).withValues(alpha: teethAlpha)
        ..style = PaintingStyle.fill;
      final teethRect = Rect.fromLTWH(
        mouthRect.left + (mouthRect.width * 0.20),
        mouthRect.top,
        mouthRect.width * 0.60,
        min(2.5, openH * 0.35),
      );
      canvas.drawRRect(RRect.fromRectAndRadius(teethRect, const Radius.circular(1.2)), teethPaint);
    }

    // 3. Lower Lip highlight & shadow
    final lipColor = isFemale ? const Color(0xFFDC7D7D) : const Color(0xFFBF7568);
    final lowerLipPaint = Paint()
      ..color = lipColor.withValues(alpha: 0.92)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round;

    final lowerLipPath = Path();
    lowerLipPath.moveTo(mouthRect.left, mouthRect.top + (openH * 0.35));
    lowerLipPath.quadraticBezierTo(
      mouthCenter.dx,
      mouthRect.bottom + 1.2,
      mouthRect.right,
      mouthRect.top + (openH * 0.35),
    );
    canvas.drawPath(lowerLipPath, lowerLipPaint);
  }

  @override
  bool shouldRepaint(covariant _RealisticMouthLipSyncPainter old) {
    return old.viseme.openness != viseme.openness ||
        old.viseme.type != viseme.type ||
        old.viseme.widthRatio != viseme.widthRatio ||
        old.viseme.pucker != viseme.pucker ||
        old.isFemale != isFemale;
  }
}
