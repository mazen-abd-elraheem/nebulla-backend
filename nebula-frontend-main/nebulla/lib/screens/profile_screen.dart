import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/api_service.dart';
import '../services/avatar_audio_service.dart';
import '../services/storage_service.dart';
import '../services/locale_service.dart';
import '../services/nebula_repository.dart';
import '../utils/avatar_photo_picker.dart';
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
  bool _uploadingAvatar = false;
  String _fullName = 'المستخدم';
  String _email = 'user@nebula.local';
  String _phone = '+20 10 1234 5678';
  String _location = 'القاهرة، مصر';
  String _organization = 'فريق أبحاث نيبولا للذكاء الاصطناعي';
  String _joinDate = 'مارس 2024';

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
        if (user.phone != null && user.phone!.isNotEmpty) _phone = user.phone!;
        if (user.location != null && user.location!.isNotEmpty) _location = user.location!;
        if (user.organization != null && user.organization!.isNotEmpty) _organization = user.organization!;
        if (user.createdAt != null && user.createdAt!.isNotEmpty) _joinDate = user.createdAt!;
      });
    }
    // Fetch live fresh profile from backend
    NebulaRepository.instance.getMe().then((remoteUser) {
      if (mounted) {
        setState(() {
          if (remoteUser.fullName.isNotEmpty) _fullName = remoteUser.fullName;
          if (remoteUser.email.isNotEmpty) _email = remoteUser.email;
          if (remoteUser.phone != null && remoteUser.phone!.isNotEmpty) _phone = remoteUser.phone!;
          if (remoteUser.location != null && remoteUser.location!.isNotEmpty) _location = remoteUser.location!;
          if (remoteUser.organization != null && remoteUser.organization!.isNotEmpty) _organization = remoteUser.organization!;
        });
      }
    }).catchError((_) {});
  }

  Widget _buildProfileAvatar() {
    final avatarUrl = StorageService.instance.getUserAvatarUrl();
    final avatarPath = StorageService.instance.getUserAvatarPath();

    if (avatarUrl != null && avatarUrl.isNotEmpty) {
      final base = StorageService.instance.getBaseUrl();
      final fullUrl = avatarUrl.startsWith('http') ? avatarUrl : '$base$avatarUrl';
      return Image.network(
        fullUrl,
        fit: BoxFit.cover,
        alignment: Alignment.center,
        errorBuilder: (context, error, stackTrace) => _profileInitialFallback(),
      );
    } else if (avatarPath != null && File(avatarPath).existsSync()) {
      return Image.file(
        File(avatarPath),
        fit: BoxFit.cover,
        alignment: Alignment.center,
        errorBuilder: (_, _, _) => _profileInitialFallback(),
      );
    } else {
      return _profileInitialFallback();
    }
  }

  Widget _profileInitialFallback() {
    final initial = _fullName.trim().isNotEmpty ? _fullName.trim()[0].toUpperCase() : 'U';
    return Container(
      color: const Color(0xFFE0F2FE),
      child: Center(
        child: Text(
          initial,
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 34,
            fontWeight: FontWeight.bold,
            color: Color(0xFF006677),
          ),
        ),
      ),
    );
  }

  Future<void> _showChangeAvatarSheet() async {
    final t = LocaleService.instance.tr;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE2E8F0),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  t('تغيير الصورة الشخصية والأفاتار', 'Change Profile Photo & Avatar'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  t(
                    'سيتم إرسال صورتك إلى الخادم وتحويلها لأفاتار ناطق متفاعل على الصفحة الرئيسية',
                    'Your photo will be sent to the backend and converted to your speaking avatar on the Home screen',
                  ),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: Color(0xFF64748B),
                  ),
                ),
                const SizedBox(height: 18),
                ListTile(
                  leading: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFECFEFF),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.camera_alt_rounded,
                      color: Color(0xFF00B4D8),
                    ),
                  ),
                  title: Text(
                    t('التقاط بالكاميرا', 'Take Photo with Camera'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    _pickAndUploadAvatar(preferCamera: true);
                  },
                ),
                ListTile(
                  leading: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEFF6FF),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.photo_library_rounded,
                      color: Color(0xFF3B82F6),
                    ),
                  ),
                  title: Text(
                    t('اختيار من المعرض', 'Choose from Gallery'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    _pickAndUploadAvatar(preferCamera: false);
                  },
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _pickAndUploadAvatar({bool preferCamera = false}) async {
    try {
      final file = await pickAvatarPhotoFile(preferCamera: preferCamera);
      if (file == null || !mounted) return;
      setState(() => _uploadingAvatar = true);

      try {
        await NebulaRepository.instance.generateAvatar(file);
        await StorageService.instance.setUserAvatarPath(file.path);
        await AvatarAudioService.instance.loadActiveAvatar(force: true);
        if (!mounted) return;
        setState(() => _uploadingAvatar = false);
        showSuccessSnackbar(
          context,
          LocaleService.instance.tr(
            'تم تحويل صورتك إلى أفاتار ناطق وتحديث ملفك بنجاح ✨',
            'Your photo was transformed into your speaking avatar ✨',
          ),
        );
      } catch (e) {
        if (!mounted) return;
        setState(() => _uploadingAvatar = false);
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر تحويل الصورة إلى أفاتار، يرجى المحاولة مرة أخرى.',
            'Could not transform photo into avatar. Please try again.',
          ),
        );
      }
    } catch (_) {
      if (mounted) setState(() => _uploadingAvatar = false);
    }
  }

  String _tr(String ar, String en) => LocaleService.instance.tr(ar, en);

  void _showEditProfileDialog({String? focusField}) {
    final nameCtrl = TextEditingController(text: _fullName);
    final emailCtrl = TextEditingController(text: _email);
    final phoneCtrl = TextEditingController(text: _phone);
    final locationCtrl = TextEditingController(text: _location);
    final orgCtrl = TextEditingController(text: _organization);
    bool saving = false;
    String? nameError;
    String? emailError;
    String? generalError;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) {
          nameCtrl.addListener(() {
            if (nameError != null) setDialogState(() => nameError = null);
            if (generalError != null) setDialogState(() => generalError = null);
          });
          emailCtrl.addListener(() {
            if (emailError != null) setDialogState(() => emailError = null);
            if (generalError != null) setDialogState(() => generalError = null);
          });

          return Directionality(
            textDirection: LocaleService.instance.textDirection,
            child: AlertDialog(
              backgroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
              title: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE0F2FE),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.edit_rounded, color: Color(0xFF00B4D8), size: 18),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    _tr('تعديل البيانات الشخصية', 'Edit Personal Info'),
                    style: const TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold, fontSize: 16, color: Color(0xFF0F172A)),
                  ),
                ],
              ),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (nameError != null) ...[
                      InlineFieldError(message: nameError!),
                      const SizedBox(height: 6),
                    ],
                    TextField(
                      controller: nameCtrl,
                      autofocus: focusField == 'name',
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      decoration: InputDecoration(
                        labelText: _tr('الاسم الكامل', 'Full Name'),
                        labelStyle: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF475569)),
                        prefixIcon: const Icon(Icons.person_outline_rounded, color: Color(0xFF00B4D8)),
                        filled: true,
                        fillColor: nameError != null ? const Color(0xFFFFF5F5) : const Color(0xFFF8FAFC),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: nameError != null ? const Color(0xFFEF4444) : const Color(0xFFE2E8F0))),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: nameError != null ? const Color(0xFFEF4444) : const Color(0xFF00B4D8), width: 1.5)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (emailError != null) ...[
                      InlineFieldError(message: emailError!),
                      const SizedBox(height: 6),
                    ],
                    TextField(
                      controller: emailCtrl,
                      keyboardType: TextInputType.emailAddress,
                      autofocus: focusField == 'email',
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      decoration: InputDecoration(
                        labelText: _tr('البريد الإلكتروني', 'Email Address'),
                        labelStyle: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF475569)),
                        prefixIcon: const Icon(Icons.alternate_email_rounded, color: Color(0xFF00B4D8)),
                        filled: true,
                        fillColor: emailError != null ? const Color(0xFFFFF5F5) : const Color(0xFFF8FAFC),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: emailError != null ? const Color(0xFFEF4444) : const Color(0xFFE2E8F0))),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: emailError != null ? const Color(0xFFEF4444) : const Color(0xFF00B4D8), width: 1.5)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: phoneCtrl,
                      keyboardType: TextInputType.phone,
                      textDirection: TextDirection.ltr,
                      autofocus: focusField == 'phone',
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      decoration: InputDecoration(
                        labelText: _tr('رقم الهاتف', 'Phone Number'),
                        labelStyle: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF475569)),
                        prefixIcon: const Icon(Icons.phone_outlined, color: Color(0xFF00B4D8)),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFF00B4D8), width: 1.5)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: locationCtrl,
                      autofocus: focusField == 'location',
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      decoration: InputDecoration(
                        labelText: _tr('الموقع الجغرافي', 'Location'),
                        labelStyle: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF475569)),
                        prefixIcon: const Icon(Icons.location_on_outlined, color: Color(0xFF00B4D8)),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFF00B4D8), width: 1.5)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: orgCtrl,
                      autofocus: focusField == 'org',
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      decoration: InputDecoration(
                        labelText: _tr('المؤسسة والجهة', 'Organization'),
                        labelStyle: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF475569)),
                        prefixIcon: const Icon(Icons.domain_rounded, color: Color(0xFF00B4D8)),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Color(0xFF00B4D8), width: 1.5)),
                      ),
                    ),
                    if (generalError != null) ...[
                      const SizedBox(height: 12),
                      InlineFieldError(message: generalError!),
                    ],
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: Text(_tr('إلغاء', 'Cancel'), style: const TextStyle(fontFamily: 'Cairo', color: Color(0xFF64748B))),
                ),
                ElevatedButton(
                  onPressed: saving
                      ? null
                      : () async {
                          final name = nameCtrl.text.trim();
                          final email = emailCtrl.text.trim();

                          String? nErr;
                          String? eErr;

                          if (name.isEmpty) {
                            nErr = _tr('يرجى إدخال الاسم بالكامل', 'Please enter your name');
                          }

                          final emailRegex = RegExp(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$');
                          if (email.isEmpty) {
                            eErr = _tr('يرجى إدخال البريد الإلكتروني', 'Please enter your email');
                          } else if (!emailRegex.hasMatch(email)) {
                            eErr = _tr('صيغة البريد الإلكتروني غير صحيحة', 'Invalid email format');
                          }

                          if (nErr != null || eErr != null) {
                            setDialogState(() {
                              nameError = nErr;
                              emailError = eErr;
                              generalError = null;
                            });
                            return;
                          }

                          setDialogState(() {
                            saving = true;
                            nameError = null;
                            emailError = null;
                            generalError = null;
                          });

                          try {
                            final updatedUser = await NebulaRepository.instance.updateProfile(
                              fullName: name,
                              email: email,
                              phone: phoneCtrl.text.trim(),
                              location: locationCtrl.text.trim(),
                              organization: orgCtrl.text.trim(),
                            );
                            if (mounted) {
                              setState(() {
                                _fullName = updatedUser.fullName;
                                _email = updatedUser.email;
                                if (updatedUser.phone != null) _phone = updatedUser.phone!;
                                if (updatedUser.location != null) _location = updatedUser.location!;
                                if (updatedUser.organization != null) _organization = updatedUser.organization!;
                              });
                              if (ctx.mounted) Navigator.of(ctx).pop();
                              showSuccessSnackbar(
                                context,
                                _tr('تم حفظ وتحديث بياناتك بنجاح ✨', 'Profile updated successfully ✨'),
                              );
                            }
                          } catch (e) {
                            setDialogState(() => saving = false);
                            final msg = e is ApiException ? e.message : e.toString();
                            final lower = msg.toLowerCase();

                            if (lower.contains('email') ||
                                lower.contains('بريد') ||
                                lower.contains('already') ||
                                lower.contains('exists') ||
                                lower.contains('taken') ||
                                lower.contains('مسجل') ||
                                lower.contains('موجود')) {
                              setDialogState(() {
                                emailError = _tr('هذا البريد الإلكتروني مسجل مسبقاً، يرجى استخدام بريد آخر.', 'This email is already in use.');
                              });
                              return;
                            }

                            setDialogState(() {
                              generalError = _tr('تعذر حفظ البيانات حالياً، يرجى المحاولة مرة أخرى.', 'Could not save profile. Please try again.');
                            });
                          }
                        },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF00B4D8),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: saving
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : Text(_tr('حفظ في السيرفر', 'Save Changes'), style: const TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          );
        },
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
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 20,
                              fontWeight: FontWeight.w900,
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
                        GestureDetector(
                          onTap: _uploadingAvatar ? null : _showChangeAvatarSheet,
                          child: Container(
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
                              child: _uploadingAvatar
                                  ? const Center(
                                      child: SizedBox(
                                        width: 24,
                                        height: 24,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2.5,
                                          color: Color(0xFF00B4D8),
                                        ),
                                      ),
                                    )
                                  : _buildProfileAvatar(),
                            ),
                          ),
                        ),
                        // Camera upload badge button
                        Positioned(
                          bottom: -2,
                          right: -2,
                          child: GestureDetector(
                            onTap: _uploadingAvatar ? null : _showChangeAvatarSheet,
                            child: Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: const Color(0xFF00B4D8),
                                shape: BoxShape.circle,
                                border: Border.all(color: Colors.white, width: 2),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.15),
                                    blurRadius: 4,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: const Icon(
                                Icons.camera_alt_rounded,
                                size: 14,
                                color: Colors.white,
                              ),
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
                        const SizedBox(width: 8),
                        InkWell(
                          onTap: () => _showEditProfileDialog(focusField: 'name'),
                          borderRadius: BorderRadius.circular(8),
                          child: Container(
                            padding: const EdgeInsets.all(5),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE0F2FE),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: const Color(0xFFBAE6FD)),
                            ),
                            child: const Icon(
                              Icons.edit_rounded,
                              size: 15,
                              color: Color(0xFF0284C7),
                            ),
                          ),
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
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.edit_outlined,
                                color: Colors.white, size: 16),
                            const SizedBox(width: 6),
                            Text(
                              _tr('تعديل البيانات', 'Edit Profile'),
                              style: const TextStyle(
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
                          context,
                          _tr(
                            'تم نسخ بيانات الملف الشخصي إلى الحافظة.',
                            'Profile info copied to clipboard.',
                          ),
                        );
                      },
                      child: Container(
                        height: 44,
                        decoration: BoxDecoration(
                          color: const Color(0xFFEEF2FF),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.share_outlined,
                                color: Color(0xFF4F46E5), size: 16),
                            const SizedBox(width: 6),
                            Text(
                              _tr('مشاركة الملف', 'Share Profile'),
                              style: const TextStyle(
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

              // 4. Section: معلومات الاتصال والجهة
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    _tr('معلومات الاتصال والجهة', 'Contact & Organization'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 14.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    _tr('المعلومات الأساسية', 'Basic Info'),
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
                    _buildInfoItem(
                      label: _tr('البريد الإلكتروني', 'Email Address'),
                      value: _email,
                      icon: Icons.alternate_email_rounded,
                      badge: _tr('مؤكد', 'Verified'),
                      onEdit: () => _showEditProfileDialog(focusField: 'email'),
                      onCopy: () {
                        Clipboard.setData(ClipboardData(text: _email));
                        showSuccessSnackbar(
                          context,
                          _tr('تم نسخ البريد الإلكتروني.', 'Email copied.'),
                        );
                      },
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    _buildInfoItem(
                      label: _tr('رقم الهاتف', 'Phone Number'),
                      value: _phone,
                      subValue: _tr('رئيسي', 'Primary'),
                      icon: Icons.phone_outlined,
                      onEdit: () => _showEditProfileDialog(focusField: 'phone'),
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    _buildInfoItem(
                      label: _tr('الموقع الجغرافي', 'Location'),
                      value: _location,
                      icon: Icons.location_on_outlined,
                      onEdit: () => _showEditProfileDialog(focusField: 'location'),
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    _buildInfoItem(
                      label: _tr('المؤسسة والجهة', 'Organization'),
                      value: _organization,
                      icon: Icons.domain_rounded,
                      onEdit: () => _showEditProfileDialog(focusField: 'org'),
                    ),
                    const Divider(color: Color(0xFFF1F5F9), height: 18),

                    _buildInfoItem(
                      label: _tr('تاريخ الانضمام', 'Member Since'),
                      value: _joinDate,
                      icon: Icons.calendar_today_outlined,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // 5. Section: التفضيلات والأمان
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    _tr('التفضيلات والأمان', 'Preferences & Security'),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 14.5,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    _tr('إعدادات الحساب', 'Account Settings'),
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Colors.blue.shade700,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),

              _buildNavCard(
                title: _tr('تفضيلات الإشعارات والتنبيهات', 'Notification Preferences'),
                subtitle: _tr('البريد، المنصة، التحديثات الدورية', 'Email, alerts, periodic updates'),
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

              _buildNavCard(
                title: _tr('الأمان والتحقق بخطوتين', 'Security & Two-Factor Auth'),
                subtitle: _tr('كلمة المرور ومفاتيح الأمان', 'Password & security keys'),
                icon: Icons.shield_outlined,
                badge: _tr('مفعّل', 'Active'),
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const Security2FAScreen(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),

              _buildNavCard(
                title: _tr('إدارة البيانات والخصوصية', 'Data & Privacy'),
                subtitle: _tr('تصدير السجلات، سياسات التخزين', 'Export logs & storage policies'),
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

              _buildNavCard(
                title: _tr('لغة التطبيق والمظهر', 'Language & Appearance'),
                subtitle: _tr(
                  'العربية • المظهر الهادئ',
                  'English • Light Theme',
                ),
                icon: Icons.translate_rounded,
                endText: _tr('العربية', 'English'),
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
    VoidCallback? onEdit,
  }) {
    return Row(
      children: [
        if (onEdit != null) ...[
          InkWell(
            onTap: onEdit,
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: const Color(0xFFE0F2FE),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.edit_rounded,
                size: 14,
                color: Color(0xFF0284C7),
              ),
            ),
          ),
          const SizedBox(width: 8),
        ],
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
            const Icon(Icons.arrow_forward_ios_rounded,
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
