import 'package:flutter/material.dart';
import '../widgets/common_widgets.dart';

class NotificationPreferencesScreen extends StatefulWidget {
  const NotificationPreferencesScreen({super.key});

  @override
  State<NotificationPreferencesScreen> createState() =>
      _NotificationPreferencesScreenState();
}

class _NotificationPreferencesScreenState
    extends State<NotificationPreferencesScreen> {
  // General
  bool _allowPopups = true;
  bool _audioTones = true;
  bool _vibrate = true;

  // Categories
  bool _messagesAlerts = true;
  final bool _securityAlerts = true; // Always enabled
  bool _eventsAlerts = true;

  // Channels
  bool _directPhone = true;
  bool _sms = false;

  bool _isSaving = false;

  void _savePreferences() async {
    setState(() => _isSaving = true);
    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    setState(() => _isSaving = false);
    showSuccessSnackbar(context, 'تم حفظ تفضيلات الإشعارات بنجاح!');
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        appBar: AppBar(
          backgroundColor: Colors.white,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.arrow_forward_ios_rounded,
                color: Color(0xFF1E293B), size: 20),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: const Text(
            'تفضيلات الإشعارات والتنبيهات',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0F172A),
            ),
          ),
          centerTitle: true,
        ),
        body: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          children: [
            // 1. General System Notifications
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'إشعارات التطبيق العامة',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13.5,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF0F172A),
                  ),
                ),
                Text(
                  'إعدادات النظام',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    color: Colors.blue.shade700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            _buildToggleCard(
              title: 'السماح بالإشعارات المنبثقة',
              subtitle: 'عرض التنبيهات على شاشة القفل والراية العلوية',
              icon: Icons.notifications_active_outlined,
              value: _allowPopups,
              onChanged: (v) => setState(() => _allowPopups = v),
            ),
            const SizedBox(height: 8),
            _buildToggleCard(
              title: 'نغمة التنبيه الصوتية',
              subtitle: 'تشغيل صوت خفيف عند ورود إشعار جديد',
              icon: Icons.volume_up_outlined,
              value: _audioTones,
              onChanged: (v) => setState(() => _audioTones = v),
            ),
            const SizedBox(height: 8),
            _buildToggleCard(
              title: 'الاهتزاز عند التنبيه',
              subtitle: 'اهتزاز هادئ عند تلقي الإشعارات الهامة',
              icon: Icons.vibration_rounded,
              value: _vibrate,
              onChanged: (v) => setState(() => _vibrate = v),
            ),
            const SizedBox(height: 20),

            // 2. Notification Categories
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'أنواع تنبيهات التطبيق',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13.5,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF0F172A),
                  ),
                ),
                Text(
                  'تخصيص الفئات',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    color: Colors.blue.shade700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            _buildToggleCard(
              title: 'الرسائل والمحادثات الجديدة',
              subtitle: 'تنبيهات الرسائل الخاصة والردود المباشرة',
              icon: Icons.chat_bubble_outline_rounded,
              value: _messagesAlerts,
              onChanged: (v) => setState(() => _messagesAlerts = v),
            ),
            const SizedBox(height: 8),
            _buildToggleCard(
              title: 'تحديثات الحساب والأمان',
              subtitle: 'تسجيل الدخول والتغييرات الأمنية المهمة',
              icon: Icons.security_rounded,
              value: _securityAlerts,
              iconColor: const Color(0xFFDC2626),
              isAlwaysEnabled: true,
              onChanged: null,
            ),
            const SizedBox(height: 8),
            _buildToggleCard(
              title: 'الأنشطة والفعاليات',
              subtitle: 'تحديثات التفاعل ومتابعة الأحداث ذات الصلة',
              icon: Icons.calendar_month_outlined,
              value: _eventsAlerts,
              onChanged: (v) => setState(() => _eventsAlerts = v),
            ),
            const SizedBox(height: 20),

            // 3. Channels
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'قنوات التواصل',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13.5,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF0F172A),
                  ),
                ),
                Text(
                  'طرق الاستلام',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    color: Colors.blue.shade700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            _buildToggleCard(
              title: 'إشعارات الهاتف المباشرة',
              subtitle: 'تلقي الإشعارات الفورية على هذا الجهاز',
              icon: Icons.smartphone_rounded,
              value: _directPhone,
              onChanged: (v) => setState(() => _directPhone = v),
            ),
            const SizedBox(height: 8),
            _buildToggleCard(
              title: 'الرسائل النصية القصيرة (SMS)',
              subtitle: 'رموز التأكيد والتنبيهات المستعجلة فقط',
              icon: Icons.sms_outlined,
              value: _sms,
              onChanged: (v) => setState(() => _sms = v),
            ),
            const SizedBox(height: 24),

            // Save Action Button
            GestureDetector(
              onTap: _isSaving ? null : _savePreferences,
              child: Container(
                height: 52,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF0072FF), Color(0xFF00C6FF)],
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF0072FF).withValues(alpha: 0.3),
                      blurRadius: 16,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Center(
                  child: _isSaving
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.check_circle_outline_rounded,
                                color: Colors.white, size: 20),
                            SizedBox(width: 8),
                            Text(
                              'حفظ تفضيلات الإشعارات',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 14.5,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ],
                        ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            const Center(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.verified_user_outlined,
                      size: 13, color: Color(0xFF64748B)),
                  SizedBox(width: 4),
                  Text(
                    'سيتم حفظ وتطبيق التفضيلات فوراً على حسابك',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Color(0xFF64748B),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildToggleCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required bool value,
    Color? iconColor,
    bool isAlwaysEnabled = false,
    ValueChanged<bool>? onChanged,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Row(
        children: [
          // Switch or badge
          if (isAlwaysEnabled)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFFEEF2FF),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.lock_rounded, size: 12, color: Color(0xFF4F46E5)),
                  SizedBox(width: 4),
                  Text(
                    'دائماً مفعل',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF4F46E5),
                    ),
                  ),
                ],
              ),
            )
          else
            Switch(
              value: value,
              onChanged: onChanged,
              activeThumbColor: const Color(0xFF0072FF),
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF1E293B),
                  ),
                ),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    color: Color(0xFF64748B),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: (iconColor ?? const Color(0xFF0072FF)).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              icon,
              color: iconColor ?? const Color(0xFF0072FF),
              size: 20,
            ),
          ),
        ],
      ),
    );
  }
}
