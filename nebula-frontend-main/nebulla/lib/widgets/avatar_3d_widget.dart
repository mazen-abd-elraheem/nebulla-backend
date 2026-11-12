import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:webview_windows/webview_windows.dart';
import '../services/avatar_3d_controller.dart';
import '../services/avatar_3d_server.dart';

/// Real 3D Human Female Avatar Component.
/// - Embeds high-fidelity Three.js WebGL canvas running the real rigged GLB model.
/// - Facial Blendshapes: natural blinking (`eyeBlinkLeft`/`Right`), realistic speech mouth/jaw opening (`mouthOpen`/`jawOpen`).
/// - Skeletal Kinematics: head/neck rotations (pitch, yaw, roll).
/// - Dynamic Eye Gaze: look left, right, up, down.
/// - Continuous idle animation and breathing.
class Avatar3DWidget extends StatefulWidget {
  final Avatar3DController controller;
  final double? width;
  final double? height;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;

  const Avatar3DWidget({
    super.key,
    required this.controller,
    this.width,
    this.height,
    this.onTap,
    this.onDoubleTap,
  });

  @override
  State<Avatar3DWidget> createState() => _Avatar3DWidgetState();
}

class _Avatar3DWidgetState extends State<Avatar3DWidget> {
  final WebviewController _webviewController = WebviewController();
  bool _initialized = false;
  Timer? _syncTimer;

  @override
  void initState() {
    super.initState();
    widget.controller.startSimulation();
    if (!kIsWeb && Platform.isWindows) {
      _init3DWebView();
    }
    _startKinematicSync();
  }

  Future<void> _init3DWebView() async {
    try {
      await Avatar3DServer.instance.ensureStarted();
      await _webviewController.initialize();
      await _webviewController.setBackgroundColor(Colors.transparent);

      final url = '${Avatar3DServer.instance.baseUrl}/assets/3d/avatar_3d.html';
      await _webviewController.loadUrl(url);

      if (mounted) {
        setState(() => _initialized = true);
      }
    } catch (_) {
      if (mounted) {
        setState(() => _initialized = false);
      }
    }
  }

  void _startKinematicSync() {
    // 50 FPS high-rate smooth parameter streaming to the 3D GLB engine
    _syncTimer = Timer.periodic(const Duration(milliseconds: 20), (_) {
      if (!_initialized || !mounted) return;

      final payload = jsonEncode({
        'mouth': widget.controller.mouthOpenness.value,
        'blink': widget.controller.blinkWeight.value,
        'pitch': widget.controller.headPitch.value,
        'yaw': widget.controller.headYaw.value,
        'roll': widget.controller.headRoll.value,
        'gazeX': widget.controller.eyeGazeX.value,
        'gazeY': widget.controller.eyeGazeY.value,
        'breath': widget.controller.breathingPhase.value,
      });

      _webviewController.executeScript('if (window.updateAvatar) window.updateAvatar($payload);');
    });
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    if (_initialized) {
      _webviewController.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onDoubleTap: widget.onDoubleTap,
      child: SizedBox(
        width: widget.width,
        height: widget.height,
        child: Stack(
          alignment: Alignment.center,
          children: [
            if (_initialized)
              Webview(
                _webviewController,
                permissionRequested: (_, _, _) async => WebviewPermissionDecision.allow,
              )
            else
              const Center(
                child: SizedBox(
                  width: 32,
                  height: 32,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.2,
                    color: Color(0xFF00E5FF),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
