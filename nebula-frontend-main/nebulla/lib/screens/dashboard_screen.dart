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

  Future<void> _load({bool showErrors = false}) async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        _repo.getDeviceStatus(),
        _repo.getPersonalities(),
      ]);
      final status = results[0] as DeviceStatus;
      final personalities = results[1] as List<Personality>;
      if (!mounted) return;
      setState(() {
        _status = status;
        _personalities = personalities;
        _activePersonality =
            personalities.where((p) => p.isActive).firstOrNull;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      if (showErrors) {
        showErrorSnackbar(context, 'خطأ في تحميل البيانات: $e');
      }
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
            onRefresh: () => _load(showErrors: true),
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
                        child: const Icon(Icons.smart_toy_outlined,
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
                      onPressed: () => _load(showErrors: true),
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
    final hasActiveConnection = status?.esp32Connected == true ||
        status?.phoneConnected == true ||
        status?.deskConnected == true;

    return NebulaCard(
      glowing: hasActiveConnection,
      borderColor: hasActiveConnection
          ? AppColors.teal.withValues(alpha: 0.5)
          : AppColors.cardBorder,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'حالة الاتصال'),
          const SizedBox(height: 18),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _ChannelStatus(
                  label: 'الهاتف',
                  icon: Icons.phone_android_rounded,
                  connected: status?.phoneConnected ?? false),
              _ChannelStatus(
                  label: 'سطح المكتب',
                  icon: Icons.desktop_windows_rounded,
                  connected: status?.deskConnected ?? false),
              _ChannelStatus(
                  label: 'ESP32',
                  icon: Icons.memory_rounded,
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
    const activeColor = AppColors.success;
    const inactiveBorder = Color(0xFF223A5E);
    const inactiveBg = Color(0xFF132238);
    const inactiveIcon = Color(0xFFCBD5E1);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 58,
          height: 58,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: connected
                ? activeColor.withValues(alpha: 0.15)
                : inactiveBg,
            border: Border.all(
              color: connected ? activeColor : inactiveBorder,
              width: connected ? 1.8 : 1.2,
            ),
            boxShadow: connected
                ? [
                    BoxShadow(
                      color: activeColor.withValues(alpha: 0.4),
                      blurRadius: 14,
                      spreadRadius: 1,
                    )
                  ]
                : [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.25),
                      blurRadius: 6,
                    )
                  ],
          ),
          child: Icon(
            icon,
            color: connected ? activeColor : inactiveIcon,
            size: 26,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w600,
            fontFamily: 'Cairo',
          ),
        ),
        const SizedBox(height: 2),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: connected
                ? activeColor.withValues(alpha: 0.12)
                : const Color(0xFF1A2B42),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            connected ? 'متصل' : 'غير متصل',
            style: TextStyle(
              color: connected ? activeColor : const Color(0xFF94A3B8),
              fontSize: 11,
              fontWeight: connected ? FontWeight.w700 : FontWeight.w500,
              fontFamily: 'Cairo',
            ),
          ),
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
    final isActive = personality != null;

    return NebulaCard(
      glowing: isActive,
      borderColor: isActive
          ? AppColors.purple.withValues(alpha: 0.6)
          : AppColors.cardBorder,
      child: Row(
        children: [
          Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppColors.purpleGradient,
              boxShadow: [
                BoxShadow(
                  color: AppColors.purple.withValues(alpha: 0.45),
                  blurRadius: 14,
                  spreadRadius: 1,
                )
              ],
            ),
            child: const Icon(Icons.person_rounded,
                color: Colors.white, size: 30),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'الشخصية النشطة',
                  style: TextStyle(
                    color: Color(0xFF94A3B8),
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    fontFamily: 'Cairo',
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  personality?.name ?? 'لا توجد شخصية نشطة',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    fontFamily: 'Cairo',
                  ),
                ),
                if (personality != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    '${personality!.dialect} · ${personality!.languageMix}',
                    style: const TextStyle(
                      color: AppColors.teal,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      fontFamily: 'Cairo',
                    ),
                  ),
                ],
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
            decoration: BoxDecoration(
              color: isActive
                  ? AppColors.success.withValues(alpha: 0.15)
                  : const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isActive
                    ? AppColors.success.withValues(alpha: 0.6)
                    : const Color(0xFF334155),
                width: 1.2,
              ),
            ),
            child: Text(
              isActive ? 'نشط' : 'خامل',
              style: TextStyle(
                color: isActive ? AppColors.success : const Color(0xFF94A3B8),
                fontSize: 12,
                fontWeight: FontWeight.w700,
                fontFamily: 'Cairo',
              ),
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
    final activeCount = personalities.where((p) => p.isActive).length;

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
                  icon: Icons.people_alt_rounded,
                  color: AppColors.purple,
                  bgColor: const Color(0xFF141F36),
                  borderColor: const Color(0xFF283B60),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _StatItem(
                  label: 'نشطة',
                  value: activeCount.toString(),
                  icon: Icons.check_circle_rounded,
                  color: AppColors.success,
                  bgColor: const Color(0xFF0C2430),
                  borderColor: const Color(0xFF1B4958),
                ),
              ),
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
  final Color bgColor;
  final Color borderColor;

  const _StatItem({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    required this.bgColor,
    required this.borderColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: borderColor, width: 1.2),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  fontFamily: 'Cairo',
                ),
              ),
              Text(
                label,
                style: const TextStyle(
                  color: Color(0xFFCBD5E1),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  fontFamily: 'Cairo',
                ),
              ),
            ],
          ),
          Icon(icon, color: color, size: 26),
        ],
      ),
    );
  }
}
