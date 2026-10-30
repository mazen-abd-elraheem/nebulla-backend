import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _repo = NebulaRepository.instance;

  DeviceStatus? _status;
  List<Personality> _personalities = [];
  Personality? _activePersonality;
  bool _loading = true;
  bool _stoppingEmergency = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        _repo.getDeviceStatus(),
        _repo.getPersonalities(),
      ]);
      final status = results[0] as DeviceStatus;
      final personalities = results[1] as List<Personality>;
      setState(() {
        _status = status;
        _personalities = personalities;
        _activePersonality =
            personalities.where((p) => p.isActive).firstOrNull;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
      if (mounted) showErrorSnackbar(context, 'خطأ في تحميل البيانات: $e');
    }
  }

  Future<void> _emergencyStop() async {
    setState(() => _stoppingEmergency = true);
    try {
      await _repo.emergencyStop();
      if (mounted) showSuccessSnackbar(context, '🚨 تم إيقاف الطوارئ');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الإيقاف: $e');
    } finally {
      if (mounted) setState(() => _stoppingEmergency = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.bgGradient),
        child: SafeArea(
          child: RefreshIndicator(
            color: AppColors.teal,
            backgroundColor: AppColors.surface,
            onRefresh: _load,
            child: CustomScrollView(
              slivers: [
                SliverAppBar(
                  backgroundColor: Colors.transparent,
                  floating: true,
                  title: Row(
                    children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                              color: AppColors.teal.withValues(alpha: 0.5)),
                          gradient: LinearGradient(colors: [
                            AppColors.teal.withValues(alpha: 0.2),
                            AppColors.purple.withValues(alpha: 0.2),
                          ]),
                        ),
                        child: Icon(Icons.smart_toy_outlined,
                            color: AppColors.teal, size: 18),
                      ),
                      const SizedBox(width: 10),
                      const Text('لوحة التحكم',
                          style: TextStyle(
                              fontFamily: 'Cairo',
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary)),
                    ],
                  ),
                  actions: [
                    IconButton(
                      icon: const Icon(Icons.refresh, color: AppColors.teal),
                      onPressed: _load,
                    ),
                  ],
                ),
                if (_loading)
                  const SliverFillRemaining(
                      child: Center(
                          child: CircularProgressIndicator(
                              color: AppColors.teal)))
                else
                  SliverPadding(
                    padding: const EdgeInsets.all(16),
                    sliver: SliverList(
                      delegate: SliverChildListDelegate([
                        // Connection status
                        _ConnectionCard(status: _status),
                        const SizedBox(height: 16),
                        // Active personality
                        _ActivePersonalityCard(
                            personality: _activePersonality),
                        const SizedBox(height: 16),
                        // System overview
                        _SystemOverviewCard(
                            personalities: _personalities),
                        const SizedBox(height: 24),
                        // Emergency stop
                        NebulaDangerButton(
                          label: '🚨 إيقاف طارئ فوري',
                          icon: Icons.stop_circle_outlined,
                          onTap:
                              _stoppingEmergency ? null : _emergencyStop,
                        ),
                        const SizedBox(height: 32),
                      ]),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectionCard extends StatelessWidget {
  final DeviceStatus? status;
  const _ConnectionCard({this.status});

  @override
  Widget build(BuildContext context) {
    return NebulaCard(
      glowing: status?.esp32Connected == true,
      borderColor: status?.esp32Connected == true
          ? AppColors.success
          : AppColors.cardBorder,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'حالة الاتصال'),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _ChannelStatus(
                  label: 'الهاتف',
                  icon: Icons.phone_android,
                  connected: status?.phoneConnected ?? false),
              _ChannelStatus(
                  label: 'سطح المكتب',
                  icon: Icons.desktop_windows_outlined,
                  connected: status?.deskConnected ?? false),
              _ChannelStatus(
                  label: 'ESP32',
                  icon: Icons.memory_outlined,
                  connected: status?.esp32Connected ?? false),
            ],
          ),
        ],
      ),
    );
  }
}

class _ChannelStatus extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool connected;

  const _ChannelStatus(
      {required this.label,
      required this.icon,
      required this.connected});

  @override
  Widget build(BuildContext context) {
    final color = connected ? AppColors.success : AppColors.textMuted;
    return Column(
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.1),
            border: Border.all(color: color.withValues(alpha: 0.5)),
            boxShadow: connected
                ? [
                    BoxShadow(
                        color: color.withValues(alpha: 0.3),
                        blurRadius: 12)
                  ]
                : null,
          ),
          child: Icon(icon, color: color, size: 24),
        ),
        const SizedBox(height: 8),
        Text(label,
            style: TextStyle(
                color: color, fontSize: 12, fontFamily: 'Cairo')),
        Text(
          connected ? 'متصل' : 'غير متصل',
          style: TextStyle(
              color: color.withValues(alpha: 0.7),
              fontSize: 11,
              fontFamily: 'Cairo'),
        ),
      ],
    );
  }
}

class _ActivePersonalityCard extends StatelessWidget {
  final Personality? personality;
  const _ActivePersonalityCard({this.personality});

  @override
  Widget build(BuildContext context) {
    return NebulaCard(
      glowing: personality != null,
      borderColor: AppColors.purple.withValues(alpha: 0.5),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppColors.purpleGradient,
              boxShadow: [
                BoxShadow(
                    color: AppColors.purple.withValues(alpha: 0.4),
                    blurRadius: 12)
              ],
            ),
            child: const Icon(Icons.person_outline,
                color: Colors.white, size: 28),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('الشخصية النشطة',
                    style: TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 12,
                        fontFamily: 'Cairo')),
                const SizedBox(height: 4),
                Text(
                  personality?.name ?? 'لا توجد شخصية نشطة',
                  style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      fontFamily: 'Cairo'),
                ),
                if (personality != null)
                  Text(
                    '${personality!.dialect} · ${personality!.languageMix}',
                    style: const TextStyle(
                        color: AppColors.teal,
                        fontSize: 12,
                        fontFamily: 'Cairo'),
                  ),
              ],
            ),
          ),
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: personality != null
                  ? AppColors.success.withValues(alpha: 0.15)
                  : AppColors.textMuted.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                  color: personality != null
                      ? AppColors.success.withValues(alpha: 0.5)
                      : AppColors.textMuted.withValues(alpha: 0.3)),
            ),
            child: Text(
              personality != null ? 'نشط' : 'خامل',
              style: TextStyle(
                  color: personality != null
                      ? AppColors.success
                      : AppColors.textMuted,
                  fontSize: 11,
                  fontFamily: 'Cairo'),
            ),
          ),
        ],
      ),
    );
  }
}

class _SystemOverviewCard extends StatelessWidget {
  final List<Personality> personalities;
  const _SystemOverviewCard({required this.personalities});

  @override
  Widget build(BuildContext context) {
    return NebulaCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'نظرة عامة'),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                  child: _StatItem(
                      label: 'الشخصيات',
                      value: personalities.length.toString(),
                      icon: Icons.people_outline,
                      color: AppColors.purple)),
              const SizedBox(width: 12),
              Expanded(
                  child: _StatItem(
                      label: 'نشطة',
                      value: personalities
                          .where((p) => p.isActive)
                          .length
                          .toString(),
                      icon: Icons.check_circle_outline,
                      color: AppColors.success)),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatItem(
      {required this.label,
      required this.value,
      required this.icon,
      required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 24),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value,
                  style: TextStyle(
                      color: color,
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      fontFamily: 'Cairo')),
              Text(label,
                  style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                      fontFamily: 'Cairo')),
            ],
          ),
        ],
      ),
    );
  }
}

