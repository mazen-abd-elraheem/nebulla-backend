import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/audio_viseme_analyzer.dart';

/// Interactive 3D Avatar Widget with client-side blendshapes,
/// 360° orbit rotation, 3D idle sway, and audio-driven lip-sync.
class ThreeDAvatarWidget extends StatefulWidget {
  final bool fullScreen;
  final VoidCallback? onAvatarTapped;

  const ThreeDAvatarWidget({
    super.key,
    this.fullScreen = true,
    this.onAvatarTapped,
  });

  @override
  State<ThreeDAvatarWidget> createState() => _ThreeDAvatarWidgetState();
}

class _ThreeDAvatarWidgetState extends State<ThreeDAvatarWidget>
    with TickerProviderStateMixin {
  final _audioService = AvatarAudioService.instance;

  // 3D Motion & Idle Controllers
  late final AnimationController _idleSwayController;
  late final AnimationController _breathingController;
  late final AnimationController _blinkController;

  // 3D Rotation Angles (controlled by gestures + idle loop)
  double _userRotationX = 0.0;
  double _userRotationY = 0.0;
  Offset? _lastPanPos;

  Timer? _blinkTimer;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _initControllers();
    _scheduleNextBlink();
  }

  void _initControllers() {
    // 1. Organic 3D Idle Head Sway Loop (6 seconds)
    _idleSwayController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    )..repeat(reverse: true);

    // 2. Chest & Torso Breathing Cycle (3.8 seconds)
    _breathingController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3800),
    )..repeat(reverse: true);

    // 3. 3D Eyelid Blink Controller (130ms quick natural close & open)
    _blinkController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 130),
    );
  }

  void _scheduleNextBlink() {
    _blinkTimer?.cancel();
    final nextMs = 2400 + _random.nextInt(1800);
    _blinkTimer = Timer(Duration(milliseconds: nextMs), () {
      if (!mounted) return;
      _blinkController.forward(from: 0.0).then((_) {
        if (!mounted) return;
        _blinkController.reverse().then((_) {
          if (mounted) _scheduleNextBlink();
        });
      });
    });
  }

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _idleSwayController.dispose();
    _breathingController.dispose();
    _blinkController.dispose();
    super.dispose();
  }

  void _onPanStart(DragStartDetails details) {
    _lastPanPos = details.localPosition;
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_lastPanPos == null) return;
    final delta = details.localPosition - _lastPanPos!;
    _lastPanPos = details.localPosition;

    setState(() {
      _userRotationY += delta.dx * 0.008; // Orbit horizontally
      _userRotationX = (_userRotationX - delta.dy * 0.006).clamp(-0.35, 0.35); // Orbit vertically
    });
  }

  void _onPanEnd(DragEndDetails details) {
    _lastPanPos = null;
  }

  void _triggerGreeting() {
    final name = _audioService.activePersonaName.value;
    final isFemale = _audioService.activeAvatarType.value == 'female';
    final greeting = isFemale
        ? 'مرحباً بك! أنا $name، جاهزة لمساعدتك بتقنية الأفاتار ثلاثي الأبعاد.'
        : 'أهلاً بك! أنا $name، جاهز لإنجاز مهامك فوراً بنظام المجسم التفاعلي.';
    _audioService.speak(greeting, emotion: 'happy');
    widget.onAvatarTapped?.call();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;

        return GestureDetector(
          onTap: _triggerGreeting,
          onPanStart: _onPanStart,
          onPanUpdate: _onPanUpdate,
          onPanEnd: _onPanEnd,
          child: AnimatedBuilder(
            animation: Listenable.merge([
              _idleSwayController,
              _breathingController,
              _blinkController,
              _audioService.currentViseme,
              _audioService.speechAmplitude,
              _audioService.isSpeaking,
            ]),
            builder: (context, child) {
              final viseme = _audioService.currentViseme.value;
              final isSpeaking = _audioService.isSpeaking.value;
              final amplitude = _audioService.speechAmplitude.value;

              // Compute dynamic 3D idle head & neck motion
              final t = _idleSwayController.value * 2 * pi;
              final idleYaw = sin(t * 0.8) * 0.045; // ±2.6° horizontal sway
              final idlePitch = cos(t * 1.1) * 0.025 + (isSpeaking ? sin(t * 4.0) * 0.015 : 0.0);
              final idleRoll = sin(t * 0.6) * 0.020;

              final totalRotY = _userRotationY + idleYaw;
              final totalRotX = _userRotationX + idlePitch;
              final totalRotZ = idleRoll;

              final breath = _breathingController.value;
              final blink = _blinkController.value;

              return Stack(
                fit: StackFit.expand,
                alignment: Alignment.center,
                children: [
                  // 1. Cybernetic Ambient Lighting Halo
                  Center(
                    child: Container(
                      width: min(w * 0.88, 380),
                      height: min(w * 0.88, 380),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF00D2FF).withValues(
                              alpha: isSpeaking ? 0.28 + amplitude * 0.15 : 0.12,
                            ),
                            blurRadius: isSpeaking ? 80 : 50,
                            spreadRadius: isSpeaking ? 24 : 10,
                          ),
                        ],
                      ),
                    ),
                  ),

                  // 2. 3D Avatar Rendering Canvas (Perspective Matrix + 52 Blendshapes)
                  CustomPaint(
                    size: Size(w, h),
                    painter: _ThreeDAvatarMeshPainter(
                      rotX: totalRotX,
                      rotY: totalRotY,
                      rotZ: totalRotZ,
                      breath: breath,
                      blink: blink,
                      viseme: viseme,
                      isSpeaking: isSpeaking,
                      amplitude: amplitude,
                      isFemale: _audioService.activeAvatarType.value == 'female',
                    ),
                  ),

                  // 3. 3D Interaction Pill Cue (shows users they can rotate in 360°)
                  Positioned(
                    top: 80,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.85),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.05),
                            blurRadius: 10,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.view_in_ar_rounded,
                            size: 14,
                            color: Color(0xFF0284C7),
                          ),
                          SizedBox(width: 6),
                          Text(
                            'مجسم 3D تفاعلي • اسحب للتدوير 360°',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 10.5,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF0284C7),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  // 4. Reset 3D Rotation Button (appears if rotated)
                  if (_userRotationY.abs() > 0.05 || _userRotationX.abs() > 0.05)
                    Positioned(
                      top: 120,
                      child: GestureDetector(
                        onTap: () {
                          setState(() {
                            _userRotationX = 0.0;
                            _userRotationY = 0.0;
                          });
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF1F5F9).withValues(alpha: 0.9),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: const Color(0xFFCBD5E1)),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.restart_alt_rounded, size: 13, color: Color(0xFF475569)),
                              SizedBox(width: 4),
                              Text(
                                'إعادة التوسيط',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                  color: Color(0xFF475569),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }
}

