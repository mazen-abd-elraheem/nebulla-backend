import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'face_registration_screen.dart';

class Security2FAScreen extends StatefulWidget {
  const Security2FAScreen({super.key});

  @override
  State<Security2FAScreen> createState() => _Security2FAScreenState();
}

class _Security2FAScreenState extends State<Security2FAScreen> {
  final _repo = NebulaRepository.instance;

  bool _isLoading = true;
  bool _twoFactorEnabled = true;
  bool _biometricEnabled = true;
  bool _hasBiometric = false;
  bool _isSaving = false;
  List<String> _backupCodes = [];
  DateTime? _passwordUpdatedAt;
  List<SecuritySessionItem> _sessions = [];

  @override
  void initState() {
    super.initState();
    _sessions = [_buildLocalDeviceSession()];
    _loadSecuritySettings();
  }

  SecuritySessionItem _buildLocalDeviceSession() {
    if (kIsWeb) {
      return SecuritySessionItem(
        id: 'local_web',
        deviceName: 'متصفح الويب (هذا الجهاز)',
        platform: 'تطبيق الويب • متصل بالخادم',
        deviceType: 'web',
        isCurrent: true,
        statusLabel: 'نشط الآن',
      );
    }
    if (Platform.isWindows) {
      return SecuritySessionItem(
        id: 'local_windows',
        deviceName: 'جهاز الكمبيوتر (هذا الجهاز)',
        platform: 'ويندوز / تطبيق سطح المكتب • متصل بالخادم',
        deviceType: 'desktop',
        isCurrent: true,
        statusLabel: 'نشط الآن',
      );
    }
    if (Platform.isMacOS) {
      return SecuritySessionItem(
        id: 'local_macos',
        deviceName: 'جهاز Mac (هذا الجهاز)',
        platform: 'macOS / تطبيق سطح المكتب • متصل بالخادم',
        deviceType: 'desktop',
        isCurrent: true,
        statusLabel: 'نشط الآن',
      );
    }
    if (Platform.isLinux) {
      return SecuritySessionItem(
        id: 'local_linux',
        deviceName: 'جهاز الكمبيوتر (هذا الجهاز)',
        platform: 'لينكس / تطبيق سطح المكتب • متصل بالخادم',
        deviceType: 'desktop',
        isCurrent: true,
        statusLabel: 'نشط الآن',
      );
    }
    if (Platform.isIOS) {
      return SecuritySessionItem(
        id: 'local_ios',
        deviceName: 'جهاز الآيفون (هذا الجهاز)',
        platform: 'iOS • متصل بالخادم',
        deviceType: 'mobile',
        isCurrent: true,
        statusLabel: 'نشط الآن',
      );
    }
    return SecuritySessionItem(
      id: 'local_android',
      deviceName: 'الجهاز المحمول (هذا الجهاز)',
      platform: 'أندرويد • متصل بالخادم',
      deviceType: 'mobile',
      isCurrent: true,
      statusLabel: 'نشط الآن',
    );
  }

  Future<void> _loadSecuritySettings() async {
    try {
      final data = await _repo.getSecuritySettings();
      if (!mounted) return;
      setState(() {
        _twoFactorEnabled = data.twoFactorEnabled;
        _biometricEnabled = data.biometricEnabled;
        _hasBiometric = data.hasBiometric;
        _backupCodes = data.backupCodes;
        _passwordUpdatedAt = data.passwordUpdatedAt;
        _sessions = data.activeSessions.isNotEmpty
            ? data.activeSessions
            : [_buildLocalDeviceSession()];
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _sessions = [_buildLocalDeviceSession()];
        _isLoading = false;
      });
    }
  }

