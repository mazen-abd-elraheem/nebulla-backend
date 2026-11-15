import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import '../models/avatar_profile.dart';
import 'api_service.dart';
import 'storage_service.dart';
import 'audio_viseme_analyzer.dart';

/// Manages real-time audio playback, backend speech synthesis,
/// and live synchronization with avatar facial expressions and lip-sync.
class AvatarAudioService {
  AvatarAudioService._();
  static final AvatarAudioService instance = AvatarAudioService._();

  final ValueNotifier<bool> isSpeaking = ValueNotifier<bool>(false);
  final ValueNotifier<double> speechAmplitude = ValueNotifier<double>(0.0);
  final ValueNotifier<VisemeFrame> currentViseme = ValueNotifier<VisemeFrame>(VisemeFrame.neutral);
  final ValueNotifier<String> currentEmotion = ValueNotifier<String>('neutral');
  final ValueNotifier<String> currentFaceEmoji = ValueNotifier<String>('😐');
  final ValueNotifier<String> activeAvatarType = ValueNotifier<String>('female'); // 'male' | 'female'
  final ValueNotifier<int> activePersonalityId = ValueNotifier<int>(1);
  final ValueNotifier<String> activePersonaName = ValueNotifier<String>('المساعد الذكي');
  final ValueNotifier<AvatarProfileModel?> activeAvatar = ValueNotifier<AvatarProfileModel?>(null);

  bool _avatarLoadedOnce = false;
  String? _lastAvatarToken;

  Timer? _amplitudeTimer;
  Process? _activeAudioProcess;
  File? _lastAudioFile;

  void setPersonaName(String name) {
    final clean = name.trim();
    if (clean.isNotEmpty) {
      activePersonaName.value = clean;
    }
  }

  /// Update locally active GAGAvatar profile for all mounted avatars.
  void setActiveAvatar(AvatarProfileModel? avatar) {
    activeAvatar.value = avatar;
    _avatarLoadedOnce = true;
    if (avatar?.name != null && avatar!.name!.trim().isNotEmpty) {
      activePersonaName.value = avatar.name!.trim();
    }
  }

  /// Fetch active approved avatar from backend on startup / after login.
  Future<void> loadActiveAvatar({bool force = false, int? personalityId}) async {
    final currentToken = StorageService.instance.getToken();
    if (_avatarLoadedOnce && !force && _lastAvatarToken == currentToken) return;
    _avatarLoadedOnce = true;
    _lastAvatarToken = currentToken;
    try {
      final params = <String, dynamic>{};
      if (personalityId != null) params['personality_id'] = personalityId;
      final data = await ApiService.instance.get('/api/v1/avatar/active', params);
      if (data is Map<String, dynamic> &&
          data['has_avatar'] == true &&
          data['avatar'] is Map<String, dynamic>) {
        setActiveAvatar(AvatarProfileModel.fromJson(data['avatar'] as Map<String, dynamic>));
      } else {
        setActiveAvatar(null);
      }
    } catch (e) {
      debugPrint('AvatarAudioService loadActiveAvatar notice: $e');
    }
  }

  /// Switch the active avatar character appearance ('male' or 'female')
  void switchAvatar(String type, {String? name}) {
    if (type == 'male' || type == 'female') {
      activeAvatarType.value = type;
      activePersonalityId.value = (type == 'male') ? 1 : 2;
      if (name != null && name.trim().isNotEmpty) {
        activePersonaName.value = name.trim();
      }
    }
  }

  static const Map<String, String> _emojiToExpression = {
    '😐': 'neutral',
    '😊': 'happy',
    '😃': 'happy',
    '😄': 'happy',
    '😂': 'laugh',
    '🤣': 'laugh',
    '😍': 'love',
    '🥰': 'love',
    '❤️': 'love',
    '😢': 'sad',
    '😭': 'sad',
    '😮': 'surprised',
    '😲': 'surprised',
    '😡': 'angry',
    '😠': 'angry',
    '🤔': 'thinking',
    '😉': 'wink',
    '😴': 'sleepy',
    '👋': 'wave',
    '👍': 'like',
  };

