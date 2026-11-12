import 'dart:async';
import 'dart:math';
import 'package:flutter/foundation.dart';

/// Supported high-level states for the 3D Avatar
enum AvatarBehaviorState {
  idle,
  listening,
  talking,
  lookLeft,
  lookRight,
  lookForward,
  lookUp,
  lookDown,
}

/// Independent, reusable controller for 3D GLB/GLTF Avatar animation and behaviors.
/// Can be driven via mock commands or connected directly to backend WebSocket / REST events.
class Avatar3DController {
  Avatar3DController({
    AvatarBehaviorState initialState = AvatarBehaviorState.idle,
    bool enableMockScheduler = false,
  }) : _state = ValueNotifier<AvatarBehaviorState>(initialState) {
    if (enableMockScheduler) {
      startMockCommandScheduler();
    }
  }

  final ValueNotifier<AvatarBehaviorState> _state;
  ValueListenable<AvatarBehaviorState> get stateListenable => _state;
  AvatarBehaviorState get currentState => _state.value;

  // Real-time kinematic and morph parameter notifiers for the 3D engine
  final ValueNotifier<double> mouthOpenness = ValueNotifier<double>(0.0);
  final ValueNotifier<double> blinkWeight = ValueNotifier<double>(0.0);
  final ValueNotifier<double> headPitch = ValueNotifier<double>(0.0); // Up/Down tilt (X axis)
  final ValueNotifier<double> headYaw = ValueNotifier<double>(0.0);   // Left/Right turn (Y axis)
  final ValueNotifier<double> headRoll = ValueNotifier<double>(0.0);  // Cant tilt (Z axis)
  final ValueNotifier<double> eyeGazeX = ValueNotifier<double>(0.0);  // Eye gaze horizontal (-1.0 to 1.0)
  final ValueNotifier<double> eyeGazeY = ValueNotifier<double>(0.0);  // Eye gaze vertical (-1.0 to 1.0)
  final ValueNotifier<double> breathingPhase = ValueNotifier<double>(0.0);

  // Active morph target viseme weights for realistic human lip sync
  final ValueNotifier<Map<String, double>> visemeWeights = ValueNotifier<Map<String, double>>({});

  Timer? _mockSchedulerTimer;
  Timer? _simulationLoopTimer;
  Timer? _blinkTimer;
  final Random _random = Random();
  double _time = 0.0;
  bool _isDisposed = false;

  /// Starts the internal simulation loop that calculates organic continuous micro-movements
  /// (breathing, micro-saccades, subtle head sway) according to current state.
  void startSimulation() {
    _simulationLoopTimer?.cancel();
    _scheduleNextBlink();
    _simulationLoopTimer = Timer.periodic(const Duration(milliseconds: 20), (timer) {
      if (_isDisposed) {
        timer.cancel();
        return;
      }
      _time += 0.02;
      _updateKinematics();
    });
  }

  void _scheduleNextBlink() {
    _blinkTimer?.cancel();
    if (_isDisposed) return;
    // Natural human blink every 2.8 to 5.2 seconds
    final delayMs = 2800 + _random.nextInt(2400);
    _blinkTimer = Timer(Duration(milliseconds: delayMs), () {
      _executeBlink();
      _scheduleNextBlink();
    });
  }

  void _executeBlink() {
    if (_isDisposed) return;
    // 120ms organic blink envelope: 50ms close, 20ms hold, 50ms open
    const blinkDurationMs = 120;
    const stepMs = 20;
    int elapsed = 0;

    Timer.periodic(const Duration(milliseconds: stepMs), (timer) {
      elapsed += stepMs;
      final t = elapsed / blinkDurationMs;
      if (t >= 1.0 || _isDisposed) {
        blinkWeight.value = 0.0;
        timer.cancel();
      } else if (t < 0.45) {
        blinkWeight.value = (t / 0.45).clamp(0.0, 1.0);
      } else if (t < 0.55) {
        blinkWeight.value = 1.0;
      } else {
        blinkWeight.value = (1.0 - ((t - 0.55) / 0.45)).clamp(0.0, 1.0);
      }
    });
  }