  String _formatPasswordLastUpdated() {
    if (_passwordUpdatedAt == null) {
      return 'مؤمّنة ومشفّرة بالكامل';
    }
    final diff = DateTime.now().difference(_passwordUpdatedAt!.toLocal());
    if (diff.inMinutes < 2) {
      return 'آخر تحديث: الآن';
    }
    if (diff.inHours < 1) {
      return 'آخر تحديث: منذ ${diff.inMinutes} دقيقة';
    }
    if (diff.inDays < 1) {
      return 'آخر تحديث: اليوم';
    }
    if (diff.inDays == 1) {
      return 'آخر تحديث: منذ يوم واحد';
    }
    return 'آخر تحديث: قبل ${diff.inDays} يوماً';
  }

  String _getSecurityLevelKey() {
    if (_twoFactorEnabled && _biometricEnabled) return 'high';
    if (_twoFactorEnabled || _biometricEnabled) return 'medium';
    return 'basic';
  }

  IconData _sessionIcon(String deviceType) {
    switch (deviceType) {
      case 'mobile':
        return Icons.phone_android_rounded;
      case 'robot':
        return Icons.memory_rounded;
      case 'web':
        return Icons.language_rounded;
      case 'desktop':
      default:
        return Icons.laptop_windows_rounded;
    }
  }

  Future<void> _toggleTwoFactor(bool val) async {
    setState(() => _twoFactorEnabled = val);
    try {
      final updated = await _repo.updateSecuritySettings(
        twoFactorEnabled: val,
      );
      if (!mounted) return;
      setState(() {
        _twoFactorEnabled = updated.twoFactorEnabled;
        _biometricEnabled = updated.biometricEnabled;
        _backupCodes = updated.backupCodes;
      });
      showSuccessSnackbar(
        context,
        val
            ? 'تم تفعيل التحقق بخطوتين وحفظه بنجاح.'
            : 'تم إيقاف التحقق بخطوتين.',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _twoFactorEnabled = !val);
      final msg = e is ApiException ? e.message : 'تعذر الاتصال بالخادم';
      showErrorSnackbar(context, msg);
    }
  }

  Future<void> _toggleBiometric(bool val) async {
    setState(() => _biometricEnabled = val);
    try {
      final updated = await _repo.updateSecuritySettings(
        biometricEnabled: val,
      );
      if (!mounted) return;
      setState(() {
        _biometricEnabled = updated.biometricEnabled;
        _hasBiometric = updated.hasBiometric;
      });
      showSuccessSnackbar(
        context,
        val
            ? 'تم تفعيل بصمة الإصبع والوجه بنجاح.'
            : 'تم إيقاف التحقق بالبصمة والوجه.',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _biometricEnabled = !val);
      final msg = e is ApiException ? e.message : 'تعذر الاتصال بالخادم';
      showErrorSnackbar(context, msg);
    }
  }

