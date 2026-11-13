import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/storage_service.dart';
import '../services/locale_service.dart';
import '../widgets/common_widgets.dart';
import 'language_appearance_screen.dart';
import 'notification_preferences_screen.dart';
import 'security_2fa_screen.dart';
import 'data_privacy_screen.dart';
import 'main_shell.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String _fullName = 'امير';
  String _email = 'amer.mercer@futuremind.ai';
  final String _phone = '+966 50 123 4567';
  final String _location = 'الرياض، المملكة العربية السعودية';
  final String _organization = 'مركز الأبحاث المتقدمة والتقنيات الحيوية';
  final String _joinDate = 'مارس 2023';

  @override
  void initState() {
    super.initState();
    _loadUser();
  }

  void _loadUser() {
    final user = StorageService.instance.getUser();
    if (user != null) {
      setState(() {
        if (user.fullName.isNotEmpty) _fullName = user.fullName;
        if (user.email.isNotEmpty) _email = user.email;
      });
    }
  }

  void _showEditProfileDialog() {
    final nameCtrl = TextEditingController(text: _fullName);
    final emailCtrl = TextEditingController(text: _email);

    showDialog(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
          title: const Text(
            'تعديل البيانات الشخصية',
            style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameCtrl,
                decoration: InputDecoration(
                  labelText: 'الاسم الكامل',
                  labelStyle: const TextStyle(fontFamily: 'Cairo'),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                  labelText: 'البريد الإلكتروني',
                  labelStyle: const TextStyle(fontFamily: 'Cairo'),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
            ),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _fullName = nameCtrl.text.trim();
                  _email = emailCtrl.text.trim();
                });
                Navigator.of(ctx).pop();
                showSuccessSnackbar(context, 'تم تحديث البيانات بنجاح!');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF006677),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: const Text('حفظ',
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
      textDirection: LocaleService.instance.textDirection,
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
            children: [
              // 1. Top Header Bar:
              // Arabic: Menu on LEFT, Exit & Actions on RIGHT.
              // English: Swaps between Menu (RIGHT) and Exit & Actions (LEFT).
              Builder(
                builder: (context) {
                  final isArabic = LocaleService.instance.isArabic;

                  final menuBtn = InkWell(
                    onTap: () => MainShell.openSideMenu(context),
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

                  final actionsSection = Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _buildTopIconButton(
                        icon: Icons.notifications_none_rounded,
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  const NotificationPreferencesScreen(),
                            ),
                          );
                        },
                      ),
                      const SizedBox(width: 8),
                      _buildTopIconButton(
                        icon: Icons.settings_outlined,
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => const Security2FAScreen(),
                            ),
                          );
                        },
                      ),
                      const SizedBox(width: 8),
                      // Exit / Back button with arrow (Transparent)
                      InkWell(
                        onTap: () {
                          if (Navigator.canPop(context)) {
                            Navigator.pop(context);
                          } else {
                            MainShell.navigateTo(context, 0);
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
                            isArabic
                                ? Icons.arrow_forward_rounded
                                : Icons.arrow_back_rounded,
                            size: 20,
                            color: const Color(0xFF0F172A),
                          ),
                        ),
                      ),
                    ],
                  );

                  final leftSide = isArabic ? menuBtn : actionsSection;
                  final rightSide = isArabic ? actionsSection : menuBtn;

                  return Directionality(
                    textDirection: TextDirection.ltr,
                    child: Row(
                      children: [
                        leftSide,
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            LocaleService.instance.translate('nav_profile'),
                            textAlign:
                                isArabic ? TextAlign.right : TextAlign.left,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF0F172A),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        rightSide,
                      ],
                    ),
                  );
                },
              ),
              const SizedBox(height: 18),

              // 2. Centered User Avatar & Verified Name
              Center(
                child: Column(
                  children: [
                    Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Container(
                          width: 86,
                          height: 86,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFF006677).withValues(alpha: 0.2),
                              width: 3,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.08),
                                blurRadius: 16,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ClipOval(
                            child: Image.asset(
                              'assets/images/cyborg_bg.jpg',
                              fit: BoxFit.cover,
                            ),
                          ),
                        ),
                        // Online green dot
                        Positioned(
                          bottom: 2,
                          left: 4,
                          child: Container(
                            width: 14,
                            height: 14,
                            decoration: BoxDecoration(
                              color: const Color(0xFF10B981),
                              shape: BoxShape.circle,
                              border: Border.all(color: Colors.white, width: 2),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _fullName,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 19,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Icon(
                          Icons.verified_rounded,
                          size: 18,
                          color: Color(0xFF0284C7),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),

              // 3. Action Buttons: تعديل البيانات & مشاركة الملف
              Row(
                children: [
                  Expanded(
                    child: GestureDetector(
                      onTap: _showEditProfileDialog,
                      child: Container(
                        height: 44,
                        decoration: BoxDecoration(
                          color: const Color(0xFF006677),
                          borderRadius: BorderRadius.circular(14),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF006677).withValues(alpha: 0.2),
                              blurRadius: 10,
                              offset: const Offset(0, 3),
                            ),
                          ],
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.edit_outlined,
                                color: Colors.white, size: 16),
                            SizedBox(width: 6),
                            Text(
                              'تعديل البيانات',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: GestureDetector(
                      onTap: () {
                        Clipboard.setData(ClipboardData(text: _email));
                        showSuccessSnackbar(
                            context, 'تم نسخ بيانات الملف الشخصي إلى الحافظة.');
                      },
                      child: Container(
                        height: 44,
                        decoration: BoxDecoration(
                          color: const Color(0xFFEEF2FF),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.share_outlined,
                                color: Color(0xFF4F46E5), size: 16),
                            SizedBox(width: 6),
                            Text(
                              'مشاركة الملف',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF4F46E5),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),

              // 4. Section: معلومات الاتصال والجهة (المعلومات الأساسية)
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'معلومات الاتصال والجهة',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 14.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    'المعلومات الأساسية',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Colors.blue.shade700,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.02),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    // البريد الإلكتروني
                    _buildInfoItem(
                      label: 'البريد الإلكتروني',
                      value: _email,
                      icon: Icons.alternate_email_rounded,
                      badge: 'مؤكد',
                      onCopy: () {
                        Clipboard.setData(ClipboardData(text: _email));
                        showSuccessSnackbar(context, 'تم نسخ البريد الإلكتروني.');
                      },
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    // رقم الهاتف
                    _buildInfoItem(
                      label: 'رقم الهاتف',
                      value: _phone,
                      subValue: 'رئيسي',
                      icon: Icons.phone_outlined,
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    // الموقع الجغرافي
                    _buildInfoItem(
                      label: 'الموقع الجغرافي',
                      value: _location,
                      icon: Icons.location_on_outlined,
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    // المؤسسة والجهة
                    _buildInfoItem(
                      label: 'المؤسسة والجهة',
                      value: _organization,
                      icon: Icons.domain_rounded,
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    // تاريخ الانضمام
                    _buildInfoItem(
                      label: 'تاريخ الانضمام',
                      value: _joinDate,
                      icon: Icons.calendar_today_outlined,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // 5. Section: التفضيلات والأمان (إعدادات الحساب)
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'التفضيلات والأمان',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 14.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    'إعدادات الحساب',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Colors.blue.shade700,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),

              // Item 1: تفضيلات الإشعارات والتنبيهات -> NotificationPreferencesScreen
              _buildNavCard(
                title: 'تفضيلات الإشعارات والتنبيهات',
                subtitle: 'البريد، المنصة، التحديثات الدورية',
                icon: Icons.notifications_active_outlined,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const NotificationPreferencesScreen(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),

              // Item 2: الأمان والتحقق بخطوتين -> Security2FAScreen
              _buildNavCard(
                title: 'الأمان والتحقق بخطوتين',
                subtitle: 'كلمة المرور ومفاتيح الأمان',
                icon: Icons.shield_outlined,
                badge: 'مفعّل',
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const Security2FAScreen(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),

              // Item 3: إدارة البيانات والخصوصية -> DataPrivacyScreen
              _buildNavCard(
                title: 'إدارة البيانات والخصوصية',
                subtitle: 'تصدير السجلات، سياسات التخزين',
                icon: Icons.history_rounded,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const DataPrivacyScreen(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),

              // Item 4: لغة التطبيق والمظهر -> LanguageAppearanceScreen
              _buildNavCard(
                title: 'لغة التطبيق والمظهر',
                subtitle: 'العربية (المملكة) • المظهر الهادئ',
                icon: Icons.translate_rounded,
                endText: 'العربية',
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const LanguageAppearanceScreen(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 20),

              const SizedBox(height: 100), // padding for bottom nav
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopIconButton({
    required IconData icon,
    Color? color,
    Color? bgColor,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: bgColor ?? Colors.white,
          shape: BoxShape.circle,
          border: Border.all(color: const Color(0xFFE2E8F0)),
        ),
        child: Icon(icon, color: color ?? const Color(0xFF334155), size: 19),
      ),
    );
  }

  Widget _buildInfoItem({
    required String label,
    required String value,
    String? subValue,
    required IconData icon,
    String? badge,
    VoidCallback? onCopy,
  }) {
    return Row(
      children: [
        if (onCopy != null)
          IconButton(
            icon: const Icon(Icons.copy_rounded,
                size: 15, color: Color(0xFF94A3B8)),
            onPressed: onCopy,
            constraints: const BoxConstraints(),
            padding: EdgeInsets.zero,
          ),
        if (badge != null) ...[
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFFECFDF5),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              badge,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 10.5,
                fontWeight: FontWeight.bold,
                color: Color(0xFF10B981),
              ),
            ),
          ),
        ],
        if (subValue != null) ...[
          Text(
            subValue,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 11,
              color: Color(0xFF94A3B8),
            ),
          ),
          const SizedBox(width: 8),
        ],
        const Spacer(),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11,
                color: Color(0xFF94A3B8),
              ),
            ),
            Text(
              value,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: Color(0xFF1E293B),
              ),
            ),
          ],
        ),
        const SizedBox(width: 10),
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: const Color(0xFFEFF6FF),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: const Color(0xFF0284C7), size: 19),
        ),
      ],
    );
  }

  Widget _buildNavCard({
    required String title,
    required String subtitle,
    required IconData icon,
    String? badge,
    String? endText,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xFFE2E8F0)),
        ),
        child: Row(
          children: [
            const Icon(Icons.arrow_back_ios_rounded,
                size: 13, color: Color(0xFF94A3B8)),
            if (endText != null) ...[
              const SizedBox(width: 6),
              Text(
                endText,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11.5,
                  color: Color(0xFF006677),
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
            if (badge != null) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  badge,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10.5,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF10B981),
                  ),
                ),
              ),
            ],
            const Spacer(),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
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
            const SizedBox(width: 10),
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: const Color(0xFFEEF2FF),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: const Color(0xFF4F46E5), size: 20),
            ),
          ],
        ),
      ),
    );
  }
}