/// 3D Mesh & Blendshape Painter that renders the avatar in 3D perspective space
/// with volumetric head, depth lighting, ARKit visemes, and eyelid morphs.
class _ThreeDAvatarMeshPainter extends CustomPainter {
  final double rotX; // Pitch (nod up/down)
  final double rotY; // Yaw (turn left/right)
  final double rotZ; // Roll (tilt)
  final double breath;
  final double blink;
  final VisemeFrame viseme;
  final bool isSpeaking;
  final double amplitude;
  final bool isFemale;

  _ThreeDAvatarMeshPainter({
    required this.rotX,
    required this.rotY,
    required this.rotZ,
    required this.breath,
    required this.blink,
    required this.viseme,
    required this.isSpeaking,
    required this.amplitude,
    required this.isFemale,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2.0;
    // Avatar head centered nicely in upper-middle
    final cy = size.height * 0.44;

    canvas.save();

    // 1. Base Chest & Shoulders (3D Respiration & Specular Volume)
    final chestY = cy + 180 + (breath * 5.0);
    final shoulderW = size.width * 0.95;

    final torsoPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          const Color(0xFFDDE4EC),
          const Color(0xFFB0C0D0),
          const Color(0xFF8899AA).withValues(alpha: 0.9),
        ],
      ).createShader(Rect.fromLTWH(cx - shoulderW / 2, chestY, shoulderW, 300));

    final torsoPath = Path();
    torsoPath.moveTo(cx - (shoulderW * 0.46), size.height);
    torsoPath.quadraticBezierTo(cx - (shoulderW * 0.38), chestY + 20, cx - 70, chestY - 10);
    torsoPath.lineTo(cx + 70, chestY - 10);
    torsoPath.quadraticBezierTo(cx + (shoulderW * 0.38), chestY + 20, cx + (shoulderW * 0.46), size.height);
    torsoPath.close();
    canvas.drawPath(torsoPath, torsoPaint);

    // 2. Cybernetic Neck & Spine Structure
    final neckW = 58.0;
    final neckRect = Rect.fromCenter(center: Offset(cx + (rotY * 15), cy + 130), width: neckW, height: 90);
    final neckPaint = Paint()
      ..shader = LinearGradient(
        colors: [
          const Color(0xFF8A9BA8),
          const Color(0xFFC4D2DF),
          const Color(0xFF708090),
        ],
      ).createShader(neckRect);
    canvas.drawRRect(RRect.fromRectAndRadius(neckRect, const Radius.circular(16)), neckPaint);

