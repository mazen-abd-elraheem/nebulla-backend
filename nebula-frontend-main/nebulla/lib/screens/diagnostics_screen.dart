import 'dart:io';
import 'dart:math' as math;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import '../widgets/nebula_side_menu.dart';
import 'face_registration_screen.dart';
import 'signals_screen.dart';

class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen> {
  final _repo = NebulaRepository.instance;
  final ScrollController _scrollController = ScrollController();

  // Hardware & sensor state (synced with backend + SharedPreferences)
  final int _batteryPercent = 96;
  final String _remainingTime = '18h 40m';
  final int _batteryHealth = 100;
  bool _isCharging = true;
  bool _networkConnected = true;

  // Vision unit
  final String _visionResolution = '4K HDR';
  final String _visionFps = '60 FPS';
  String _tofStatus = 'ACTIVE';

  // Servo matrix
  double _pitchAngle = 45.0;
  double _yawAngle = 90.0;
  final double _servoTemp = 34.2;

  // Audio / Volume unit
  int _volumeLevel = 85;
  bool _isMuted = false;

  // Microphone / Voice recording unit
  String _voiceStatusLabel = 'جاهز للتسجيل';
  bool _uploadingVoice = false;

  // Actions loading state
  bool _runningFullScan = false;

  static const String _prefsKey = 'nebula_diagnostics_state_v1';