  void _updateKinematics() {
    // 1. Natural Breathing cycle (4.0s full sine wave)
    final breath = (sin(_time * 1.57) * 0.5 + 0.5);
    breathingPhase.value = breath;

    // 2. Kinematics depending on current behavior state
    switch (_state.value) {
      case AvatarBehaviorState.idle:
        // Subtle ambient head sway
        final targetYaw = sin(_time * 0.45) * 0.08 + sin(_time * 0.22) * 0.03;
        final targetPitch = cos(_time * 0.6) * 0.03 + (breath * 0.015);
        final targetRoll = sin(_time * 0.35) * 0.02;

        headYaw.value = _lerp(headYaw.value, targetYaw, 0.06);
        headPitch.value = _lerp(headPitch.value, targetPitch, 0.06);
        headRoll.value = _lerp(headRoll.value, targetRoll, 0.06);

        // Gentle eye exploration
        eyeGazeX.value = _lerp(eyeGazeX.value, sin(_time * 0.5) * 0.35, 0.08);
        eyeGazeY.value = _lerp(eyeGazeY.value, cos(_time * 0.7) * 0.15, 0.08);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.12);
        break;

      case AvatarBehaviorState.listening:
        // Attentive head tilt, focused forward gaze, closed mouth
        headYaw.value = _lerp(headYaw.value, 0.02, 0.08);
        headPitch.value = _lerp(headPitch.value, 0.04 + (breath * 0.01), 0.08); // Slight forward nod
        headRoll.value = _lerp(headRoll.value, 0.03, 0.08); // Gentle attentive cant
        eyeGazeX.value = _lerp(eyeGazeX.value, 0.0, 0.1);
        eyeGazeY.value = _lerp(eyeGazeY.value, 0.0, 0.1);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.15);
        break;

      case AvatarBehaviorState.talking:
        // Dynamic realistic speech cadence with animated mouth and head cadence
        final speechFreq = sin(_time * 11.0) * cos(_time * 7.5);
        final speechOpen = ((speechFreq.abs() * 0.75) + (sin(_time * 15.0).abs() * 0.25)).clamp(0.08, 0.85);

        mouthOpenness.value = _lerp(mouthOpenness.value, speechOpen, 0.25);
        headPitch.value = _lerp(headPitch.value, sin(_time * 3.5) * 0.04 + 0.02, 0.1);
        headYaw.value = _lerp(headYaw.value, sin(_time * 1.8) * 0.06, 0.08);
        headRoll.value = _lerp(headRoll.value, cos(_time * 2.2) * 0.025, 0.08);

        eyeGazeX.value = _lerp(eyeGazeX.value, sin(_time * 1.2) * 0.15, 0.08);
        eyeGazeY.value = _lerp(eyeGazeY.value, cos(_time * 1.5) * 0.1, 0.08);
        break;

