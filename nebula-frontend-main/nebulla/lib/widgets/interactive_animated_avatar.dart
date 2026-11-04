import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';

/// Full interactive animated cybernetic avatar.
/// - Stable, grounded portrait framing matching the design mockups.
/// - Subtle living breathing micro-animation (no violent shaking).
/// - Dynamic acoustic energy rings & voice waveform visualizer when speaking.
/// - Smooth interactive touch / cursor gaze parallax.
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

  // Safe animation controllers
  AnimationController? _breathingController;
  Animation<double>? _breathingAnimation;
  AnimationController? _auraPulseController;

  // Touch gaze parallax
  double _panX = 0.0;
  double _panY = 0.0;

  @override
  void initState() {
    super.initState();
    _initControllers();
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
  }

  @override
  void dispose() {
    _breathingController?.dispose();
    _auraPulseController?.dispose();
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

        // Elegant framing: keep portrait aspect ratio centered even on wide desktops
        final portraitW = widget.fullScreen
            ? min(availableW, availableH * 0.58).clamp(320.0, 520.0)
            : min(availableW, 420.0);
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
            ]),
            builder: (context, child) {
              // Very subtle, natural living breathing: only 1.4px movement, 1.006 scale
              final breathVal = _breathingAnimation!.value;
              final breathOffset = breathVal * 1.6;
              final breathScale = 1.0 + (breathVal * 0.006);

              // Smooth gaze parallax (no shearing or distortion)
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

                      // 2. Character Portrait (Clean, perfectly framed, steady)
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
                                  // Base Portrait Image
                                  Image.asset(
                                    assetPath,
                                    width: portraitW,
                                    height: portraitH,
                                    fit: BoxFit.cover,
                                    alignment: Alignment.topCenter,
                                    errorBuilder: (_, _, _) => _buildFallback(isFemale),
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
                                            Colors.white.withValues(alpha: 0.8),
                                          ],
                                          stops: const [0.0, 0.78, 1.0],
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