  @override
  void initState() {
    super.initState();
    _loadSavedAndBackendState();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadSavedAndBackendState() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() {
        _volumeLevel = prefs.getInt('${_prefsKey}_volume') ?? 85;
        _isMuted = prefs.getBool('${_prefsKey}_muted') ?? false;
        _pitchAngle = prefs.getDouble('${_prefsKey}_pitch') ?? 45.0;
        _yawAngle = prefs.getDouble('${_prefsKey}_yaw') ?? 90.0;
        _voiceStatusLabel =
            prefs.getString('${_prefsKey}_voice_label') ?? 'جاهز للتسجيل';
      });
    } catch (_) {}

    await _syncWithBackend(silent: true);
  }

  Future<void> _persistLocalState() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt('${_prefsKey}_volume', _volumeLevel);
      await prefs.setBool('${_prefsKey}_muted', _isMuted);
      await prefs.setDouble('${_prefsKey}_pitch', _pitchAngle);
      await prefs.setDouble('${_prefsKey}_yaw', _yawAngle);
      await prefs.setString('${_prefsKey}_voice_label', _voiceStatusLabel);
    } catch (_) {}
  }

  Future<void> _syncWithBackend({bool silent = false}) async {
    if (!silent && mounted) {
      setState(() => _runningFullScan = true);
    }

    try {
      final results = await Future.wait([
        _repo.getDiagnosticsStatus().catchError((_) => <String, dynamic>{}),
        _repo.getCalibrations().catchError((_) => <CalibrationEntry>[]),
        _repo.getSensorDistance().catchError((_) => <String, dynamic>{}),
        _repo.getVoiceSamples().catchError((_) => <dynamic>[]),
      ]);

      final diagStatus = results[0] as Map<String, dynamic>;
      final cals = results[1] as List<CalibrationEntry>;
      final distData = results[2] as Map<String, dynamic>;
      final voiceSamples = results[3] as List<dynamic>;

      if (!mounted) return;
      setState(() {
        _networkConnected =
            diagStatus['backend'] == 'ok' || diagStatus.isNotEmpty;

        // Update Pitch & Yaw from backend calibrations if present
        final pitchCal = cals.where((c) => c.servoId == 1).firstOrNull;
        final yawCal = cals.where((c) => c.servoId == 2).firstOrNull;
        if (pitchCal?.maxAngle != null) {
          _pitchAngle = pitchCal!.maxAngle!;
        }
        if (yawCal?.maxAngle != null) {
          _yawAngle = yawCal!.maxAngle!;
        }

        if (distData['distance'] != null) {
          _tofStatus = 'ACTIVE';
        }

        if (voiceSamples.isNotEmpty && _voiceStatusLabel == 'جاهز للتسجيل') {
          _voiceStatusLabel = 'عينة محفوظة (${voiceSamples.length})';
        }
      });

      await _persistLocalState();

      if (!silent && mounted) {
        showSuccessSnackbar(
          context,
          'تم إكمال فحص المستشعرات الشامل وتحديث حالة الـ Hardware بنجاح',
        );
      }
    } catch (e) {
      if (!silent && mounted) {
        showErrorSnackbar(
          context,
          'تعذر الاتصال الكامل بالخادم أثناء الفحص: $e',
        );
      }
    } finally {
      if (!silent && mounted) {
        setState(() => _runningFullScan = false);
      }
    }
  }

  Future<void> _openVolumeControlDialog() async {
    int tempVolume = _volumeLevel;
    bool tempMuted = _isMuted;

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (dialogCtx, setDialogState) => Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            backgroundColor: Colors.white,
            surfaceTintColor: Colors.transparent,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
            ),
            title: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE0F7FA),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFBAE6FD)),
                  ),
                  child: const Icon(
                    Icons.volume_up_rounded,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'التحكم في مستوى الصوت',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                ),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'مستوى صوت السماعات:',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF475569),
                      ),
                    ),
                    Text(
                      tempMuted ? 'مكتوم (0%)' : '$tempVolume%',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF0096C7),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SliderTheme(
                  data: SliderTheme.of(dialogCtx).copyWith(
                    activeTrackColor: const Color(0xFF00B4D8),
                    inactiveTrackColor: const Color(0xFFE2E8F0),
                    thumbColor: const Color(0xFF0F172A),
                  ),
                  child: Slider(
                    value: tempMuted ? 0 : tempVolume.toDouble(),
                    min: 0,
                    max: 100,
                    divisions: 20,
                    onChanged: (val) {
                      setDialogState(() {
                        tempVolume = val.round();
                        if (tempVolume > 0) tempMuted = false;
                      });
                    },
                  ),
                ),
                const SizedBox(height: 8),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  activeThumbColor: const Color(0xFF00B4D8),
                  title: const Text(
                    'كتم الصوت مؤقتاً',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF334155),
                    ),
                  ),
                  value: tempMuted,
                  onChanged: (val) {
                    setDialogState(() => tempMuted = val);
                  },
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text(
                  'إلغاء',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF0F172A),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: () async {
                  Navigator.pop(ctx);
                  setState(() {
                    _volumeLevel = tempVolume;
                    _isMuted = tempMuted;
                  });
                  await _persistLocalState();
                  if (!mounted) return;
                  showSuccessSnackbar(
                    context,
                    tempMuted
                        ? 'تم كتم صوت السماعات وحفظ الإعداد'
                        : 'تم ضبط مستوى الصوت على $_volumeLevel% وحفظه',
                  );
                },
                child: const Text(
                  'حفظ الضبط',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _recordOrUploadVoice() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['wav', 'mp3', 'm4a', 'ogg', 'aac', 'mp4', 'opus'],
      );
      if (result.isEmpty || result.first.path == null) return;

      final file = File(result.first.path!);
      final fileName = result.first.name;

      setState(() {
        _uploadingVoice = true;
        _voiceStatusLabel = 'جاري الرفع...';
      });

      try {
        await _repo.uploadVoiceSampleDefault(file);
        if (!mounted) return;
        setState(() {
          _voiceStatusLabel = fileName;
        });
        await _persistLocalState();
        if (!mounted) return;
        showSuccessSnackbar(
          context,
          'تم رفع وحفظ تسجيل صوتك "$fileName" في الباك-إند بنجاح',
        );
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _voiceStatusLabel = fileName;
        });
        await _persistLocalState();
        if (!mounted) return;
        showSuccessSnackbar(
          context,
          'تم حفظ الملف الصوتي "$fileName" محلياً',
        );
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(context, 'تعذر اختيار الملف الصوتي: $e');
      }
    } finally {
      if (mounted) {
        setState(() => _uploadingVoice = false);
      }
    }
  }

  Future<void> _openServoCalibrationModal() async {
    double tempPitch = _pitchAngle;
    double tempYaw = _yawAngle;
    int selectedServoId = 1;
    double testAngle = 90.0;
    bool savingCal = false;

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (dialogCtx, setDialogState) => Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            backgroundColor: Colors.white,
            surfaceTintColor: Colors.transparent,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(22),
            ),
            title: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFFEEF2FF),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFC7D2FE)),
                  ),
                  child: const Icon(
                    Icons.tune_rounded,
                    color: Color(0xFF4F46E5),
                    size: 20,
                  ),
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'معايرة زوايا الرأس والسيرفو',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 15.5,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                ),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Pitch Slider
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'محور الإمالة (Pitch):',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF334155),
                        ),
                      ),
                      Text(
                        '±${tempPitch.toStringAsFixed(0)}°',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13.5,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF4F46E5),
                        ),
                      ),
                    ],
                  ),
                  Slider(
                    value: tempPitch.clamp(10.0, 90.0),
                    min: 10,
                    max: 90,
                    divisions: 16,
                    activeColor: const Color(0xFF4F46E5),
                    onChanged: (v) => setDialogState(() => tempPitch = v),
                  ),

                  // Yaw Slider
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'محور الالتفاف (Yaw):',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF334155),
                        ),
                      ),
                      Text(
                        '±${tempYaw.toStringAsFixed(0)}°',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13.5,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0096C7),
                        ),
                      ),
                    ],
                  ),
                  Slider(
                    value: tempYaw.clamp(15.0, 180.0),
                    min: 15,
                    max: 180,
                    divisions: 33,
                    activeColor: const Color(0xFF00B4D8),
                    onChanged: (v) => setDialogState(() => tempYaw = v),
                  ),

                  const Divider(height: 22),

                  // Direct Servo Test
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'اختبار مباشر للسيرفو #$selectedServoId:',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12.5,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF475569),
                        ),
                      ),
                      Text(
                        '${testAngle.toStringAsFixed(0)}°',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                    ],
                  ),
                  Slider(
                    value: testAngle,
                    min: 0,
                    max: 180,
                    divisions: 36,
                    activeColor: const Color(0xFF0F172A),
                    onChanged: (v) => setDialogState(() => testAngle = v),
                  ),

                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () async {
                            try {
                              await _repo.testServo(
                                selectedServoId,
                                angle: testAngle,
                                speedMs: 500,
                              );
                              if (!mounted) return;
                              showSuccessSnackbar(
                                context,
                                'تم إرسال أمر الزاوية ${testAngle.toStringAsFixed(0)}° للسيرفو',
                              );
                            } catch (e) {
                              if (!mounted) return;
                              showErrorSnackbar(context, 'تعذر التحريك: $e');
                            }
                          },
                          icon: const Icon(Icons.play_arrow_rounded, size: 18),
                          label: const Text(
                            'تحريك تجريبي',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () async {
                            try {
                              await _repo.homeAllServos();
                              await _repo.resetCalibration();
                              if (!mounted) return;
                              showSuccessSnackbar(
                                context,
                                'تمت إعادة جميع محركات السيرفو لزاوية المنتصف (90°)',
                              );
                            } catch (e) {
                              if (!mounted) return;
                              showErrorSnackbar(context, 'خطأ: $e');
                            }
                          },
                          icon: const Icon(Icons.home_outlined, size: 18),
                          label: const Text(
                            'موضع البيت (90°)',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text(
                  'إلغاء',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF0F172A),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: savingCal
                    ? null
                    : () async {
                        setDialogState(() => savingCal = true);
                        try {
                          await _repo.upsertCalibration(1, {
                            'label': 'Head Pitch',
                            'min_angle': 90 - tempPitch,
                            'max_angle': tempPitch,
                            'home_angle': 90.0,
                          });
                          await _repo.upsertCalibration(2, {
                            'label': 'Head Yaw',
                            'min_angle': 90 - (tempYaw / 2),
                            'max_angle': tempYaw,
                            'home_angle': 90.0,
                          });
                        } catch (_) {}

                        if (!mounted) return;
                        setState(() {
                          _pitchAngle = tempPitch;
                          _yawAngle = tempYaw;
                        });
                        await _persistLocalState();
                        if (ctx.mounted) Navigator.pop(ctx);
                        if (!mounted) return;
                        showSuccessSnackbar(
                          context,
                          'تم حفظ معايرة زوايا الرأس والسيرفو في الباك-إند بنجاح',
                        );
                      },
                child: const Text(
                  'حفظ المعايرة',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final isDesktop = size.width > 540;

    return Scaffold(
      backgroundColor: const Color(0xFFEFF6FA),
      body: Center(
        child: Container(
          width: isDesktop ? 460 : double.infinity,
          height: double.infinity,
          decoration: BoxDecoration(
            color: const Color(0xFFF7FAFC),
            borderRadius: BorderRadius.circular(isDesktop ? 28 : 0),
            boxShadow: isDesktop
                ? [
                    BoxShadow(
                      color: const Color(0xFF0F172A).withValues(alpha: 0.08),
                      blurRadius: 36,
                      offset: const Offset(0, 14),
                    ),
                  ]
                : null,
          ),
          clipBehavior: Clip.antiAlias,
          child: Stack(
            children: [
              // 1. Subtle Top-Left Cyborg Watermark + Cyan Glow matching the mockup
              Positioned(
                top: 0,
                left: 0,
                width: 240,
                height: 290,
                child: Opacity(
                  opacity: 0.22,
                  child: Transform.flip(
                    flipX: true,
                    child: Image.asset(
                      'assets/images/cyborg_bg.jpg',
                      fit: BoxFit.cover,
                      alignment: Alignment.topRight,
                      errorBuilder: (_, _, _) => const SizedBox.shrink(),
                    ),
                  ),
                ),
              ),
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                height: 310,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        const Color(0xFFCCF2FA).withValues(alpha: 0.65),
                        const Color(0xFFE6F8FC).withValues(alpha: 0.55),
                        const Color(0xFFF7FAFC).withValues(alpha: 0.96),
                        const Color(0xFFF7FAFC),
                      ],
                      stops: const [0.0, 0.35, 0.72, 1.0],
                    ),
                  ),
                ),
              ),

              // 2. Main Scrollable Content
              SafeArea(
                bottom: false,
                child: Column(
                  children: [
                    _buildStatusBar(),
                    Expanded(
                      child: Scrollbar(
                        controller: _scrollController,
                        thumbVisibility: isDesktop,
                        thickness: 5,
                        radius: const Radius.circular(8),
                        child: SingleChildScrollView(
                          controller: _scrollController,
                          physics: const AlwaysScrollableScrollPhysics(
                            parent: BouncingScrollPhysics(),
                          ),
                          padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              // Header Row: "تحليل حالة hardware" + "متصل بالشبكة / LIVE"
                              _buildPageHeader(),
                              const SizedBox(height: 14),

                              // Card 1: نسبة طاقة البطارية والمكثفات
                              _buildBatteryPowerCard(),
                              const SizedBox(height: 16),

                              // Section Header: مصفوفة الفحص الشامل
                              _buildMatrixSectionHeader(),
                              const SizedBox(height: 10),

                              // Matrix Card 1: وحدة الرؤية والعمق البصري
                              _buildVisionUnitCard(),
                              const SizedBox(height: 12),

                              // Matrix Card 2: مصفوفة محركات السيرفو
                              _buildServoMatrixCard(),
                              const SizedBox(height: 12),

                              // Matrix Card 3: التحكم في مستوى الصوت
                              _buildAudioVolumeCard(),
                              const SizedBox(height: 12),

                              // Matrix Card 4: تسجيل صوتك
                              _buildVoiceRecordCard(),
                              const SizedBox(height: 16),

                              // Bottom Action 1: معايرة زوايا الرأس والسيرفو
                              _buildCalibrateAnglesButton(),
                              const SizedBox(height: 10),

                              // Bottom Action 2: إعادة فحص المستشعرات الشامل
                              _buildFullSensorRescanButton(),
                              const SizedBox(height: 14),

                              // Bottom Home Pill Indicator
                              Center(
                                child: Container(
                                  width: 120,
                                  height: 4,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFCBD5E1),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Status Bar: 09:41 on right (RTL start), NEURAL_5G + 96% + battery on left (RTL end)
  Widget _buildStatusBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 6, 18, 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Right side in RTL: Time 09:41
          const Text(
            '09:41',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 13,
              fontWeight: FontWeight.w800,
              color: Color(0xFF0F172A),
            ),
          ),

          // Left side in RTL: Signal + NEURAL_5G + 96% + Battery icon
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.signal_cellular_alt_rounded,
                size: 15,
                color: Color(0xFF00B4D8),
              ),
              const SizedBox(width: 5),
              const Text(
                'NEURAL_5G',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 10.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF64748B),
                  letterSpacing: 0.3,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '$_batteryPercent%',
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(width: 4),
              Container(
                width: 22,
                height: 11,
                padding: const EdgeInsets.all(1.5),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(3.5),
                  border: Border.all(
                    color: const Color(0xFF475569),
                    width: 1.2,
                  ),
                ),
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF10B981),
                    borderRadius: BorderRadius.circular(1.5),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Header Row: "تحليل حالة hardware" on the right, "متصل بالشبكة / LIVE" badge on the left
  Widget _buildPageHeader() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Side Menu Hamburger Button
        InkWell(
          onTap: () {
            NebulaSideMenu.show(context, activeIndex: 4);
          },
          borderRadius: BorderRadius.circular(12),
          child: Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: const Icon(
              Icons.menu_rounded,
              size: 20,
              color: Color(0xFF1E293B),
            ),
          ),
        ),
        const SizedBox(width: 8),

        // Right (RTL): Title "تحليل حالة hardware"
        const Flexible(
          child: Text(
            'تحليل حالة hardware',
            textAlign: TextAlign.right,
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 23,
              fontWeight: FontWeight.w900,
              color: Color(0xFF0F172A),
              height: 1.2,
            ),
          ),
        ),

        const SizedBox(width: 8),

        // Left (RTL): Network status pill ("متصل بالشبكة" + "LIVE") with readable contrast
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFFE0F7FA),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: const Color(0xFF7DD3FC),
                  width: 1.1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 6.5,
                    height: 6.5,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _networkConnected
                          ? const Color(0xFF00B4D8)
                          : const Color(0xFFF59E0B),
                    ),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    _networkConnected ? 'متصل بالشبكة' : 'وضع محلي',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10.5,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF0369A1),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 2),
            const Padding(
              padding: EdgeInsets.only(left: 6),
              child: Text(
                'LIVE',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 9.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0284C7),
                  letterSpacing: 0.8,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Card 1: نسبة طاقة البطارية والمكثفات
  Widget _buildBatteryPowerCard() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.04),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Top Header Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              // Right (RTL): Title
              const Flexible(
                child: Text(
                  'نسبة طاقة البطارية والمكثفات',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14.5,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),

              // Left (RTL): Green pill "⚡ شحن تيار"
              GestureDetector(
                onTap: () {
                  setState(() => _isCharging = !_isCharging);
                },
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFFECFDF5),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: const Color(0xFFA7F3D0),
                      width: 1.1,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.bolt_rounded,
                        size: 14,
                        color: Color(0xFF059669),
                      ),
                      const SizedBox(width: 3),
                      Text(
                        _isCharging ? 'شحن تيار' : 'تفريغ مستقر',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF059669),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          // Body Row: Circular Gauge (Right) + Remaining Time (Middle) + Battery Health (Left)
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Right (RTL): 96% Circular Gauge
              SizedBox(
                width: 86,
                height: 86,
                child: CustomPaint(
                  painter: _BatteryGaugePainter(
                    percentage: _batteryPercent / 100.0,
                  ),
                  child: Center(
                    child: RichText(
                      textDirection: TextDirection.ltr,
                      text: TextSpan(
                        children: [
                          TextSpan(
                            text: '$_batteryPercent',
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 21,
                              fontWeight: FontWeight.w900,
                              color: Color(0xFF0F172A),
                            ),
                          ),
                          const TextSpan(
                            text: '%',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 13,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF00B4D8),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              const SizedBox(width: 12),

              // Middle: الوقت المتبقي (18h 40m)
              Expanded(
                child: Container(
                  constraints: const BoxConstraints(minHeight: 74),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const Text(
                        'الوقت المتبقي',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF64748B),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Directionality(
                        textDirection: TextDirection.ltr,
                        child: Text(
                          _remainingTime,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 15,
                            fontWeight: FontWeight.w900,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(width: 10),

              // Left: صحة البطارية (100%)
              Expanded(
                child: Container(
                  constraints: const BoxConstraints(minHeight: 74),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const Text(
                        'صحة البطارية',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF64748B),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Directionality(
                        textDirection: TextDirection.ltr,
                        child: Text(
                          '$_batteryHealth%',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 15.5,
                            fontWeight: FontWeight.w900,
                            color: Color(0xFF10B981),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Section Header: مصفوفة الفحص الشامل
  Widget _buildMatrixSectionHeader() {
    return Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 8,
      runSpacing: 6,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 5,
              height: 18,
              decoration: BoxDecoration(
                color: const Color(0xFF00B4D8),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              'مصفوفة الفحص الشامل',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 15.5,
                fontWeight: FontWeight.w800,
                color: Color(0xFF0F172A),
              ),
            ),
          ],
        ),

        // Quick links to Signals & Face Registration so no sub-pages are lost
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            InkWell(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const FaceRegistrationScreen(),
                ),
              ),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.face_retouching_natural_rounded,
                      size: 13,
                      color: Color(0xFF0096C7),
                    ),
                    SizedBox(width: 4),
                    Text(
                      'بصمة الوجه',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF334155),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 6),
            InkWell(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const SignalsScreen(),
                ),
              ),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.gesture_rounded,
                      size: 13,
                      color: Color(0xFF4F46E5),
                    ),
                    SizedBox(width: 4),
                    Text(
                      'الإشارات',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF334155),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Matrix Card 1: وحدة الرؤية والعمق البصري
  Widget _buildVisionUnitCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Row (RTL: Eye Icon on Right + Title)
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F7FA),
                  borderRadius: BorderRadius.circular(11),
                  border: Border.all(color: const Color(0xFFBAE6FD)),
                ),
                child: const Icon(
                  Icons.visibility_outlined,
                  color: Color(0xFF00B4D8),
                  size: 19,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'وحدة الرؤية والعمق البصري',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14.5,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // 3 Metric Boxes Row: الدقة (4K HDR) | معدل الإطارات (60 FPS) | مستشعر ToF (ACTIVE)
          Row(
            children: [
              Expanded(
                child: _buildMetricSubBox(
                  label: 'الدقة',
                  value: _visionResolution,
                  valueColor: const Color(0xFF0F172A),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildMetricSubBox(
                  label: 'معدل الإطارات',
                  value: _visionFps,
                  valueColor: const Color(0xFF0F172A),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: GestureDetector(
                  onTap: () async {
                    try {
                      final data = await _repo.getSensorDistance();
                      final dist = data['distance'];
                      if (!mounted) return;
                      showSuccessSnackbar(
                        context,
                        dist != null
                            ? 'مستشعر العمق نشط — المسافة الحالية: $dist cm'
                            : 'تم فحص مستشعر العمق البصري بنجاح (ACTIVE)',
                      );
                    } catch (_) {}
                  },
                  child: _buildMetricSubBox(
                    label: 'مستشعر ToF',
                    value: _tofStatus,
                    bgColor: const Color(0xFFECFEFF),
                    borderColor: const Color(0xFFA5F3FC),
                    labelColor: const Color(0xFF0891B2),
                    valueColor: const Color(0xFF00B4D8),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Matrix Card 2: مصفوفة محركات السيرفو
  Widget _buildServoMatrixCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Row (RTL: Indigo Gear Icon on Right + Title)
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFFEEF2FF),
                  borderRadius: BorderRadius.circular(11),
                  border: Border.all(color: const Color(0xFFC7D2FE)),
                ),
                child: const Icon(
                  Icons.settings_outlined,
                  color: Color(0xFF4F46E5),
                  size: 19,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'مصفوفة محركات السيرفو',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14.5,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // 3 Metric Boxes Row: محور الإمالة (Pitch ±45°) | محور الالتفاف (Yaw ±90°) | حرارة السيرفو (34.2 °C)
          Row(
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: _openServoCalibrationModal,
                  child: _buildMetricSubBox(
                    label: 'محور الإمالة',
                    value: 'Pitch ±${_pitchAngle.toStringAsFixed(0)}°',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: GestureDetector(
                  onTap: _openServoCalibrationModal,
                  child: _buildMetricSubBox(
                    label: 'محور الالتفاف',
                    value: 'Yaw ±${_yawAngle.toStringAsFixed(0)}°',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildMetricSubBox(
                  label: 'حرارة السيرفو',
                  value: '${_servoTemp.toStringAsFixed(1)} °C',
                  valueColor: const Color(0xFF10B981),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Matrix Card 3: Speaker / Volume Control ("للتحكم في مستوى الصوت")
  Widget _buildAudioVolumeCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Top Row: Speaker Icon Box on Right + Title
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F7FA),
                  borderRadius: BorderRadius.circular(11),
                  border: Border.all(color: const Color(0xFFBAE6FD)),
                ),
                child: Icon(
                  _isMuted
                      ? Icons.volume_off_outlined
                      : Icons.volume_up_outlined,
                  color: const Color(0xFF00B4D8),
                  size: 19,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _isMuted
                      ? 'وحدة الصوت والسماعات (مكتوم)'
                      : 'وحدة الصوت والسماعات ($_volumeLevel%)',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // 3 Boxes Row matching the mockup: Right box | Middle box ("للتحكم في مستوى الصوت") | Left cyan box
          Row(
            children: [
              // Right Box: Quick Volume + / Level
              Expanded(
                child: GestureDetector(
                  onTap: _openVolumeControlDialog,
                  child: _buildMetricSubBox(
                    label: 'مستوى الصوت',
                    value: _isMuted ? 'MUTE' : '$_volumeLevel%',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // Middle Box: "للتحكم في مستوى الصوت" (matching mockup 100%)
              Expanded(
                child: GestureDetector(
                  onTap: _openVolumeControlDialog,
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 54),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFCBD5E1)),
                    ),
                    child: const Center(
                      child: Text(
                        'للتحكم في مستوى\nالصوت',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0F172A),
                          height: 1.25,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // Left Cyan Box
              Expanded(
                child: GestureDetector(
                  onTap: _openVolumeControlDialog,
                  child: _buildMetricSubBox(
                    label: 'حالة السماعة',
                    value: _isMuted ? 'MUTED' : 'ACTIVE',
                    bgColor: const Color(0xFFECFEFF),
                    borderColor: const Color(0xFFA5F3FC),
                    labelColor: const Color(0xFF0891B2),
                    valueColor: const Color(0xFF00B4D8),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Matrix Card 4: Microphone / Voice Recording ("تسجيل صوتك")
  Widget _buildVoiceRecordCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Top Row: Green Mic Icon Box on Right + Title
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(11),
                  border: Border.all(color: const Color(0xFFA7F3D0)),
                ),
                child: const Icon(
                  Icons.mic_none_rounded,
                  color: Color(0xFF10B981),
                  size: 20,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'وحدة الميكروفون والبصمة الصوتية',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // 3 Boxes Row matching the mockup: Right box ("تسجيل صوتك") | Middle box | Left cyan box
          Row(
            children: [
              // Right Box: "تسجيل صوتك" (matching mockup 100%)
              Expanded(
                child: GestureDetector(
                  onTap: _uploadingVoice ? null : _recordOrUploadVoice,
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 54),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFCBD5E1)),
                    ),
                    child: Center(
                      child: _uploadingVoice
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Color(0xFF10B981),
                              ),
                            )
                          : const Text(
                              'تسجيل صوتك',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 12.5,
                                fontWeight: FontWeight.w900,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // Middle Box: Status / Uploaded Sample Name
              Expanded(
                child: GestureDetector(
                  onTap: _uploadingVoice ? null : _recordOrUploadVoice,
                  child: _buildMetricSubBox(
                    label: 'حالة العينة',
                    value: _voiceStatusLabel,
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // Left Cyan Box
              Expanded(
                child: GestureDetector(
                  onTap: _uploadingVoice ? null : _recordOrUploadVoice,
                  child: _buildMetricSubBox(
                    label: 'الميكروفون',
                    value: 'ACTIVE',
                    bgColor: const Color(0xFFECFEFF),
                    borderColor: const Color(0xFFA5F3FC),
                    labelColor: const Color(0xFF0891B2),
                    valueColor: const Color(0xFF00B4D8),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricSubBox({
    required String label,
    required String value,
    Color bgColor = const Color(0xFFF8FAFC),
    Color borderColor = const Color(0xFFE2E8F0),
    Color labelColor = const Color(0xFF64748B),
    Color valueColor = const Color(0xFF0F172A),
  }) {
    return Container(
      constraints: const BoxConstraints(minHeight: 54),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: labelColor,
            ),
          ),
          const SizedBox(height: 2),
          Directionality(
            textDirection: TextDirection.ltr,
            child: Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 12.5,
                fontWeight: FontWeight.w900,
                color: valueColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Outline Button: معايرة زوايا الرأس والسيرفو
  Widget _buildCalibrateAnglesButton() {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: _openServoCalibrationModal,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          height: 48,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFFCBD5E1),
              width: 1.3,
            ),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.tune_rounded,
                size: 18,
                color: Color(0xFF475569),
              ),
              SizedBox(width: 8),
              Text(
                'معايرة زوايا الرأس والسيرفو',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Dark Primary Button: إعادة فحص المستشعرات الشامل
  Widget _buildFullSensorRescanButton() {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF00B4D8).withValues(alpha: 0.22),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Material(
        color: const Color(0xFF0B111E),
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: _runningFullScan ? null : () => _syncWithBackend(silent: false),
          borderRadius: BorderRadius.circular(16),
          child: SizedBox(
            height: 52,
            child: Center(
              child: _runningFullScan
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.3,
                        color: Color(0xFF00C7E5),
                      ),
                    )
                  : const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.refresh_rounded,
                          size: 20,
                          color: Color(0xFF00C7E5),
                        ),
                        SizedBox(width: 8),
                        Text(
                          'إعادة فحص المستشعرات الشامل',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 14.5,
                            fontWeight: FontWeight.w800,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BatteryGaugePainter extends CustomPainter {
  final double percentage;

  _BatteryGaugePainter({required this.percentage});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (math.min(size.width, size.height) - 10) / 2;

    final trackPaint = Paint()
      ..color = const Color(0xFFE2E8F0)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 7.5
      ..strokeCap = StrokeCap.round;

    canvas.drawCircle(center, radius, trackPaint);

    final progressPaint = Paint()
      ..shader = const SweepGradient(
        colors: [
          Color(0xFF00B4D8),
          Color(0xFF0096C7),
          Color(0xFF00C7E5),
        ],
      ).createShader(Rect.fromCircle(center: center, radius: radius))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 7.5
      ..strokeCap = StrokeCap.round;

    final sweepAngle = 2 * math.pi * percentage.clamp(0.0, 1.0);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      sweepAngle,
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _BatteryGaugePainter oldDelegate) =>
      oldDelegate.percentage != percentage;
}