  static const Map<String, String> _expressionToEmoji = {
    'neutral': '😐',
    'happy': '😊',
    'laugh': '😂',
    'love': '😍',
    'sad': '😢',
    'surprised': '😮',
    'angry': '😡',
    'thinking': '🤔',
    'wink': '😉',
    'sleepy': '😴',
    'wave': '👋',
    'like': '👍',
  };

  /// Apply an incoming face-emoji or expression payload from LLM / WebSocket.
  void applyEmojiAction({
    String? faceEmoji,
    String? expression,
    Map<String, dynamic>? avatarAction,
  }) {
    final actionEmoji = avatarAction?['face_emoji'] as String?;
    final actionExpr = avatarAction?['expression'] as String?;

    final chosenEmoji = faceEmoji ?? actionEmoji;
    String? chosenExpr = expression ?? actionExpr;

    if (chosenExpr == null && chosenEmoji != null) {
      chosenExpr = _emojiToExpression[chosenEmoji];
    }
    if (chosenExpr != null && chosenExpr.isNotEmpty) {
      currentEmotion.value = chosenExpr;
    }
    if (chosenEmoji != null && chosenEmoji.isNotEmpty) {
      currentFaceEmoji.value = chosenEmoji;
    } else if (chosenExpr != null) {
      currentFaceEmoji.value = _expressionToEmoji[chosenExpr] ?? '😐';
    }
  }

  /// Synthesizes and speaks text using the backend audio pipeline,
  /// animating the avatar in real time with its expression & cloned voice.
  Future<void> speak(
    String text, {
    String? emotion,
    String? faceEmoji,
    String? expression,
    Map<String, dynamic>? avatarAction,
    int? personalityId,
  }) async {
    final detectedEmoji = faceEmoji ??
        (avatarAction?['face_emoji'] as String?) ??
        _extractFaceEmojiFromText(text);

    // Strip HTML, [tags], and Unicode face emojis before TTS so cloned voice never reads them aloud
    final clean = text
        .replaceAll(RegExp(r'<[^>]*>'), '')
        .replaceAll(RegExp(r'\[[^\]]+\]'), '')
        .replaceAll(
          RegExp(r'[\u{1F1E0}-\u{1F9FF}\u{1FA00}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0E\uFE0F\u200D]', unicode: true),
          ' ',
        )
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (clean.isEmpty) return;

    final targetPid = personalityId ?? activePersonalityId.value;
    final resolvedExpr = expression ??
        (avatarAction?['expression'] as String?) ??
        (detectedEmoji != null ? _emojiToExpression[detectedEmoji] : null) ??
        emotion ??
        _detectEmotion(clean);

    applyEmojiAction(
      faceEmoji: detectedEmoji,
      expression: resolvedExpr,
      avatarAction: avatarAction,
    );

    try {
      // 1. Fetch audio from backend (supports /api/v1/voice-clone/synthesize or /api/v1/audio/voicetut)
      Uint8List? audioBytes;
      try {
        final baseUrl = StorageService.instance.getBaseUrl().replaceAll('localhost', '127.0.0.1');
        final uri = Uri.parse(
          '$baseUrl/api/v1/voice-clone/synthesize?text=${Uri.encodeComponent(clean)}&personality_id=$targetPid',
        );

        final token = StorageService.instance.getToken();
        final client = HttpClient();
        client.connectionTimeout = const Duration(seconds: 8);

        final req = await client.getUrl(uri);
        req.headers.set('Accept', 'audio/wav');
        if (token != null) {
          req.headers.set('Authorization', 'Bearer $token');
        }

        final res = await req.close().timeout(const Duration(seconds: 12));
        if (res.statusCode == 200) {
          final builder = BytesBuilder();
          await for (final chunk in res) {
            builder.add(chunk);
          }
          final bytes = builder.takeBytes();
          if (bytes.length > 500) {
            audioBytes = bytes;
          }
        }
      } catch (e) {
        debugPrint('AvatarAudioService voice-clone fetch notice: $e');
      }

      // Fallback to voicetut endpoint if needed
      if (audioBytes == null) {
        try {
          final baseUrl = StorageService.instance.getBaseUrl().replaceAll('localhost', '127.0.0.1');
          final uri = Uri.parse('$baseUrl/api/v1/audio/voicetut');
          final token = StorageService.instance.getToken();
          final client = HttpClient();
          final req = await client.postUrl(uri);
          req.headers.set('Content-Type', 'application/x-www-form-urlencoded');
          if (token != null) req.headers.set('Authorization', 'Bearer $token');
          final bodyData = 'text=${Uri.encodeQueryComponent(clean)}&speaker=${targetPid == 1 ? "mazen" : "yasmin"}';
          req.add(utf8.encode(bodyData));
          final res = await req.close().timeout(const Duration(seconds: 10));
          if (res.statusCode == 200) {
            final builder = BytesBuilder();
            await for (final chunk in res) {
              builder.add(chunk);
            }
            final b = builder.takeBytes();
            if (b.length > 500) audioBytes = b;
          }
        } catch (_) {}
      }

      // Calculate approximate speech duration (standard speech is ~3.5 words/sec or ~14 chars/sec)
      final estimatedDurationMs = max(
        1800,
        (clean.length * 75).clamp(1800, 14000),
      );

      // 2. Play audio natively on Windows or platform
      if (audioBytes != null && audioBytes.isNotEmpty && Platform.isWindows) {
        await _playWavOnWindows(audioBytes, estimatedDurationMs);
      } else if (Platform.isWindows) {
        // Fallback: Speak with native Windows speech synthesizer so sound ALWAYS plays
        await _speakWindowsNativeFallback(clean, estimatedDurationMs);
      } else {
        // Fallback simulation when offline/soundcard busy
        _startLipSyncPulse(estimatedDurationMs);
      }
    } catch (e) {
      debugPrint('AvatarAudioService speak error: $e');
      if (Platform.isWindows) {
        _speakWindowsNativeFallback(clean, 3000);
      } else {
        _startLipSyncPulse(3000);
      }
    }
  }

