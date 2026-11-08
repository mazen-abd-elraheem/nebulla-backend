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
  AnimationController? _nodController;
  Animation<double>? _nodAnimation;

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
    // 1. Lively living breathing cycle (3.2 seconds, organic rise and fall)
    _breathingController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3200),
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

    // 3. Natural Eye Blinking Controller (160ms organic eyelid close & open)
    _blinkController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 160),
    );

    _blinkAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _blinkController!,
        curve: Curves.easeInOutQuad,
      ),
    );

    // 4. Interactive Tap Nod Gesture Reaction
    _nodController ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );

    _nodAnimation ??= Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _nodController!,
        curve: Curves.easeInOutBack,
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
    _nodController?.dispose();
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
              ?_nodAnimation,
            ]),
            builder: (context, child) {
              // 1. Lively Living Breathing Physics
              final breathVal = _breathingAnimation!.value;
              final breathOffset = sin(breathVal * pi * 2) * 8.5;
              final breathScale = 1.0 + (sin(breathVal * pi * 2) * 0.022);
              final breathTilt = sin(breathVal * pi) * 0.015;

              // 2. Active Conversational Speech Articulation & Gestures
              final speakTick = DateTime.now().millisecondsSinceEpoch / 1000.0;
              final speechBob = isSpeaking ? (sin(speakTick * 7.5) * amplitude * 12.0) : 0.0;
              final speechTilt = isSpeaking ? (sin(speakTick * 3.8) * amplitude * 0.035) : 0.0;
              final speechScale = isSpeaking ? (1.0 + (amplitude * 0.028)) : 1.0;

              // 3. Interactive Gaze & Cursor Tracking Parallax
              final parallaxX = _panX * 22.0;
              final parallaxY = _panY * 14.0;
              final gazeTilt = _panX * 0.03;

              // 4. Interactive Touch Reaction Nod
              final nodVal = _nodAnimation?.value ?? 0.0;
              final nodOffset = nodVal * 12.0;

              final totalOffsetY = breathOffset + speechBob + parallaxY + nodOffset;
              final totalOffsetX = parallaxX;
              final totalScale = breathScale * speechScale;
              final totalTilt = breathTilt + speechTilt + gazeTilt;

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

                      // 2. Character Portrait + Dynamic Movement & Natural Action
                      Transform.translate(
                        offset: Offset(totalOffsetX, totalOffsetY),
                        child: Transform.rotate(
                          angle: totalTilt,
                          child: Transform.scale(
                            scale: totalScale,
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
                                    // Base Character Image (Elevated top alignment so character fills the screen naturally)
                                    Image.asset(
                                      assetPath,
                                      width: portraitW,
                                      height: portraitH,
                                      fit: BoxFit.cover,
                                      alignment: isFemale
                                          ? const Alignment(0.0, -0.10)
                                          : const Alignment(0.0, -0.22),
                                      errorBuilder: (_, _, _) => _buildFallback(isFemale),
                                    ),

                                    // Natural Eye Blinking Overlay
                                    Positioned.fill(
                                      child: CustomPaint(
                                        painter: _RealisticEyelidPainter(
                                          isFemale: isFemale,
                                          blinkProgress: _blinkAnimation?.value ?? 0.0,
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
    _nodController?.forward(from: 0.0).then((_) {
      if (mounted) _nodController?.reverse();
    });
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

/// Organic, photorealistic eye blinking painter matching the avatar's eye positions
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

    // Female eye center: y = 0.410, left X = 0.395, right X = 0.610
    // Male eye center: y = 0.366, left X = 0.357, right X = 0.647
    final eyeY = size.height * (isFemale ? 0.410 : 0.366);
    final leftX = size.width * (isFemale ? 0.395 : 0.357);
    final rightX = size.width * (isFemale ? 0.610 : 0.647);
    final eyeW = size.width * (isFemale ? 0.092 : 0.108);
    final eyeH = size.height * (isFemale ? 0.036 : 0.040);

    final lidColor = isFemale ? const Color(0xFFE8D4C8) : const Color(0xFFD6B5A2);
    final shadowColor = isFemale ? const Color(0xFFC49F8E) : const Color(0xFFAC8775);

    _paintSingleEye(canvas, Offset(leftX, eyeY), eyeW, eyeH, lidColor, shadowColor);
    _paintSingleEye(canvas, Offset(rightX, eyeY), eyeW, eyeH, lidColor, shadowColor);
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
      ..color = lid.withValues(alpha: (0.94 * blinkProgress).clamp(0.0, 1.0))
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
