import 'package:flutter/material.dart';

class LanguageAppearanceScreen extends StatefulWidget {
  const LanguageAppearanceScreen({super.key});

  @override
  State<LanguageAppearanceScreen> createState() =>
      _LanguageAppearanceScreenState();
}

class _LanguageAppearanceScreenState extends State<LanguageAppearanceScreen> {
  // Theme: 0 = Pure Light, 1 = Dark, 2 = Auto
  int _selectedTheme = 0;
  bool _eyeProtection = true;

  // Font size: 0 = Small, 1 = Default, 2 = Large, 3 = Extra Large
  int _fontSizeIndex = 1;

  // Language: 'ar' or 'en'
  bool _autoMatchPhoneLang = false;
  String _selectedLang = 'ar';

  // Regional Preferences
  int _calendarType = 0; // 0 = Gregorian (G), 1 = Hijri (H)
  int _timeFormat = 0; // 0 = 12h, 1 = 24h

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
              color: Color(0xFF1E293B),
              size: 20,
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: const Text(
            'لغة التطبيق والمظهر',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0F172A),
            ),
          ),
          centerTitle: true,
          actions: [
            Padding(
              padding: const EdgeInsets.only(left: 16),
              child: Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFF00E5FF), width: 2),
                ),
                child: Center(
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      color: Color(0xFF00E5FF),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          children: [
            // 1. Top Banner
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFFE0F7FA), Color(0xFFF1F5F9)],
                  begin: Alignment.topRight,
                  end: Alignment.bottomLeft,
                ),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFCCFBF1)),
              ),
              child: Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(14),
                    child: Image.asset(
                      'assets/images/cyborg_bg.jpg',
                      width: 50,
                      height: 50,
                      fit: BoxFit.cover,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              'التخصيص والعرض المرئي',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                            SizedBox(width: 6),
                            Icon(Icons.circle, size: 7, color: Color(0xFF00E5FF)),
                          ],
                        ),
                        SizedBox(height: 2),
                        Text(
                          'تنسيق النقاء اللوني والخطوط البصرية المتطورة',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 11,
                            color: Color(0xFF64748B),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),

            // 2. Section: المظهر والسمة البصرية
            _buildSectionHeader(
              title: 'المظهر والسمة البصرية',
              icon: Icons.palette_outlined,
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                _buildThemeCard(
                  index: 0,
                  title: 'فاتح نقي',
                  badgeText: _selectedTheme == 0 ? '✓ نشط' : null,
                  isActive: _selectedTheme == 0,
                  previewColor: Colors.white,
                  borderColor: const Color(0xFF0284C7),
                  onTap: () => setState(() => _selectedTheme = 0),
                ),
                const SizedBox(width: 10),
                _buildThemeCard(
                  index: 1,
                  title: 'داكن',
                  badgeText: _selectedTheme == 1 ? '✓ نشط' : 'تفعيل',
                  isActive: _selectedTheme == 1,
                  previewColor: const Color(0xFF1E293B),
                  borderColor: const Color(0xFF334155),
                  onTap: () => setState(() => _selectedTheme = 1),
                ),
                const SizedBox(width: 10),
                _buildThemeCard(
                  index: 2,
                  title: 'تلقائي',
                  badgeText: 'نظام الجهاز',
                  isActive: _selectedTheme == 2,
                  previewColor: const Color(0xFFE2E8F0),
                  borderColor: const Color(0xFF94A3B8),
                  onTap: () => setState(() => _selectedTheme = 2),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Eye Protection Switch
            _buildSettingCard(
              title: 'حماية العين والضوء الهادئ',
              subtitle: 'تقليل الإشعاع الأزرق لتحسين القراءة',
              icon: Icons.remove_red_eye_outlined,
              trailing: Switch(
                value: _eyeProtection,
                onChanged: (val) => setState(() => _eyeProtection = val),
                activeThumbColor: const Color(0xFF006677),
              ),
            ),
            const SizedBox(height: 20),

            // 3. Section: الخط وحجم النصوص
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _buildSectionHeader(
                  title: 'الخط وحجم النصوص',
                  icon: Icons.text_fields_rounded,
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE0F2FE),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    'معاينة فورية',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0284C7),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),

            // Font Preview Box
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.smart_toy_outlined,
                          size: 16, color: Color(0xFF64748B)),
                      SizedBox(width: 6),
                      Text(
                        'نص العينة التفاعلي',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          color: Color(0xFF64748B),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'واجهة ذكية ومريحة للعين، مصممة بدقة الخوارزميات الحيوية.',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: _getFontSize(),
                      fontWeight: FontWeight.w600,
                      color: const Color(0xFF0F172A),
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    '• الخط الافتراضي',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Color(0xFF006677),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),

            // Font Size Selector Buttons
            Row(
              children: [
                _buildFontSizeButton(label: 'صغير', sub: 'A-', idx: 0),
                const SizedBox(width: 8),
                _buildFontSizeButton(label: 'افتراضي', sub: 'A', idx: 1),
                const SizedBox(width: 8),
                _buildFontSizeButton(label: 'كبير', sub: 'A+', idx: 2),
                const SizedBox(width: 8),
                _buildFontSizeButton(label: 'كبير جداً', sub: 'A++', idx: 3),
              ],
            ),
            const SizedBox(height: 20),

            // 4. Section: لغة التطبيق والواجهة
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _buildSectionHeader(
                  title: 'لغة التطبيق والواجهة',
                  icon: Icons.translate_rounded,
                ),
                const Text(
                  'مدعوم RTL',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10.5,
                    color: Color(0xFF94A3B8),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),

            // Auto-match switch
            _buildSettingCard(
              title: 'مطابقة لغة الهاتف تلقائياً',
              subtitle: 'التبديل التلقائي وفق إعدادات نظام التشغيل',
              icon: Icons.sync_rounded,
              trailing: Switch(
                value: _autoMatchPhoneLang,
                onChanged: (v) => setState(() => _autoMatchPhoneLang = v),
                activeThumbColor: const Color(0xFF006677),
              ),
            ),
            const SizedBox(height: 8),

            // Arabic option
            _buildLanguageCard(
              title: 'العربية',
              badge: 'ض',
              isSelected: _selectedLang == 'ar',
              onTap: () => setState(() => _selectedLang = 'ar'),
            ),
            const SizedBox(height: 8),

            // English option
            _buildLanguageCard(
              title: 'English',
              subtitle: 'United States (LTR)',
              badge: 'EN',
              isSelected: _selectedLang == 'en',
              onTap: () => setState(() => _selectedLang = 'en'),
            ),
            const SizedBox(height: 20),

            // 5. Section: التفضيلات الإقليمية والتنسيق
            _buildSectionHeader(
              title: 'التفضيلات الإقليمية والتنسيق',
              icon: Icons.tune_rounded,
            ),
            const SizedBox(height: 10),

            // Calendar Type Card
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.calendar_today_rounded,
                              size: 16, color: Color(0xFF64748B)),
                          SizedBox(width: 8),
                          Text(
                            'نوع التقويم المعتمد',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF1E293B),
                            ),
                          ),
                        ],
                      ),
                      Text(
                        _calendarType == 0 ? 'الميلادي (G)' : 'الهجري (H)',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF0284C7),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _buildChoicePill(
                          title: 'الميلادي (G)',
                          isSelected: _calendarType == 0,
                          onTap: () => setState(() => _calendarType = 0),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _buildChoicePill(
                          title: 'الهجري (H)',
                          isSelected: _calendarType == 1,
                          onTap: () => setState(() => _calendarType = 1),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),

            // Time Format Card
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.access_time_rounded,
                              size: 16, color: Color(0xFF64748B)),
                          SizedBox(width: 8),
                          Text(
                            'تنسيق عرض الوقت',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF1E293B),
                            ),
                          ),
                        ],
                      ),
                      Text(
                        _timeFormat == 0 ? '12 ساعة (ص/م)' : '24 ساعة',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF0284C7),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _buildChoicePill(
                          title: '12 ساعة (02:45 م)',
                          isSelected: _timeFormat == 0,
                          onTap: () => setState(() => _timeFormat = 0),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _buildChoicePill(
                          title: '24 ساعة (14:45)',
                          isSelected: _timeFormat == 1,
                          onTap: () => setState(() => _timeFormat = 1),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Footer note
            Center(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: const BoxDecoration(
                      color: Color(0xFF00E5FF),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    'تمت مزامنة تفضيلات المظهر مع السحابة المركزية • الآن',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Color(0xFF94A3B8),
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

  double _getFontSize() {
    switch (_fontSizeIndex) {
      case 0:
        return 12.0;
      case 2:
        return 16.0;
      case 3:
        return 18.0;
      default:
        return 14.0;
    }
  }

  Widget _buildSectionHeader({required String title, required IconData icon}) {
    return Row(
      children: [
        Icon(icon, size: 18, color: const Color(0xFF006677)),
        const SizedBox(width: 8),
        Text(
          title,
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 13.5,
            fontWeight: FontWeight.bold,
            color: Color(0xFF0F172A),
          ),
        ),
      ],
    );
  }

  Widget _buildThemeCard({
    required int index,
    required String title,
    String? badgeText,
    required bool isActive,
    required Color previewColor,
    required Color borderColor,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isActive ? const Color(0xFF006677) : const Color(0xFFE2E8F0),
              width: isActive ? 2 : 1,
            ),
          ),
          child: Column(
            children: [
              Container(
                height: 48,
                decoration: BoxDecoration(
                  color: previewColor,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: borderColor),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                title,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12,
                  fontWeight: isActive ? FontWeight.bold : FontWeight.w500,
                  color: const Color(0xFF1E293B),
                ),
              ),
              if (badgeText != null) ...[
                const SizedBox(height: 2),
                Text(
                  badgeText,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: isActive
                        ? const Color(0xFF006677)
                        : const Color(0xFF94A3B8),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSettingCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required Widget trailing,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: const Color(0xFF0284C7), size: 20),
          ),
          const SizedBox(width: 12),
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
          trailing,
        ],
      ),
    );
  }

  Widget _buildFontSizeButton({
    required String label,
    required String sub,
    required int idx,
  }) {
    final selected = _fontSizeIndex == idx;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _fontSizeIndex = idx),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF006677) : const Color(0xFFF1F5F9),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            children: [
              Text(
                label,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 10,
                  color: selected ? Colors.white : const Color(0xFF64748B),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                sub,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: selected ? Colors.white : const Color(0xFF1E293B),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLanguageCard({
    required String title,
    String? subtitle,
    required String badge,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? const Color(0xFF006677) : const Color(0xFFE2E8F0),
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: const Color(0xFFF1F5F9),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: Text(
                  badge,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF006677),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF1E293B),
                    ),
                  ),
                  if (subtitle != null)
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
            if (isSelected)
              const Icon(Icons.check_circle_rounded,
                  color: Color(0xFF006677), size: 20)
            else
              Container(
                width: 20,
                height: 20,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFCBD5E1)),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildChoicePill({
    required String title,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 40,
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF006677) : const Color(0xFFF1F5F9),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Center(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (isSelected) ...[
                const Icon(Icons.check_rounded, color: Colors.white, size: 16),
                const SizedBox(width: 4),
              ],
              Text(
                title,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: isSelected ? Colors.white : const Color(0xFF475569),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