  Future<void> _speakWindowsNativeFallback(String cleanText, int durationMs) async {
    _startLipSyncPulse(durationMs);
    try {
      final safe = cleanText.replaceAll("'", "''").replaceAll('"', ' ');
      final tempDir = Directory.systemTemp;
      final ts = DateTime.now().millisecondsSinceEpoch;
      final script = File('${tempDir.path}\\speak_$ts.ps1');
      await script.writeAsString("""
Add-Type -AssemblyName System.Speech
\$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
\$synth.Speak('$safe')
""");
      _activeAudioProcess = await Process.start('powershell', [
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        script.path,
      ]);
      _activeAudioProcess?.exitCode.then((_) {
        try {
          if (script.existsSync()) script.deleteSync();
        } catch (_) {}
      });
    } catch (_) {}
  }

  Future<void> _playWavOnWindows(Uint8List audioBytes, int fallbackDurationMs) async {
    try {
      stop();
      final isMp3 = audioBytes.length >= 3 &&
          ((audioBytes[0] == 0x49 && audioBytes[1] == 0x44 && audioBytes[2] == 0x33) ||
           (audioBytes[0] == 0xFF && (audioBytes[1] & 0xE0) == 0xE0));
      final ext = isMp3 ? 'mp3' : 'wav';
      final tempDir = Directory.systemTemp;
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final tempFile = File('${tempDir.path}\\nebula_speech_$timestamp.$ext');
      await tempFile.writeAsBytes(audioBytes, flush: true);
      _lastAudioFile = tempFile;

      int durationMs = fallbackDurationMs;
      if (!isMp3 && audioBytes.length > 44) {
        try {
          final byteData = ByteData.sublistView(audioBytes);
          final byteRate = byteData.getUint32(28, Endian.little);
          if (byteRate > 0) {
            durationMs = ((audioBytes.length - 44) * 1000 / byteRate).round();
          }
        } catch (_) {}
      }

      _startLipSyncPulse(durationMs, audioBytes);

      final safePath = tempFile.absolute.path.replaceAll('/', '\\').replaceAll("'", "''");
      final psScript = isMp3
          ? """
\$wmp = New-Object -ComObject WMPlayer.OCX
\$wmp.settings.volume = 100
\$wmp.URL = '$safePath'
\$wmp.controls.play()
Start-Sleep -Milliseconds 300
while (\$wmp.playState -eq 3 -or \$wmp.playState -eq 6 -or \$wmp.playState -eq 9) {
    Start-Sleep -Milliseconds 100
}
"""
          : """
\$sp = New-Object System.Media.SoundPlayer '$safePath'
\$sp.PlaySync()
""";
      final scriptFile = File('${tempDir.path}\\play_$timestamp.ps1');
      await scriptFile.writeAsString(psScript);

      _activeAudioProcess = await Process.start('powershell', [
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        scriptFile.path,
      ]);

      _activeAudioProcess?.exitCode.then((_) {
        try {
          if (scriptFile.existsSync()) scriptFile.deleteSync();
        } catch (_) {}
        _cleanupAudioFile(tempFile);
      });
    } catch (e) {
      debugPrint('Windows native sound playback error: $e');
      _startLipSyncPulse(fallbackDurationMs);
    }
  }

