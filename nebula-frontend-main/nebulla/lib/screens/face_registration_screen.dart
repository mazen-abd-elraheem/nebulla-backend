import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/theme.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';

class FaceRegistrationScreen extends StatefulWidget {
  const FaceRegistrationScreen({super.key});

  @override
  State<FaceRegistrationScreen> createState() =>
      _FaceRegistrationScreenState();
}

class _FaceRegistrationScreenState extends State<FaceRegistrationScreen> {
  final _repo = NebulaRepository.instance;
  final _nameCtrl = TextEditingController();
  File? _imageFile;
  bool _uploading = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final picked =
        await picker.pickImage(source: source, imageQuality: 85);
    if (picked != null) {
      setState(() => _imageFile = File(picked.path));
    }
  }

  Future<void> _register() async {
    if (_nameCtrl.text.trim().isEmpty || _imageFile == null) {
      showErrorSnackbar(context, 'الرجاء إدخال الاسم واختيار صورة');
      return;
    }
    setState(() => _uploading = true);
    try {
      await _repo.registerFace(_nameCtrl.text.trim(), _imageFile!);
      if (mounted) {
        showSuccessSnackbar(context, 'تم تسجيل الوجه بنجاح');
        setState(() {
          _imageFile = null;
          _nameCtrl.clear();
        });
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل التسجيل: $e');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.bgGradient),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header
                Row(
                  children: [
                    GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: const Icon(Icons.arrow_back_ios,
                          color: AppColors.teal, size: 20),
                    ),
                    const SizedBox(width: 12),
                    const Text('تسجيل الوجه',
                        style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                            color: AppColors.textPrimary)),
                  ],
                ),
                const SizedBox(height: 24),
                // Info card
                NebulaCard(
                  borderColor: AppColors.teal.withValues(alpha: 0.3),
                  child: const Row(
                    children: [
                      Icon(Icons.info_outline,
                          color: AppColors.teal, size: 20),
                      SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'سيتم تسجيل الوجه في قاعدة بيانات نظام UniFace لتمكين التعرف البصري.',
                          style: TextStyle(
                              color: AppColors.textSecondary,
                              fontFamily: 'Cairo',
                              fontSize: 13,
                              height: 1.5),
                          textDirection: TextDirection.rtl,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                // Image picker
                GestureDetector(
                  onTap: () => _showPickOptions(),
                  child: Container(
                    height: 240,
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: _imageFile != null
                            ? AppColors.teal.withValues(alpha: 0.5)
                            : AppColors.cardBorder,
                        width: _imageFile != null ? 1.5 : 1,
                      ),
                    ),
                    child: _imageFile != null
                        ? ClipRRect(
                            borderRadius: BorderRadius.circular(16),
                            child: Image.file(
                              _imageFile!,
                              fit: BoxFit.cover,
                              width: double.infinity,
                            ),
                          )
                        : Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Container(
                                width: 72,
                                height: 72,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: AppColors.teal
                                      .withValues(alpha: 0.1),
                                  border: Border.all(
                                      color: AppColors.teal
                                          .withValues(alpha: 0.3)),
                                ),
                                child: const Icon(
                                    Icons.add_a_photo_outlined,
                                    color: AppColors.teal,
                                    size: 30),
                              ),
                              const SizedBox(height: 16),
                              const Text('اضغط لاختيار صورة',
                                  style: TextStyle(
                                      color: AppColors.textSecondary,
                                      fontFamily: 'Cairo',
                                      fontSize: 15)),
                              const SizedBox(height: 6),
                              const Text('JPG / PNG · جودة واضحة للوجه',
                                  style: TextStyle(
                                      color: AppColors.textMuted,
                                      fontFamily: 'Cairo',
                                      fontSize: 12)),
                            ],
                          ),
                  ),
                ),
                if (_imageFile != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: TextButton.icon(
                      onPressed: _showPickOptions,
                      icon: const Icon(Icons.swap_horiz,
                          color: AppColors.teal, size: 16),
                      label: const Text('تغيير الصورة',
                          style: TextStyle(
                              color: AppColors.teal, fontFamily: 'Cairo')),
                    ),
                  ),
                const SizedBox(height: 20),
                // Name field
                NebulaCard(
                  child: TextFormField(
                    controller: _nameCtrl,
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                        color: AppColors.textPrimary, fontFamily: 'Cairo'),
                    decoration: const InputDecoration(
                      labelText: 'اسم الشخص',
                      prefixIcon: Icon(Icons.person_outline),
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                NebulaPrimaryButton(
                  label: 'تسجيل الوجه',
                  icon: Icons.face_retouching_natural,
                  onTap: _register,
                  loading: _uploading,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showPickOptions() {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
          borderRadius:
              BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: AppColors.cardBorder,
                    borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(height: 20),
              ListTile(
                leading: const Icon(Icons.camera_alt_outlined,
                    color: AppColors.teal),
                title: const Text('الكاميرا',
                    style: TextStyle(
                        fontFamily: 'Cairo', color: AppColors.textPrimary)),
                onTap: () {
                  Navigator.pop(context);
                  _pickImage(ImageSource.camera);
                },
              ),
              ListTile(
                leading: const Icon(Icons.photo_library_outlined,
                    color: AppColors.teal),
                title: const Text('معرض الصور',
                    style: TextStyle(
                        fontFamily: 'Cairo', color: AppColors.textPrimary)),
                onTap: () {
                  Navigator.pop(context);
                  _pickImage(ImageSource.gallery);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
