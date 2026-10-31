import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'signals_screen.dart';
import 'face_registration_screen.dart';

class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen>
    with SingleTickerProviderStateMixin {
  final _repo = NebulaRepository.instance;
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.bgGradient),
        child: SafeArea(
          child: Column(
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: [
                    const Expanded(
                      child: Text('التشخيص والتحكم',
                          style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.person_add_outlined,
                          color: AppColors.teal),
                      tooltip: 'تسجيل وجه',
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) =>
                                const FaceRegistrationScreen()),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.gesture, color: AppColors.purple),
                      tooltip: 'الإشارات',
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => const SignalsScreen()),
                      ),
                    ),
                  ],
                ),
              ),
              // Tabs
              Container(
                margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.cardBorder),
                ),
                child: TabBar(
                  controller: _tabCtrl,
                  indicator: BoxDecoration(
                    gradient: AppColors.tealGradient,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  indicatorSize: TabBarIndicatorSize.tab,
                  labelColor: AppColors.bg,
                  unselectedLabelColor: AppColors.textSecondary,
                  labelStyle: const TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      fontSize: 12),
                  tabs: const [
                    Tab(text: 'السيرفو'),
                    Tab(text: 'المحركات / LED'),
                    Tab(text: 'المعايرة'),
                  ],
                ),
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabCtrl,
                  children: [
                    _ServoTab(repo: _repo),
                    _MotorLedTab(repo: _repo),
                    _CalibrationTab(repo: _repo),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─── Servo Tab ───────────────────────────────────────────────────────────────

class _ServoTab extends StatefulWidget {
  final NebulaRepository repo;
  const _ServoTab({required this.repo});

  @override
  State<_ServoTab> createState() => _ServoTabState();
}

class _ServoTabState extends State<_ServoTab> {
  int _servoId = 1;
  double _angle = 90.0;
  int _speedMs = 500;
  bool _testing = false;
  bool _homing = false;
  double? _distance;
  bool _gettingDist = false;

  Future<void> _test() async {
    setState(() => _testing = true);
    try {
      await widget.repo
          .testServo(_servoId, angle: _angle, speedMs: _speedMs);
      if (mounted) showSuccessSnackbar(context, 'تم تحريك السيرفو');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _homeAll() async {
    setState(() => _homing = true);
    try {
      await widget.repo.homeAllServos();
      if (mounted) showSuccessSnackbar(context, 'تم إعادة الكل لموضع البيت');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _homing = false);
    }
  }

  Future<void> _getDistance() async {
    setState(() => _gettingDist = true);
    try {
      final data = await widget.repo.getSensorDistance();
      setState(() => _distance = (data['distance'] as num?)?.toDouble());
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _gettingDist = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          NebulaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: 'اختبار السيرفو'),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('معرّف السيرفو: $_servoId',
                              style: const TextStyle(
                                  color: AppColors.textSecondary,
                                  fontFamily: 'Cairo',
                                  fontSize: 13)),
                          Slider(
                            value: _servoId.toDouble(),
                            min: 1,
                            max: 12,
                            divisions: 11,
                            activeColor: AppColors.teal,
                            inactiveColor: AppColors.cardBorder,
                            label: _servoId.toString(),
                            onChanged: (v) =>
                                setState(() => _servoId = v.round()),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                Text('الزاوية: ${_angle.toStringAsFixed(0)}°',
                    style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontFamily: 'Cairo',
                        fontSize: 13)),
                Slider(
                  value: _angle,
                  min: 0,
                  max: 180,
                  divisions: 180,
                  activeColor: AppColors.purple,
                  inactiveColor: AppColors.cardBorder,
                  label: '${_angle.toStringAsFixed(0)}°',
                  onChanged: (v) => setState(() => _angle = v),
                ),
                Text('السرعة: $_speedMs ms',
                    style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontFamily: 'Cairo',
                        fontSize: 13)),
                Slider(
                  value: _speedMs.toDouble(),
                  min: 50,
                  max: 2000,
                  divisions: 39,
                  activeColor: AppColors.warning,
                  inactiveColor: AppColors.cardBorder,
                  label: '${_speedMs}ms',
                  onChanged: (v) =>
                      setState(() => _speedMs = v.round()),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: NebulaPrimaryButton(
                        label: 'اختبار',
                        icon: Icons.play_arrow_outlined,
                        onTap: _test,
                        loading: _testing,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: GestureDetector(
                        onTap: _homing ? null : _homeAll,
                        child: Container(
                          height: 54,
                          decoration: BoxDecoration(
                            color: AppColors.purple.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                                color: AppColors.purple
                                    .withValues(alpha: 0.4)),
                          ),
                          child: Center(
                            child: _homing
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: AppColors.purple))
                                : const Text('موضع البيت',
                                    style: TextStyle(
                                        color: AppColors.purple,
                                        fontFamily: 'Cairo',
                                        fontWeight: FontWeight.w700)),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Distance sensor
          NebulaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: 'مستشعر المسافة HC-SR04'),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: _distance != null
                          ? Text(
                              '${_distance!.toStringAsFixed(1)} cm',
                              style: const TextStyle(
                                  color: AppColors.teal,
                                  fontSize: 28,
                                  fontWeight: FontWeight.w800,
                                  fontFamily: 'Cairo'),
                            )
                          : const Text('اضغط لقراءة المسافة',
                              style: TextStyle(
                                  color: AppColors.textMuted,
                                  fontFamily: 'Cairo')),
                    ),
                    NebulaPrimaryButton(
                      label: 'قراءة',
                      icon: Icons.radar,
                      onTap: _getDistance,
                      loading: _gettingDist,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Motor / LED Tab ─────────────────────────────────────────────────────────

class _MotorLedTab extends StatefulWidget {
  final NebulaRepository repo;
  const _MotorLedTab({required this.repo});

  @override
  State<_MotorLedTab> createState() => _MotorLedTabState();
}

class _MotorLedTabState extends State<_MotorLedTab> {
  int _left = 128, _right = 128, _durationMs = 1000;
  bool _testingMotor = false;
  String _ledState = 'on';
  bool _settingLed = false;
  bool _stopping = false;

  final _ledStates = ['on', 'off', 'blink_slow', 'blink_fast', 'blink_double'];

  Future<void> _testMotors() async {
    setState(() => _testingMotor = true);
    try {
      await widget.repo.testMotors(
          left: _left, right: _right, durationMs: _durationMs);
      if (mounted) showSuccessSnackbar(context, 'تم تشغيل المحركات');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _testingMotor = false);
    }
  }

  Future<void> _setLed() async {
    setState(() => _settingLed = true);
    try {
      await widget.repo.setLed(_ledState);
      if (mounted) showSuccessSnackbar(context, 'تم ضبط LED');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _settingLed = false);
    }
  }

  Future<void> _emergencyStop() async {
    setState(() => _stopping = true);
    try {
      await widget.repo.emergencyStop();
      if (mounted) showSuccessSnackbar(context, '🚨 تم الإيقاف الطارئ');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _stopping = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Motors
          NebulaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: 'اختبار المحركات'),
                const SizedBox(height: 16),
                Text('الأيسر: $_left',
                    style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontFamily: 'Cairo',
                        fontSize: 13)),
                Slider(
                  value: _left.toDouble(),
                  min: 0,
                  max: 255,
                  divisions: 255,
                  activeColor: AppColors.teal,
                  inactiveColor: AppColors.cardBorder,
                  label: _left.toString(),
                  onChanged: (v) => setState(() => _left = v.round()),
                ),
                Text('الأيمن: $_right',
                    style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontFamily: 'Cairo',
                        fontSize: 13)),
                Slider(
                  value: _right.toDouble(),
                  min: 0,
                  max: 255,
                  divisions: 255,
                  activeColor: AppColors.teal,
                  inactiveColor: AppColors.cardBorder,
                  label: _right.toString(),
                  onChanged: (v) => setState(() => _right = v.round()),
                ),
                Text('المدة: $_durationMs ms',
                    style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontFamily: 'Cairo',
                        fontSize: 13)),
                Slider(
                  value: _durationMs.toDouble(),
                  min: 100,
                  max: 5000,
                  divisions: 49,
                  activeColor: AppColors.warning,
                  inactiveColor: AppColors.cardBorder,
                  label: '${_durationMs}ms',
                  onChanged: (v) =>
                      setState(() => _durationMs = v.round()),
                ),
                const SizedBox(height: 12),
                NebulaPrimaryButton(
                  label: 'تشغيل المحركات',
                  icon: Icons.settings_outlined,
                  onTap: _testMotors,
                  loading: _testingMotor,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // LED
          NebulaCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: 'التحكم بـ LED'),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: _ledStates.map((s) {
                    final selected = s == _ledState;
                    return GestureDetector(
                      onTap: () => setState(() => _ledState = s),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: selected
                              ? AppColors.teal.withValues(alpha: 0.2)
                              : AppColors.surface,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: selected
                                ? AppColors.teal
                                : AppColors.cardBorder,
                            width: selected ? 1.5 : 1,
                          ),
                        ),
                        child: Text(s,
                            style: TextStyle(
                                color: selected
                                    ? AppColors.teal
                                    : AppColors.textSecondary,
                                fontFamily: 'Cairo',
                                fontSize: 12)),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 14),
                NebulaPrimaryButton(
                  label: 'تطبيق',
                  icon: Icons.lightbulb_outline,
                  onTap: _setLed,
                  loading: _settingLed,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Emergency stop
          NebulaDangerButton(
            label: '🚨 إيقاف طارئ',
            icon: Icons.stop_circle_outlined,
            onTap: _stopping ? null : _emergencyStop,
          ),
        ],
      ),
    );
  }
}