      case AvatarBehaviorState.lookLeft:
        headYaw.value = _lerp(headYaw.value, 0.28, 0.08);
        headPitch.value = _lerp(headPitch.value, 0.01, 0.08);
        eyeGazeX.value = _lerp(eyeGazeX.value, 0.7, 0.12);
        eyeGazeY.value = _lerp(eyeGazeY.value, 0.0, 0.1);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.1);
        break;

      case AvatarBehaviorState.lookRight:
        headYaw.value = _lerp(headYaw.value, -0.28, 0.08);
        headPitch.value = _lerp(headPitch.value, 0.01, 0.08);
        eyeGazeX.value = _lerp(eyeGazeX.value, -0.7, 0.12);
        eyeGazeY.value = _lerp(eyeGazeY.value, 0.0, 0.1);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.1);
        break;

      case AvatarBehaviorState.lookForward:
        headYaw.value = _lerp(headYaw.value, 0.0, 0.09);
        headPitch.value = _lerp(headPitch.value, 0.0, 0.09);
        headRoll.value = _lerp(headRoll.value, 0.0, 0.09);
        eyeGazeX.value = _lerp(eyeGazeX.value, 0.0, 0.12);
        eyeGazeY.value = _lerp(eyeGazeY.value, 0.0, 0.12);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.1);
        break;

      case AvatarBehaviorState.lookUp:
        headPitch.value = _lerp(headPitch.value, -0.22, 0.08);
        headYaw.value = _lerp(headYaw.value, 0.0, 0.08);
        eyeGazeY.value = _lerp(eyeGazeY.value, 0.55, 0.12);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.1);
        break;

      case AvatarBehaviorState.lookDown:
        headPitch.value = _lerp(headPitch.value, 0.22, 0.08);
        headYaw.value = _lerp(headYaw.value, 0.0, 0.08);
        eyeGazeY.value = _lerp(eyeGazeY.value, -0.55, 0.12);
        mouthOpenness.value = _lerp(mouthOpenness.value, 0.0, 0.1);
        break;
    }
  }

  double _lerp(double current, double target, double rate) {
    return current + (target - current) * rate;
  }

  /// Sets behavior state explicitly
  void setState(AvatarBehaviorState newState) {
    if (_state.value != newState) {
      _state.value = newState;
    }
  }

  /// High-level backend command receiver.
  /// Handles future commands from WebSockets, REST, or LLM agent instructions:
  /// Examples: 'idle', 'listening', 'talking', 'look_left', 'look_right', 'look_forward', 'look_up', 'look_down'
  void handleCommand(String command, {Map<String, dynamic>? params}) {
    switch (command.toLowerCase().trim()) {
      case 'idle':
        setState(AvatarBehaviorState.idle);
        break;
      case 'listening':
        setState(AvatarBehaviorState.listening);
        break;
      case 'talking':
      case 'speak':
        setState(AvatarBehaviorState.talking);
        break;
      case 'look_left':
        setState(AvatarBehaviorState.lookLeft);
        break;
      case 'look_right':
        setState(AvatarBehaviorState.lookRight);
        break;
      case 'look_forward':
      case 'look_center':
        setState(AvatarBehaviorState.lookForward);
        break;
      case 'look_up':
        setState(AvatarBehaviorState.lookUp);
        break;
      case 'look_down':
        setState(AvatarBehaviorState.lookDown);
        break;
      default:
        setState(AvatarBehaviorState.idle);
    }
  }

  /// Runs periodic mock commands for autonomous testing and previewing behaviors
  void startMockCommandScheduler() {
    _mockSchedulerTimer?.cancel();
    final mockSequence = [
      AvatarBehaviorState.idle,
      AvatarBehaviorState.lookLeft,
      AvatarBehaviorState.lookRight,
      AvatarBehaviorState.listening,
      AvatarBehaviorState.talking,
      AvatarBehaviorState.lookForward,
    ];
    int step = 0;

    _mockSchedulerTimer = Timer.periodic(const Duration(seconds: 4), (timer) {
      if (_isDisposed) {
        timer.cancel();
        return;
      }
      step = (step + 1) % mockSequence.length;
      setState(mockSequence[step]);
    });
  }

  void stopMockCommandScheduler() {
    _mockSchedulerTimer?.cancel();
    _mockSchedulerTimer = null;
  }

  void dispose() {
    _isDisposed = true;
    _mockSchedulerTimer?.cancel();
    _simulationLoopTimer?.cancel();
    _blinkTimer?.cancel();
    _state.dispose();
    mouthOpenness.dispose();
    blinkWeight.dispose();
    headPitch.dispose();
    headYaw.dispose();
    headRoll.dispose();
    eyeGazeX.dispose();
    eyeGazeY.dispose();
    breathingPhase.dispose();
    visemeWeights.dispose();
  }
}