  void _startLipSyncPulse(int durationMs, [Uint8List? audioBytes]) {
    _amplitudeTimer?.cancel();
    isSpeaking.value = true;

    final analyzer = AudioVisemeAnalyzer.instance;
    final frames = analyzer.analyzeAudioTrack(audioBytes ?? Uint8List(0), durationMs);

    final start = DateTime.now();

    // High fidelity 50 FPS (every 20ms) viseme playback loop
    _amplitudeTimer = Timer.periodic(const Duration(milliseconds: 20), (timer) {
      final elapsed = DateTime.now().difference(start).inMilliseconds;
      if (elapsed >= durationMs) {
        stop();
        return;
      }

      final frameIndex = (elapsed ~/ 20).clamp(0, frames.length - 1);
      final current = frames[frameIndex];
      final next = (frameIndex + 1 < frames.length) ? frames[frameIndex + 1] : current;
      final subT = ((elapsed % 20) / 20.0).clamp(0.0, 1.0);

      final smoothFrame = VisemeFrame.lerp(current, next, subT);
      currentViseme.value = smoothFrame;
      speechAmplitude.value = smoothFrame.openness;
    });
  }

  void stop() {
    _amplitudeTimer?.cancel();
    _amplitudeTimer = null;
    isSpeaking.value = false;
    speechAmplitude.value = 0.0;
    currentViseme.value = VisemeFrame.neutral;
    try {
      _activeAudioProcess?.kill();
      _activeAudioProcess = null;
    } catch (_) {}
    if (_lastAudioFile != null) {
      _cleanupAudioFile(_lastAudioFile!);
      _lastAudioFile = null;
    }
  }

  void _cleanupAudioFile(File file) {
    Future.delayed(const Duration(seconds: 3), () async {
      try {
        if (await file.exists()) {
          await file.delete();
        }
      } catch (_) {}
    });
  }

  String? _extractFaceEmojiFromText(String text) {
    for (final entry in _emojiToExpression.entries) {
      if (text.contains(entry.key)) {
        return entry.key;
      }
    }
    return null;
  }

  String _detectEmotion(String text) {
    final em = _extractFaceEmojiFromText(text);
    if (em != null) return _emojiToExpression[em] ?? 'neutral';
    if (text.contains('سعيد') || text.contains('ممتاز') || text.contains('رائع') || text.contains('مرحباً') || text.contains('أهلاً')) {
      return 'happy';
    }
    if (text.contains('؟') || text.contains('هل') || text.contains('لماذا') || text.contains('كيف')) {
      return 'thinking';
    }
    if (text.contains('خطأ') || text.contains('تحذير') || text.contains('انتبه')) {
      return 'serious';
    }
    if (text.contains('بالتأكيد') || text.contains('نعم') || text.contains('حسناً')) {
      return 'confident';
    }
    return 'neutral';
  }
}