// ─── Calibration Tab ─────────────────────────────────────────────────────────

class _CalibrationTab extends StatefulWidget {
  final NebulaRepository repo;
  const _CalibrationTab({required this.repo});

  @override
  State<_CalibrationTab> createState() => _CalibrationTabState();
}

class _CalibrationTabState extends State<_CalibrationTab> {
  List<CalibrationEntry> _entries = [];
  bool _loading = true;
  bool _resetting = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _entries = await widget.repo.getCalibrations();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في التحميل: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _reset() async {
    setState(() => _resetting = true);
    try {
      await widget.repo.resetCalibration();
      if (mounted) showSuccessSnackbar(context, 'تم الإعادة لموضع البيت');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ: $e');
    } finally {
      if (mounted) setState(() => _resetting = false);
    }
  }

  void _editEntry(CalibrationEntry entry) {
    final labelCtrl =
        TextEditingController(text: entry.label ?? '');
    double minAngle = entry.minAngle ?? 0;
    double maxAngle = entry.maxAngle ?? 180;
    double homeAngle = entry.homeAngle ?? 90;

    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, ss) => AlertDialog(
          backgroundColor: AppColors.card,
          title: Text('سيرفو #${entry.servoId}',
              style: const TextStyle(
                  fontFamily: 'Cairo', color: AppColors.textPrimary)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: labelCtrl,
                style: const TextStyle(
                    color: AppColors.textPrimary, fontFamily: 'Cairo'),
                decoration: const InputDecoration(
                    labelText: 'التسمية',
                    labelStyle:
                        TextStyle(color: AppColors.textSecondary)),
              ),
              const SizedBox(height: 10),
              Text(
                  'الحد الأدنى: ${minAngle.toStringAsFixed(0)}°',
                  style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontFamily: 'Cairo',
                      fontSize: 12)),
              Slider(
                  value: minAngle,
                  min: 0,
                  max: 180,
                  activeColor: AppColors.teal,
                  inactiveColor: AppColors.cardBorder,
                  onChanged: (v) => ss(() => minAngle = v)),
              Text('الحد الأقصى: ${maxAngle.toStringAsFixed(0)}°',
                  style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontFamily: 'Cairo',
                      fontSize: 12)),
              Slider(
                  value: maxAngle,
                  min: 0,
                  max: 180,
                  activeColor: AppColors.purple,
                  inactiveColor: AppColors.cardBorder,
                  onChanged: (v) => ss(() => maxAngle = v)),
              Text(
                  'زاوية البيت: ${homeAngle.toStringAsFixed(0)}°',
                  style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontFamily: 'Cairo',
                      fontSize: 12)),
              Slider(
                  value: homeAngle,
                  min: 0,
                  max: 180,
                  activeColor: AppColors.warning,
                  inactiveColor: AppColors.cardBorder,
                  onChanged: (v) => ss(() => homeAngle = v)),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('إلغاء')),
            TextButton(
              onPressed: () async {
                Navigator.pop(ctx);
                try {
                  await widget.repo.upsertCalibration(entry.servoId, {
                    'label': labelCtrl.text.trim().isEmpty
                        ? null
                        : labelCtrl.text.trim(),
                    'min_angle': minAngle,
                    'max_angle': maxAngle,
                    'home_angle': homeAngle,
                  });
                  if (mounted) {
                    showSuccessSnackbar(context, 'تم الحفظ');
                  }
                  _load();
                } catch (e) {
                  if (mounted) {
                    showErrorSnackbar(context, 'خطأ: $e');
                  }
                }
              },
              child: const Text('حفظ',
                  style: TextStyle(color: AppColors.teal)),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return _loading
        ? const Center(
            child: CircularProgressIndicator(color: AppColors.teal))
        : SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                if (_entries.isEmpty)
                  const NebulaCard(
                    child: Center(
                      child: Text('لا توجد معايرات',
                          style: TextStyle(
                              color: AppColors.textMuted,
                              fontFamily: 'Cairo')),
                    ),
                  )
                else
                  ...(_entries.map((e) => Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: NebulaCard(
                          child: Row(
                            children: [
                              Container(
                                width: 40,
                                height: 40,
                                decoration: BoxDecoration(
                                  color: AppColors.teal
                                      .withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(8),
                                  border: Border.all(
                                      color: AppColors.teal
                                          .withValues(alpha: 0.3)),
                                ),
                                child: Center(
                                  child: Text('${e.servoId}',
                                      style: const TextStyle(
                                          color: AppColors.teal,
                                          fontFamily: 'Cairo',
                                          fontWeight: FontWeight.w800,
                                          fontSize: 14)),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                        e.label ??
                                            'سيرفو #${e.servoId}',
                                        style: const TextStyle(
                                            color: AppColors.textPrimary,
                                            fontFamily: 'Cairo',
                                            fontWeight:
                                                FontWeight.w600)),
                                    Text(
                                        'من ${e.minAngle?.toStringAsFixed(0) ?? '?'}° '
                                        'إلى ${e.maxAngle?.toStringAsFixed(0) ?? '?'}° '
                                        '(بيت: ${e.homeAngle?.toStringAsFixed(0) ?? '?'}°)',
                                        style: const TextStyle(
                                            color:
                                                AppColors.textSecondary,
                                            fontFamily: 'Cairo',
                                            fontSize: 12)),
                                  ],
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.edit_outlined,
                                    color: AppColors.teal, size: 18),
                                onPressed: () => _editEntry(e),
                              ),
                            ],
                          ),
                        ),
                      ))),
                const SizedBox(height: 8),
                NebulaDangerButton(
                  label: 'إعادة الكل لموضع البيت',
                  icon: Icons.home_outlined,
                  onTap: _resetting ? null : _reset,
                ),
              ],
            ),
          );
  }
}
