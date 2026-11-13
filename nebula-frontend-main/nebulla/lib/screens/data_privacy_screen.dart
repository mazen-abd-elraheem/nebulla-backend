import 'package:flutter/material.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'login_screen.dart';

class DataPrivacyScreen extends StatefulWidget {
  const DataPrivacyScreen({super.key});

  @override
  State<DataPrivacyScreen> createState() => _DataPrivacyScreenState();
}

class _DataPrivacyScreenState extends State<DataPrivacyScreen> {
  bool _shareAnalytics = false;
  bool _keepSearchHistory = true;

  // Retention: 0 = 3 months, 1 = 6 months, 2 = 1 year, 3 = forever
  int _retentionIndex = 1;

  void _showDeleteAccountConfirmation() {
    showDialog(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
          title: const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Color(0xFFDC2626), size: 24),
              SizedBox(width: 8),
              Text(
                'تأكيد حذف الحساب',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.bold,
                  color: Color(0xFFDC2626),
                ),
              ),
            ],
          ),
          content: const Text(
            'هل أنت متأكد تماماً من رغبتك في حذف الحساب نهائياً؟ هذا الإجراء لا يمكن التراجع عنه وسيتم مسح كافة البيانات من الخوادم فوراً.',
            style: TextStyle(fontFamily: 'Cairo', fontSize: 13, color: Color(0xFF475569)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.of(ctx).pop();
                await StorageService.instance.clearToken();
                if (mounted) {
                  showSuccessSnackbar(context, 'تم حذف بيانات الحساب وتسجيل الخروج.');
                  Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (route) => false,
                  );
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFDC2626),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: const Text('نعم، احذف نهائياً',
                  style: TextStyle(fontFamily: 'Cairo', color: Colors.white)),
            ),
          ],
        ),
      ),
    );
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
            icon: const Icon(
              Icons.arrow_forward_ios_rounded,
              textDirection: TextDirection.ltr,
              color: Color(0xFF1E293B),
              size: 20,
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F7FA),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.verified_user_rounded,
                    size: 16, color: Color(0xFF006677)),
              ),
              const SizedBox(width: 8),
              const Text(
                'إدارة البيانات والخصوصية',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF0F172A),
                ),
              ),
            ],
          ),
          centerTitle: true,
          actions: [
            Padding(
              padding: const EdgeInsets.only(left: 14),
              child: Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: Color(0xFF006677),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.person_rounded,
                    color: Colors.white, size: 18),
              ),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          children: [
            // 1. Section: أذونات المشاركة والتتبع
            _buildSectionHeader(
              title: 'أذونات المشاركة والتتبع',
              subtitle: 'تحكم شفاف ودقيق في تدفق معلوماتك',
              icon: Icons.tune_rounded,
            ),
            const SizedBox(height: 10),
            _buildCard(
              children: [
                _buildToggleRow(
                  title: 'مشاركة تحليلات الاستخدام',
                  subtitle: 'إرسال تقارير الأداء المجهولة لتحسين الخدمة',
                  value: _shareAnalytics,
                  onChanged: (v) => setState(() => _shareAnalytics = v),
                ),
                const Divider(color: Color(0xFFF1F5F9), height: 20),
                _buildToggleRow(
                  title: 'الاحتفاظ بسجل البحث الداخلي',
                  subtitle: 'تسهيل الوصول السريع للعمليات والمصطلحات السابقة',
                  value: _keepSearchHistory,
                  onChanged: (v) => setState(() => _keepSearchHistory = v),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // 2. Section: مدة الحفظ التلقائي
            _buildSectionHeader(
              title: 'مدة الحفظ التلقائي',
              subtitle: 'حذف الأنشطة غير النشطة آلياً بعد انقضاء المدة',
              icon: Icons.access_time_rounded,
            ),
            const SizedBox(height: 10),
            _buildCard(
              children: [
                Row(
                  children: [
                    _buildRetentionOption('3 أشهر', 0),
                    const SizedBox(width: 8),
                    _buildRetentionOption('6 أشهر', 1),
                    const SizedBox(width: 8),
                    _buildRetentionOption('سنة', 2),
                    const SizedBox(width: 8),
                    _buildRetentionOption('للأبد', 3),
                  ],
                ),
                const SizedBox(height: 14),
                const Row(
                  children: [
                    Icon(Icons.info_outline_rounded,
                        size: 15, color: Color(0xFF64748B)),
                    SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'سيتم حذف السجلات التي تجاوزت 6 أشهر بنهاية كل دورة شهرية.',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          color: Color(0xFF64748B),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 20),

            // 3. Section: محو السجل وإدارة الحساب
            _buildSectionHeader(
              title: 'محو السجل وإدارة الحساب',
              subtitle: 'عمليات الحذف الفوري وإلغاء البيانات',
              icon: Icons.delete_outline_rounded,
              iconColor: const Color(0xFFDC2626),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFFECACA)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.warning_amber_rounded,
                          size: 18, color: Color(0xFFDC2626)),
                      SizedBox(width: 8),
                      Text(
                        'إلغاء وتدمير الحساب نهائياً',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13.5,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFFDC2626),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'هذا الإجراء غير قابل للتراجع، سيتم محو جميع المعرفات، الأرشيفات، والملفات المرتبطة بهذا الحساب فوراً من السجلات.',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11.5,
                      color: Color(0xFF7F1D1D),
                    ),
                  ),
                  const SizedBox(height: 14),
                  GestureDetector(
                    onTap: _showDeleteAccountConfirmation,
                    child: Container(
                      height: 48,
                      decoration: BoxDecoration(
                        color: const Color(0xFFB91C1C),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFFB91C1C).withValues(alpha: 0.3),
                            blurRadius: 10,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: const Center(
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.person_remove_rounded,
                                color: Colors.white, size: 18),
                            SizedBox(width: 8),
                            Text(
                              'حذف الحساب وكافة البيانات نهائياً',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13.5,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
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
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionHeader({
    required String title,
    required String subtitle,
    required IconData icon,
    Color? iconColor,
  }) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: (iconColor ?? const Color(0xFF006677)).withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: iconColor ?? const Color(0xFF006677), size: 19),
        ),
        const SizedBox(width: 10),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 13.5,
                fontWeight: FontWeight.bold,
                color: Color(0xFF0F172A),
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
      ],
    );
  }

  Widget _buildCard({required List<Widget> children}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    );
  }

  Widget _buildToggleRow({
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Row(
      children: [
        Switch(
          value: value,
          onChanged: onChanged,
          activeThumbColor: const Color(0xFF006677),
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
      ],
    );
  }

  Widget _buildRetentionOption(String title, int index) {
    final isSelected = _retentionIndex == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _retentionIndex = index),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? Colors.white : const Color(0xFFF1F5F9),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isSelected ? const Color(0xFF006677) : Colors.transparent,
              width: 1.5,
            ),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.05),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Center(
            child: Text(
              title,
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11.5,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                color: isSelected ? const Color(0xFF006677) : const Color(0xFF64748B),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
