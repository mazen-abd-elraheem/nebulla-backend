import 'dart:math';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/avatar_3d_controller.dart';
import 'avatar_3d_widget.dart';

/// Photorealistic Real 3D Female Human Virtual Assistant Avatar.
/// - Renders the rigged 3D human model (`female_avatar.glb`) inside Three.js WebGL canvas.
/// - Controlled independently by [Avatar3DController].
/// - All 4 Behaviors implemented with 72 facial morph targets and bone kinematics:
///   1. IDLE: Continuous organic eye blinking, gaze exploring right/left, subtle head sway, natural breathing.
///   2. LISTENING: Eyes locked forward, mouth closed, attentive slight nod.
///   3. TALKING: Realistic mouth cavity and jaw opening synced with speech volume.
///   4. LOOKING: Smooth gaze transitions (left, right, up, down, forward).
class InteractiveAnimatedAvatar extends StatefulWidget {
  final String? avatarType; // 'male' or 'female'
  final bool fullScreen;
  final double? width;
  final double? height;
  final VoidCallback? onAvatarTapped;
  final VoidCallback? onAvatarDoubleTapped;
  final Avatar3DController? controller;

  const InteractiveAnimatedAvatar({
    super.key,
    this.avatarType,
    this.fullScreen = false,
    this.width,
    this.height,
    this.onAvatarTapped,
    this.onAvatarDoubleTapped,
    this.controller,
  });

  @override
  State<InteractiveAnimatedAvatar> createState() =>
      _InteractiveAnimatedAvatarState();
}

class _InteractiveAnimatedAvatarState extends State<InteractiveAnimatedAvatar> {
  final _audioService = AvatarAudioService.instance;
  late final Avatar3DController _controller;
  bool _createdOwnController = false;

  @override
  void initState() {
    super.initState();
    if (widget.controller != null) {
      _controller = widget.controller!;
    } else {
      _controller = Avatar3DController(enableMockScheduler: true);
      _createdOwnController = true;
    }

    _listenToAudioService();
  }

  void _listenToAudioService() {
    _audioService.isSpeaking.addListener(_onSpeakingChanged);
    _audioService.speechAmplitude.addListener(_onAmplitudeChanged);
    _audioService.currentViseme.addListener(_onVisemeChanged);
  }

  void _onSpeakingChanged() {
    if (_audioService.isSpeaking.value) {
      _controller.setState(AvatarBehaviorState.talking);
    } else {
      _controller.setState(AvatarBehaviorState.idle);
    }
  }

  void _onAmplitudeChanged() {
    if (_audioService.isSpeaking.value) {
      final amp = _audioService.speechAmplitude.value;
      _controller.mouthOpenness.value = (_controller.mouthOpenness.value * 0.3 + amp * 0.7).clamp(0.0, 1.0);
    }
  }

  void _onVisemeChanged() {
    if (_audioService.isSpeaking.value) {
      final viseme = _audioService.currentViseme.value;
      final targetOpen = (viseme.openness * 0.8 + _audioService.speechAmplitude.value * 0.2).clamp(0.0, 1.0);
      _controller.mouthOpenness.value = targetOpen;
    }
  }

  @override
  void dispose() {
    _audioService.isSpeaking.removeListener(_onSpeakingChanged);
    _audioService.speechAmplitude.removeListener(_onAmplitudeChanged);
    _audioService.currentViseme.removeListener(_onVisemeChanged);
    if (_createdOwnController) {
      _controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final availableW = widget.width ?? constraints.maxWidth;
        final availableH = widget.height ?? constraints.maxHeight;

        final portraitW = widget.fullScreen ? availableW : min(availableW, 440.0);
        final portraitH = availableH;

        return Center(
          child: SizedBox(
            width: portraitW,
            height: portraitH,
            child: Avatar3DWidget(
              controller: _controller,
              width: portraitW,
              height: portraitH,
              onTap: () {
                if (widget.onAvatarTapped != null) {
                  widget.onAvatarTapped!();
                } else {
                  _cycleBehaviorOnTap();
                }
              },
              onDoubleTap: widget.onAvatarDoubleTapped,
            ),
          ),
        );
      },
    );
  }

  void _cycleBehaviorOnTap() {
    switch (_controller.currentState) {
      case AvatarBehaviorState.idle:
        _controller.setState(AvatarBehaviorState.listening);
        break;
      case AvatarBehaviorState.listening:
        _controller.setState(AvatarBehaviorState.talking);
        break;
      case AvatarBehaviorState.talking:
        _controller.setState(AvatarBehaviorState.lookLeft);
        break;
      case AvatarBehaviorState.lookLeft:
        _controller.setState(AvatarBehaviorState.lookRight);
        break;
      case AvatarBehaviorState.lookRight:
        _controller.setState(AvatarBehaviorState.lookForward);
        break;
      case AvatarBehaviorState.lookForward:
      case AvatarBehaviorState.lookUp:
      case AvatarBehaviorState.lookDown:
        _controller.setState(AvatarBehaviorState.idle);
        break;
    }
  }
}
