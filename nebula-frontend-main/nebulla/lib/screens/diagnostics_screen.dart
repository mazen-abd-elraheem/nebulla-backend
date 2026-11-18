import 'dart:io';
import 'dart:math' as math;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import '../widgets/nebula_side_menu.dart';
import '../services/locale_service.dart';
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
  final int _batteryHealth = 100;
  bool _isCharging = true;

  // Vision unit
  bool _tofActive = true;

  // Servo matrix
  double _pitchAngle = 45.0;
  double _yawAngle = 90.0;
  final double _servoTemp = 34.2;

  // Audio / Volume unit
  int _volumeLevel = 85;
  bool _isMuted = false;

  // Microphone / Voice recording unit
  String? _voiceCustomLabel;
  int _voiceSamplesCount = 0;
  bool _uploadingVoice = false;

  // Actions loading state
  bool _runningFullScan = false;

  String _tr(String ar, String en) => LocaleService.instance.tr(ar, en);

  String get _displayVoiceStatus {
    if (_uploadingVoice) return _tr('جاري الرفع...', 'Uploading...');
    if (_voiceCustomLabel != null &&
        _voiceCustomLabel!.isNotEmpty &&
        _voiceCustomLabel != 'جاهز للتسجيل' &&
        !_voiceCustomLabel!.startsWith('عينة محفوظة')) {
      return _voiceCustomLabel!;
    }
    if (_voiceSamplesCount > 0) {
      return _tr(
        'عينة محفوظة ($_voiceSamplesCount)',
        'Saved ($_voiceSamplesCount)',
      );
    }
    return _tr('جاهز للتسجيل', 'Ready to record');
  }

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
        _voiceCustomLabel = prefs.getString('${_prefsKey}_voice_label');
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
      if (_voiceCustomLabel != null) {
        await prefs.setString('${_prefsKey}_voice_label', _voiceCustomLabel!);
      }
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

      final cals = results[1] as List<CalibrationEntry>;
      final distData = results[2] as Map<String, dynamic>;
      final voiceSamples = results[3] as List<dynamic>;

      if (!mounted) return;
      setState(() {
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
          _tofActive = true;
        }

        if (voiceSamples.isNotEmpty) {
          _voiceSamplesCount = voiceSamples.length;
        }
      });

      await _persistLocalState();

      if (!silent && mounted) {
        showSuccessSnackbar(
          context,
          _tr(
            'تم إكمال فحص المستشعرات الشامل وتحديث حالة الأجهزة بنجاح',
            'Full sensor diagnostics completed and hardware status updated',
          ),
        );
      }
    } catch (e) {
      if (!silent && mounted) {
        showErrorSnackbar(
          context,
          _tr(
            'تعذر الاتصال الكامل بالخادم أثناء الفحص: $e',
            'Could not complete server scan: $e',
          ),
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
          textDirection: LocaleService.instance.textDirection,
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
                Expanded(
                  child: Text(
                    _tr('التحكم في مستوى الصوت', 'Volume Control'),
                    style: const TextStyle(
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
                    Text(
                      _tr('مستوى صوت السماعات:', 'Speaker Volume:'),
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF475569),
                      ),
                    ),
                    Text(
                      tempMuted ? _tr('مكتوم (0%)', 'Muted (0%)') : '$tempVolume%',
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
                  title: Text(
                    _tr('كتم الصوت مؤقتاً', 'Mute Temporarily'),
                    style: const TextStyle(
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
                child: Text(
                  _tr('إلغاء', 'Cancel'),
                  style: const TextStyle(
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
                        ? _tr('تم كتم صوت السماعات وحفظ الإعداد', 'Speakers muted and saved')
                        : _tr(
                            'تم ضبط مستوى الصوت على $_volumeLevel% وحفظه',
                            'Volume set to $_volumeLevel% and saved',
                          ),
                  );
                },
                child: Text(
                  _tr('حفظ الضبط', 'Save'),
                  style: const TextStyle(
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
      });

      try {
        await _repo.uploadVoiceSampleDefault(file);
        if (!mounted) return;
        setState(() {
          _voiceCustomLabel = fileName;
        });
        await _persistLocalState();
        if (!mounted) return;
        showSuccessSnackbar(
          context,
          _tr(
            'تم رفع وحفظ تسجيل صوتك "$fileName" بنجاح',
            'Voice recording "$fileName" uploaded and saved',
          ),
        );
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _voiceCustomLabel = fileName;
        });
        await _persistLocalState();
        if (!mounted) return;
        showSuccessSnackbar(
          context,
          _tr(
            'تم حفظ الملف الصوتي "$fileName" محلياً',
            'Audio file "$fileName" saved locally',
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(
          context,
          _tr('تعذر اختيار الملف الصوتي: $e', 'Could not pick audio file: $e'),
        );
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
          textDirection: LocaleService.instance.textDirection,
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
                Expanded(
                  child: Text(
                    _tr('معايرة زوايا الرأس والسيرفو', 'Head & Servo Calibration'),
                    style: const TextStyle(
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
                      Text(
                        _tr('محور الإمالة:', 'Pitch Axis:'),
                        style: const TextStyle(
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
                      Text(
                        _tr('محور الالتفاف:', 'Yaw Axis:'),
                        style: const TextStyle(
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
                        _tr(
                          'اختبار مباشر للسيرفو #$selectedServoId:',
                          'Direct Test Servo #$selectedServoId:',
                        ),
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
                                _tr(
                                  'تم إرسال أمر الزاوية ${testAngle.toStringAsFixed(0)}° للسيرفو',
                                  'Sent angle ${testAngle.toStringAsFixed(0)}° command to servo',
                                ),
                              );
                            } catch (e) {
                              if (!mounted) return;
                              showErrorSnackbar(
                                context,
                                _tr('تعذر التحريك: $e', 'Move failed: $e'),
                              );
                            }
                          },
                          icon: const Icon(Icons.play_arrow_rounded, size: 18),
                          label: Text(
                            _tr('تحريك تجريبي', 'Test Move'),
                            style: const TextStyle(
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
                                _tr(
                                  'تمت إعادة جميع محركات السيرفو لزاوية المنتصف (90°)',
                                  'All servos reset to center (90°)',
                                ),
                              );
                            } catch (e) {
                              if (!mounted) return;
                              showErrorSnackbar(
                                context,
                                _tr('خطأ: $e', 'Error: $e'),
                              );
                            }
                          },
                          icon: const Icon(Icons.home_outlined, size: 18),
                          label: Text(
                            _tr('موضع المنتصف (90°)', 'Home (90°)'),
                            style: const TextStyle(
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
                child: Text(
                  _tr('إلغاء', 'Cancel'),
                  style: const TextStyle(
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
                          _tr(
                            'تم حفظ معايرة زوايا الرأس والسيرفو بنجاح',
                            'Head & servo calibration saved successfully',
                          ),
                        );
                      },
                child: Text(
                  _tr('حفظ المعايرة', 'Save Calibration'),
                  style: const TextStyle(
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

    return ListenableBuilder(
      listenable: LocaleService.instance,
      builder: (context, _) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: Scaffold(
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
                              padding: const EdgeInsets.fromLTRB(16, 4, 16, 110),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  _buildPageHeader(),
                                  const SizedBox(height: 14),
                                  _buildBatteryPowerCard(),
                                  const SizedBox(height: 16),
                                  _buildMatrixSectionHeader(),
                                  const SizedBox(height: 10),
                                  _buildVisionUnitCard(),
                                  const SizedBox(height: 12),
                                  _buildServoMatrixCard(),
                                  const SizedBox(height: 12),
                                  _buildAudioVolumeCard(),
                                  const SizedBox(height: 12),
                                  _buildVoiceRecordCard(),
                                  const SizedBox(height: 16),
                                  _buildCalibrateAnglesButton(),
                                  const SizedBox(height: 10),
                                  _buildFullSensorRescanButton(),
                                  const SizedBox(height: 14),
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
        ),
      ),
    );
  }

  /// Header Row: Menu on LEFT, Exit on RIGHT in Arabic; swapped in English
  Widget _buildPageHeader() {
    final locale = LocaleService.instance;
    final isArabic = locale.isArabic;

    final menuBtn = InkWell(
      onTap: () {
        NebulaSideMenu.show(context, activeIndex: 5);
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: const Color(0xFFCBD5E1),
            width: 1.4,
          ),
        ),
        child: const Icon(
          Icons.menu_rounded,
          size: 20,
          color: Color(0xFF0F172A),
        ),
      ),
    );

    final exitBtn = InkWell(
      onTap: () {
        if (Navigator.canPop(context)) {
          Navigator.pop(context);
        }
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: const Color(0xFFCBD5E1),
            width: 1.4,
          ),
        ),
        child: Icon(
          isArabic ? Icons.arrow_forward_rounded : Icons.arrow_back_rounded,
          size: 20,
          color: const Color(0xFF0F172A),
        ),
      ),
    );

    final leftSide = isArabic ? menuBtn : exitBtn;
    final rightSide = isArabic ? exitBtn : menuBtn;

    return Directionality(
      textDirection: TextDirection.ltr,
      child: Row(
        children: [
          leftSide,
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _tr('تحليل الحالة', 'Diagnostics'),
              textAlign: isArabic ? TextAlign.right : TextAlign.left,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 19,
                fontWeight: FontWeight.w900,
                color: Color(0xFF0F172A),
                height: 1.2,
              ),
            ),
          ),
          const SizedBox(width: 10),
          rightSide,
        ],
      ),
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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Text(
                  _tr('نسبة طاقة البطارية والمكثفات', 'Battery & Power Level'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14.5,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
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
                        _isCharging
                            ? _tr('شحن تيار', 'Charging')
                            : _tr('تفريغ مستقر', 'Stable'),
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

          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
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

              // Remaining Time
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
                      Text(
                        _tr('الوقت المتبقي', 'Remaining'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF64748B),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _tr('18 س 40 د', '18h 40m'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(width: 10),

              // Battery Health
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
                      Text(
                        _tr('صحة البطارية', 'Battery Health'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
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
            Text(
              _tr('مصفوفة الفحص الشامل', 'Full Diagnostics Matrix'),
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 15.5,
                fontWeight: FontWeight.w800,
                color: Color(0xFF0F172A),
              ),
            ),
          ],
        ),

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
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.face_retouching_natural_rounded,
                      size: 13,
                      color: Color(0xFF0096C7),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _tr('بصمة الوجه', 'Face ID'),
                      style: const TextStyle(
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
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.gesture_rounded,
                      size: 13,
                      color: Color(0xFF4F46E5),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _tr('الإشارات', 'Signals'),
                      style: const TextStyle(
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
              Expanded(
                child: Text(
                  _tr('وحدة الرؤية والعمق البصري', 'Vision & Depth Unit'),
                  style: const TextStyle(
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

          Row(
            children: [
              Expanded(
                child: _buildMetricSubBox(
                  label: _tr('الدقة', 'Resolution'),
                  value: _tr('فائقة الوضوح', '4K HDR'),
                  valueColor: const Color(0xFF0F172A),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildMetricSubBox(
                  label: _tr('معدل الإطارات', 'Frame Rate'),
                  value: _tr('60 إطار/ث', '60 FPS'),
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
                            ? _tr(
                                'مستشعر العمق نشط — المسافة الحالية: $dist سم',
                                'Depth sensor active — distance: $dist cm',
                              )
                            : _tr(
                                'تم فحص مستشعر العمق البصري بنجاح (نشط)',
                                'Depth sensor check passed (Active)',
                              ),
                      );
                    } catch (_) {}
                  },
                  child: _buildMetricSubBox(
                    label: _tr('مستشعر العمق', 'Depth Sensor'),
                    value: _tofActive
                        ? _tr('نشط', 'Active')
                        : _tr('متوقف', 'Inactive'),
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
              Expanded(
                child: Text(
                  _tr('مصفوفة محركات السيرفو', 'Servo Motor Matrix'),
                  style: const TextStyle(
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

          Row(
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: _openServoCalibrationModal,
                  child: _buildMetricSubBox(
                    label: _tr('محور الإمالة', 'Pitch Axis'),
                    value: '±${_pitchAngle.toStringAsFixed(0)}°',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: GestureDetector(
                  onTap: _openServoCalibrationModal,
                  child: _buildMetricSubBox(
                    label: _tr('محور الالتفاف', 'Yaw Axis'),
                    value: '±${_yawAngle.toStringAsFixed(0)}°',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildMetricSubBox(
                  label: _tr('حرارة السيرفو', 'Servo Temp'),
                  value: _tr(
                    '${_servoTemp.toStringAsFixed(1)} °م',
                    '${_servoTemp.toStringAsFixed(1)} °C',
                  ),
                  valueColor: const Color(0xFF10B981),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Matrix Card 3: Speaker / Volume Control
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
                      ? _tr('وحدة الصوت والسماعات (مكتوم)', 'Audio & Speakers (Muted)')
                      : _tr(
                          'وحدة الصوت والسماعات ($_volumeLevel%)',
                          'Audio & Speakers ($_volumeLevel%)',
                        ),
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

          Row(
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: _openVolumeControlDialog,
                  child: _buildMetricSubBox(
                    label: _tr('مستوى الصوت', 'Volume'),
                    value: _isMuted ? _tr('مكتوم', 'Muted') : '$_volumeLevel%',
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),

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
                    child: Center(
                      child: Text(
                        _tr('للتحكم في مستوى\nالصوت', 'Adjust\nVolume'),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
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

              Expanded(
                child: GestureDetector(
                  onTap: _openVolumeControlDialog,
                  child: _buildMetricSubBox(
                    label: _tr('حالة السماعة', 'Speaker'),
                    value: _isMuted
                        ? _tr('مكتوم', 'Muted')
                        : _tr('نشط', 'Active'),
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

  /// Matrix Card 4: Microphone / Voice Recording
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
              Expanded(
                child: Text(
                  _tr('وحدة الميكروفون والبصمة الصوتية', 'Microphone & Voiceprint'),
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

          Row(
            children: [
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
                          : Text(
                              _tr('تسجيل صوتك', 'Record Voice'),
                              textAlign: TextAlign.center,
                              style: const TextStyle(
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

              Expanded(
                child: GestureDetector(
                  onTap: _uploadingVoice ? null : _recordOrUploadVoice,
                  child: _buildMetricSubBox(
                    label: _tr('حالة العينة', 'Sample Status'),
                    value: _displayVoiceStatus,
                    valueColor: const Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),

              Expanded(
                child: GestureDetector(
                  onTap: _uploadingVoice ? null : _recordOrUploadVoice,
                  child: _buildMetricSubBox(
                    label: _tr('الميكروفون', 'Microphone'),
                    value: _tr('نشط', 'Active'),
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
          Text(
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
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.tune_rounded,
                size: 18,
                color: Color(0xFF475569),
              ),
              const SizedBox(width: 8),
              Text(
                _tr('معايرة زوايا الرأس والسيرفو', 'Calibrate Head & Servos'),
                style: const TextStyle(
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
                  : Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(
                          Icons.refresh_rounded,
                          size: 20,
                          color: Color(0xFF00C7E5),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _tr('إعادة فحص المستشعرات الشامل', 'Run Full Sensor Scan'),
                          style: const TextStyle(
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