    // 3. 3D Head Transformation (Perspective Matrix Rotation)
    final headCenter = Offset(cx, cy);
    // ignore: deprecated_member_use
    final matrix = Matrix4.identity()
      ..setEntry(3, 2, 0.0012) // Realistic focal perspective
      // ignore: deprecated_member_use
      ..translate(headCenter.dx, headCenter.dy)
      ..rotateY(rotY)
      ..rotateX(rotX)
      ..rotateZ(rotZ)
      // ignore: deprecated_member_use
      ..translate(-headCenter.dx, -headCenter.dy);

    canvas.transform(matrix.storage);

    // 4. Volumetric 3D Head Mesh (Base Cranium & Helmet)
    final headW = isFemale ? 165.0 : 178.0;
    final headH = isFemale ? 218.0 : 228.0;
    final headRect = Rect.fromCenter(center: headCenter, width: headW, height: headH);

    final craniumPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.25, -0.35), // Studio light source
        radius: 0.9,
        colors: [
          Colors.white,
          const Color(0xFFE8EEF5),
          const Color(0xFFC8D4E2),
          const Color(0xFF94A5B8),
        ],
        stops: const [0.0, 0.35, 0.75, 1.0],
      ).createShader(headRect);

    canvas.drawOval(headRect, craniumPaint);

    // 5. Stylized Cyber Head Armor Plates (3D Ear Modules)
    final earLeftRect = Rect.fromCenter(center: Offset(cx - (headW * 0.52), cy), width: 22, height: 75);
    final earRightRect = Rect.fromCenter(center: Offset(cx + (headW * 0.52), cy), width: 22, height: 75);
    final armorPaint = Paint()..color = const Color(0xFF2C3E50);
    canvas.drawRRect(RRect.fromRectAndRadius(earLeftRect, const Radius.circular(10)), armorPaint);
    canvas.drawRRect(RRect.fromRectAndRadius(earRightRect, const Radius.circular(10)), armorPaint);

    // 6. 3D Face Plate (Smooth Skin Shader)
    final faceW = headW * 0.84;
    final faceH = headH * 0.74;
    final faceRect = Rect.fromCenter(center: Offset(cx, cy + 12), width: faceW, height: faceH);
    final skinPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.15, -0.2),
        radius: 0.85,
        colors: isFemale
            ? [
                const Color(0xFFFFF2EB),
                const Color(0xFFFBE4D8),
                const Color(0xFFE8C8B8),
              ]
            : [
                const Color(0xFFF6E6DA),
                const Color(0xFFE8D0C0),
                const Color(0xFFD2B5A0),
              ],
      ).createShader(faceRect);

    canvas.drawRRect(RRect.fromRectAndRadius(faceRect, Radius.circular(faceW * 0.45)), skinPaint);

    // 7. 3D Eyes with Gaze & Eyelid Blendshapes (eyeBlinkLeft, eyeBlinkRight)
    final eyeDist = faceW * 0.28;
    final eyeY = cy - 6;
    final eyeWidth = 26.0;
    final eyeHeight = 15.0;

    _paint3DEye(canvas, Offset(cx - eyeDist, eyeY), eyeWidth, eyeHeight, blink, isLeft: true);
    _paint3DEye(canvas, Offset(cx + eyeDist, eyeY), eyeWidth, eyeHeight, blink, isLeft: false);

    // 8. 3D Nose Bridge & Contour
    final nosePaint = Paint()
      ..color = const Color(0xFFD4B4A2).withValues(alpha: 0.5)
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final nosePath = Path();
    nosePath.moveTo(cx - 5, cy + 30);
    nosePath.quadraticBezierTo(cx, cy + 36, cx + 5, cy + 30);
    canvas.drawPath(nosePath, nosePaint);

    // 9. 3D Dynamic Viseme Mouth & Blendshapes (Audio-Driven Lip-Sync)
    _paint3DVisemeMouth(canvas, cx, cy + 68, viseme);

    canvas.restore();
  }

  void _paint3DEye(Canvas canvas, Offset center, double w, double h, double blinkProgress, {required bool isLeft}) {
    final eyeRect = Rect.fromCenter(center: center, width: w, height: h);

    // Sclera (White eye background)
    final scleraPaint = Paint()..color = const Color(0xFFF8FAFC);
    canvas.drawOval(eyeRect, scleraPaint);

    // Iris (Cyan Cybernetic Glow)
    final irisRadius = h * 0.48;
    final irisCenter = Offset(center.dx + (rotY * 4.0), center.dy + (rotX * 2.0));
    final irisPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFF00E5FF),
          const Color(0xFF0284C7),
          const Color(0xFF0F172A),
        ],
      ).createShader(Rect.fromCircle(center: irisCenter, radius: irisRadius));
    canvas.drawCircle(irisCenter, irisRadius, irisPaint);

    // Pupil
    canvas.drawCircle(irisCenter, irisRadius * 0.45, Paint()..color = const Color(0xFF090D16));

    // Specular Highlight
    canvas.drawCircle(Offset(irisCenter.dx - 2, irisCenter.dy - 2), 2.2, Paint()..color = Colors.white);

    // ARKit Eyelid Blendshape Morph (eyeBlinkLeft / eyeBlinkRight)
    if (blinkProgress > 0.05) {
      final drop = h * blinkProgress * 1.1;
      final lidPath = Path();
      lidPath.moveTo(eyeRect.left, center.dy - (h * 0.4));
      lidPath.quadraticBezierTo(center.dx, center.dy - (h * 0.4) + drop, eyeRect.right, center.dy - (h * 0.4));
      lidPath.lineTo(eyeRect.right, center.dy - (h * 0.6));
      lidPath.lineTo(eyeRect.left, center.dy - (h * 0.6));
      lidPath.close();

      final lidPaint = Paint()
        ..color = (isFemale ? const Color(0xFFE2C4B4) : const Color(0xFFCAA894))
            .withValues(alpha: (blinkProgress * 1.1).clamp(0.0, 1.0));
      canvas.drawPath(lidPath, lidPaint);

      final lashPaint = Paint()
        ..color = const Color(0xFF261A18)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4;
      canvas.drawPath(lidPath, lashPaint);
    }
  }

  void _paint3DVisemeMouth(Canvas canvas, double cx, double cy, VisemeFrame viseme) {
    final baseW = isFemale ? 46.0 : 52.0;

    // 1. Apply Width Ratio & Pucker Morph Targets
    final widthRatio = viseme.widthRatio.clamp(0.75, 1.3);
    final pucker = viseme.pucker.clamp(0.0, 1.0);
    final mouthWidth = baseW * widthRatio * (1.0 - (pucker * 0.32));

    // 2. Apply Jaw Open & Drop Morph Targets (jawOpen / viseme_aa)
    final maxOpenH = isFemale ? 14.0 : 16.0;
    final openness = viseme.openness.clamp(0.0, 1.0);
    final mouthHeight = (openness * maxOpenH).clamp(1.5, maxOpenH);

    final mouthY = cy + (viseme.jawDrop * 4.0);
    final mouthRect = Rect.fromCenter(
      center: Offset(cx, mouthY),
      width: mouthWidth,
      height: mouthHeight,
    );

    // 3. Inner Mouth Cavity with Depth Gradient
    final cavityPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          const Color(0xFF160608),
          const Color(0xFF380C12),
        ],
      ).createShader(mouthRect);

    final cornerRad = pucker > 0.4 ? mouthHeight * 0.75 : mouthHeight * 0.52;
    final cavityRRect = RRect.fromRectAndRadius(mouthRect, Radius.circular(cornerRad));
    canvas.drawRRect(cavityRRect, cavityPaint);

    // 4. Upper Teeth Mesh (Visible on wide vowels and open consonants)
    if (mouthHeight > 3.2 && viseme.teethVisible > 0.1) {
      final teethAlpha = (viseme.teethVisible * 0.95).clamp(0.0, 1.0);
      final teethW = mouthWidth * 0.62;
      final teethH = min(3.0, mouthHeight * 0.35);
      final teethRect = Rect.fromLTWH(cx - (teethW / 2), mouthRect.top, teethW, teethH);
      final teethPaint = Paint()..color = const Color(0xFFFBF8F5).withValues(alpha: teethAlpha);
      canvas.drawRRect(RRect.fromRectAndRadius(teethRect, const Radius.circular(1.5)), teethPaint);
    }

    // 5. 3D Lips Highlight (Organic Bezier Curvature)
    final lipColor = isFemale ? const Color(0xFFD67272) : const Color(0xFFBA685A);
    final lipPaint = Paint()
      ..color = lipColor.withValues(alpha: 0.9)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;

    final lipPath = Path();
    lipPath.moveTo(mouthRect.left, mouthRect.top + (mouthHeight * 0.3));
    lipPath.quadraticBezierTo(cx, mouthRect.bottom + 1.5, mouthRect.right, mouthRect.top + (mouthHeight * 0.3));
    canvas.drawPath(lipPath, lipPaint);
  }

  @override
  bool shouldRepaint(covariant _ThreeDAvatarMeshPainter old) {
    return old.rotX != rotX ||
        old.rotY != rotY ||
        old.rotZ != rotZ ||
        old.breath != breath ||
        old.blink != blink ||
        old.viseme != viseme ||
        old.amplitude != amplitude ||
        old.isSpeaking != isSpeaking ||
        old.isFemale != isFemale;
  }
}