  void _showBackupCodesDialog() {
    bool regenerating = false;
    List<String> localCodes = List<String>.from(_backupCodes);

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            backgroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(22),
            ),
            title: const Row(
              children: [
                Icon(Icons.key_rounded, color: Color(0xFF006677), size: 22),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'مفاتيح الأمان ورموز الاحتياط',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                ),
              ],
            ),
            content: SizedBox(
              width: 340,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'احتفظ بهذه الرموز في مكان آمن لاستعادة حسابك عند الحاجة. اضغط على أي رمز لنسخه:',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 12,
                      color: Color(0xFF475569),
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (localCodes.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 16),
                      child: Center(
                        child: Text(
                          'اضغط "توليد رموز جديدة" لإنشاء رموز أمان احتياطية.',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12,
                            color: Color(0xFF64748B),
                          ),
                        ),
                      ),
                    )
                  else
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: localCodes.map((code) {
                        return InkWell(
                          onTap: () {
                            Clipboard.setData(ClipboardData(text: code));
                            showSuccessSnackbar(context, 'تم نسخ الرمز: $code');
                          },
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            width: 150,
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: const Color(0xFFCBD5E1),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  code,
                                  style: const TextStyle(
                                    fontFamily: 'monospace',
                                    fontSize: 13,
                                    fontWeight: FontWeight.bold,
                                    color: Color(0xFF0F172A),
                                    letterSpacing: 1.0,
                                  ),
                                ),
                                const Icon(
                                  Icons.copy_rounded,
                                  size: 14,
                                  color: Color(0xFF006677),
                                ),
                              ],
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: localCodes.isEmpty
                              ? null
                              : () {
                                  Clipboard.setData(
                                    ClipboardData(text: localCodes.join('\n')),
                                  );
                                  showSuccessSnackbar(
                                    context,
                                    'تم نسخ جميع رموز الاحتياط بنجاح.',
                                  );
                                },
                          icon: const Icon(Icons.copy_all_rounded, size: 16),
                          label: const Text(
                            'نسخ الكل',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFF006677),
                            side: const BorderSide(color: Color(0xFF006677)),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: regenerating
                              ? null
                              : () async {
                                  setDialogState(() => regenerating = true);
                                  try {
                                    final updated =
                                        await _repo.regenerateBackupCodes();
                                    if (!mounted) return;
                                    setState(() {
                                      _backupCodes = updated.backupCodes;
                                    });
                                    setDialogState(() {
                                      localCodes = List<String>.from(
                                        updated.backupCodes,
                                      );
                                      regenerating = false;
                                    });
                                    showSuccessSnackbar(
                                      context,
                                      'تم توليد رموز أمان جديدة وحفظها بنجاح!',
                                    );
                                  } catch (e) {
                                    setDialogState(() => regenerating = false);
                                    if (!mounted) return;
                                    final msg = e is ApiException
                                        ? e.message
                                        : 'تعذر توليد الرموز';
                                    showErrorSnackbar(context, msg);
                                  }
                                },
                          icon: regenerating
                              ? const SizedBox(
                                  width: 14,
                                  height: 14,
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.refresh_rounded, size: 16),
                          label: const Text(
                            'توليد جديد',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF006677),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
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
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text(
                  'إغلاق',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF006677),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showChangePasswordDialog() {
    final currentPassCtrl = TextEditingController();
    final newPassCtrl = TextEditingController();
    final confirmPassCtrl = TextEditingController();
    bool obscureCurrent = true;
    bool obscureNew = true;
    bool obscureConfirm = true;
    bool submitting = false;
    String? inlineError;

    const passFieldStyle = TextStyle(
      fontFamily: 'Cairo',
      fontSize: 14,
      fontWeight: FontWeight.w700,
      color: Color(0xFF0F172A),
    );

    showDialog(
      context: context,
      builder: (ctx) => Theme(
        data: ThemeData.light().copyWith(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF006677),
            brightness: Brightness.light,
          ),
        ),
        child: StatefulBuilder(
          builder: (ctx, setDialogState) => Directionality(
            textDirection: TextDirection.rtl,
            child: AlertDialog(
              backgroundColor: Colors.white,
              surfaceTintColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(22),
              ),
              title: const Text(
                'تحديث كلمة المرور',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextField(
                      controller: currentPassCtrl,
                      obscureText: obscureCurrent,
                      style: passFieldStyle,
                      cursorColor: const Color(0xFF006677),
                      decoration: InputDecoration(
                        labelText: 'كلمة المرور الحالية',
                        labelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        suffixIcon: IconButton(
                          icon: Icon(
                            obscureCurrent
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                            size: 18,
                            color: const Color(0xFF475569),
                          ),
                          onPressed: () => setDialogState(
                            () => obscureCurrent = !obscureCurrent,
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFFCBD5E1), width: 1.2),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFF006677), width: 1.6),
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: newPassCtrl,
                      obscureText: obscureNew,
                      style: passFieldStyle,
                      cursorColor: const Color(0xFF006677),
                      decoration: InputDecoration(
                        labelText: 'كلمة المرور الجديدة',
                        labelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        suffixIcon: IconButton(
                          icon: Icon(
                            obscureNew
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                            size: 18,
                            color: const Color(0xFF475569),
                          ),
                          onPressed: () =>
                              setDialogState(() => obscureNew = !obscureNew),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFFCBD5E1), width: 1.2),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFF006677), width: 1.6),
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: confirmPassCtrl,
                      obscureText: obscureConfirm,
                      style: passFieldStyle,
                      cursorColor: const Color(0xFF006677),
                      decoration: InputDecoration(
                        labelText: 'تأكيد كلمة المرور الجديدة',
                        labelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        suffixIcon: IconButton(
                          icon: Icon(
                            obscureConfirm
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                            size: 18,
                            color: const Color(0xFF475569),
                          ),
                          onPressed: () => setDialogState(
                            () => obscureConfirm = !obscureConfirm,
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFFCBD5E1), width: 1.2),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: Color(0xFF006677), width: 1.6),
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ),
                  if (inlineError != null) ...[
                    const SizedBox(height: 10),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF2F2),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFFECACA)),
                      ),
                      child: Text(
                        inlineError!,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11.5,
                          color: Color(0xFFDC2626),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
              actions: [
                TextButton(
                  onPressed: submitting ? null : () => Navigator.of(ctx).pop(),
                  child: const Text(
                    'إلغاء',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF475569),
                    ),
                  ),
                ),
              ElevatedButton(
                onPressed: submitting
                    ? null
                    : () async {
                        final curr = currentPassCtrl.text.trim();
                        final next = newPassCtrl.text.trim();
                        final conf = confirmPassCtrl.text.trim();

                        if (curr.isEmpty || next.isEmpty || conf.isEmpty) {
                          setDialogState(
                            () => inlineError = 'يرجى ملء جميع الحقول.',
                          );
                          return;
                        }
                        if (next.length < 6) {
                          setDialogState(
                            () => inlineError =
                                'كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل.',
                          );
                          return;
                        }
                        if (next != conf) {
                          setDialogState(
                            () => inlineError =
                                'كلمة المرور الجديدة وتأكيدها غير متطابقين.',
                          );
                          return;
                        }

                        setDialogState(() {
                          submitting = true;
                          inlineError = null;
                        });

                        try {
                          final msg = await _repo.changePassword(
                            currentPassword: curr,
                            newPassword: next,
                            confirmPassword: conf,
                          );
                          if (!mounted) return;
                          setState(() {
                            _passwordUpdatedAt = DateTime.now();
                          });
                          if (ctx.mounted) Navigator.of(ctx).pop();
                          showSuccessSnackbar(context, msg);
                        } catch (e) {
                          final errMsg = e is ApiException
                              ? e.message
                              : 'تعذر تحديث كلمة المرور، حاول مرة أخرى.';
                          setDialogState(() {
                            submitting = false;
                            inlineError = errMsg;
                          });
                        }
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF006677),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: submitting
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2,
                        ),
                      )
                    : const Text(
                        'حفظ',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          color: Colors.white,
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }

  Future<void> _saveSettings() async {
    setState(() => _isSaving = true);
    try {
      final updated = await _repo.updateSecuritySettings(
        twoFactorEnabled: _twoFactorEnabled,
        biometricEnabled: _biometricEnabled,
      );
      if (!mounted) return;
      setState(() {
        _twoFactorEnabled = updated.twoFactorEnabled;
        _biometricEnabled = updated.biometricEnabled;
        _hasBiometric = updated.hasBiometric;
        _backupCodes = updated.backupCodes;
        _passwordUpdatedAt = updated.passwordUpdatedAt;
        if (updated.activeSessions.isNotEmpty) {
          _sessions = updated.activeSessions;
        }
        _isSaving = false;
      });
      showSuccessSnackbar(context, 'تم حفظ إعدادات الأمان في الخادم بنجاح!');
    } catch (e) {
      if (!mounted) return;
      setState(() => _isSaving = false);
      final msg =
          e is ApiException ? e.message : 'تعذر حفظ إعدادات الأمان في الخادم.';
      showErrorSnackbar(context, msg);
    }
  }

  Widget _buildProtectionBanner() {
    final level = _getSecurityLevelKey();
    final Color bgColor;
    final Color fgColor;
    final IconData icon;
    final String text;

    if (level == 'high') {
      bgColor = const Color(0xFFCCFBF1);
      fgColor = const Color(0xFF006677);
      icon = Icons.check_circle_rounded;
      text = 'مستوى الحماية الحالي: مرتفع ومؤمّن بالكامل';
    } else if (level == 'medium') {
      bgColor = const Color(0xFFFEF3C7);
      fgColor = const Color(0xFFB45309);
      icon = Icons.shield_outlined;
      text = 'مستوى الحماية الحالي: متوسط — يُنصح بتفعيل كل الوسائل';
    } else {
      bgColor = const Color(0xFFFEE2E2);
      fgColor = const Color(0xFFB91C1C);
      icon = Icons.warning_amber_rounded;
      text = 'مستوى الحماية الحالي: أساسي — فعّل التحقق لحماية حسابك';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 16, color: fgColor),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11.5,
                fontWeight: FontWeight.bold,
                color: fgColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final topCardBg = _twoFactorEnabled
        ? const Color(0xFFF0FDF4)
        : const Color(0xFFFFFBEB);
    final topCardBorder = _twoFactorEnabled
        ? const Color(0xFFBBF7D0)
        : const Color(0xFFFDE68A);

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        appBar: AppBar(
          backgroundColor: Colors.white,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(
              Icons.close_rounded,
              color: Color(0xFF1E293B),
              size: 22,
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F7FA),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.verified_user_rounded,
                  size: 18,
                  color: Color(0xFF006677),
                ),
              ),
              const SizedBox(width: 8),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'الأمان والتحقق بخطوتين',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    'إدارة وسائل الحماية والجلسات النشطة',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10.5,
                      color: Color(0xFF64748B),
                    ),
                  ),
                ],
              ),
            ],
          ),
          centerTitle: true,
        ),
        body: _isLoading
            ? const Center(
                child: CircularProgressIndicator(color: Color(0xFF006677)),
              )
            : RefreshIndicator(
                onRefresh: _loadSecuritySettings,
                color: const Color(0xFF006677),
                child: ListView(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  children: [
                    // 1. Top 2FA Card
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: topCardBg,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: topCardBorder),
                      ),
                      child: Column(
                        children: [
                          Row(
                            children: [
                              Switch(
                                value: _twoFactorEnabled,
                                onChanged: _toggleTwoFactor,
                                activeThumbColor: const Color(0xFF006677),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Row(
                                      children: [
                                        Text(
                                          'التحقق بخطوتين',
                                          style: TextStyle(
                                            fontFamily: 'Cairo',
                                            fontSize: 14,
                                            fontWeight: FontWeight.bold,
                                            color: Color(0xFF0F172A),
                                          ),
                                        ),
                                        SizedBox(width: 6),
                                        Icon(
                                          Icons.shield_rounded,
                                          size: 16,
                                          color: Color(0xFF006677),
                                        ),
                                      ],
                                    ),
                                    Text(
                                      _twoFactorEnabled
                                          ? 'تطبيق المصادقة نشط ومفعّل لحماية حسابك'
                                          : 'التحقق بخطوتين غير مفعّل حالياً',
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 11,
                                        color: Color(0xFF475569),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          _buildProtectionBanner(),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),

                    // 2. Section: طرق التحقق الإضافية
                    const Text(
                      'طرق التحقق الإضافية',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 10),

                    // Biometrics Card
                    InkWell(
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const FaceRegistrationScreen(),
                          ),
                        );
                        _loadSecuritySettings();
                      },
                      borderRadius: BorderRadius.circular(18),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 12,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: const Color(0xFFE2E8F0)),
                        ),
                        child: Row(
                          children: [
                            Switch(
                              value: _biometricEnabled,
                              onChanged: _toggleBiometric,
                              activeThumbColor: const Color(0xFF006677),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'بصمة الإصبع والوجه',
                                    style: TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF1E293B),
                                    ),
                                  ),
                                  Text(
                                    _hasBiometric
                                        ? 'بصمة الوجه مسجّلة ومشفّرة (اضغط للتحديث)'
                                        : 'دخول سريع ومشفّر عبر أجهزة موثوقة (اضغط لتسجيل الوجه)',
                                    style: const TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 11,
                                      color: Color(0xFF64748B),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Container(
                              width: 38,
                              height: 38,
                              decoration: BoxDecoration(
                                color: const Color(0xFFE0F7FA),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(
                                Icons.fingerprint_rounded,
                                color: Color(0xFF006677),
                                size: 20,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),

                    // Security Keys Card
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: Row(
                        children: [
                          ElevatedButton(
                            onPressed: _showBackupCodesDialog,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFFF1F5F9),
                              foregroundColor: const Color(0xFF006677),
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 6,
                              ),
                            ),
                            child: const Text(
                              'إدارة',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          const Spacer(),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text(
                                'مفاتيح الأمان ورموز الاحتياط',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF1E293B),
                                ),
                              ),
                              Text(
                                _backupCodes.isNotEmpty
                                    ? '${_backupCodes.length} رموز استعادة جاهزة للاستخدام'
                                    : 'اضغط إدارة لعرض أو توليد رموز الاحتياط',
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
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.key_rounded,
                              color: Color(0xFF006677),
                              size: 20,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),

                    // 3. Section: الجلسات والأجهزة النشطة
                    const Text(
                      'الجلسات والأجهزة النشطة',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 10),
                    ..._sessions.map(
                      (session) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 12,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: const Color(0xFFE2E8F0)),
                        ),
                        child: Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 4,
                              ),
                              decoration: BoxDecoration(
                                color: session.isCurrent
                                    ? const Color(0xFF006677)
                                    : const Color(0xFF10B981),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                session.statusLabel,
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 10.5,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(
                                    session.deviceName,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF1E293B),
                                    ),
                                  ),
                                  Text(
                                    session.platform,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
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
                                color: const Color(0xFFF1F5F9),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Icon(
                                _sessionIcon(session.deviceType),
                                color: const Color(0xFF006677),
                                size: 20,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),

                    // 4. Section: كلمة المرور
                    const Text(
                      'كلمة المرور',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: Row(
                        children: [
                          ElevatedButton(
                            onPressed: _showChangePasswordDialog,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFFF1F5F9),
                              foregroundColor: const Color(0xFF006677),
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 6,
                              ),
                            ),
                            child: const Text(
                              'تغيير',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          const Spacer(),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text(
                                'تحديث كلمة المرور',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF1E293B),
                                ),
                              ),
                              Text(
                                _formatPasswordLastUpdated(),
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
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.password_rounded,
                              color: Color(0xFF006677),
                              size: 20,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),

                    // Bottom Save Action Button
                    GestureDetector(
                      onTap: _isSaving ? null : _saveSettings,
                      child: Container(
                        height: 52,
                        decoration: BoxDecoration(
                          color: const Color(0xFF006677),
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF006677)
                                  .withValues(alpha: 0.25),
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
                                    Icon(
                                      Icons.save_rounded,
                                      color: Colors.white,
                                      size: 20,
                                    ),
                                    SizedBox(width: 8),
                                    Text(
                                      'حفظ إعدادات الأمان',
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
                    const SizedBox(height: 24),
                  ],
                ),
              ),
      ),
    );
  }
}
