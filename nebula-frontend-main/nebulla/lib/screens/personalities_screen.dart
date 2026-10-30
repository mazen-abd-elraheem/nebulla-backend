import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'memories_screen.dart';

class PersonalitiesScreen extends StatefulWidget {
  const PersonalitiesScreen({super.key});

  @override
  State<PersonalitiesScreen> createState() => _PersonalitiesScreenState();
}

class _PersonalitiesScreenState extends State<PersonalitiesScreen> {
  final _repo = NebulaRepository.instance;
  List<Personality> _personalities = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _personalities = await _repo.getPersonalities();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في التحميل: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _activate(Personality p) async {
    try {
      await _repo.activatePersonality(p.id);
      if (mounted) showSuccessSnackbar(context, 'تم تفعيل ${p.name}');
      await _load();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل التفعيل: $e');
    }
  }

  Future<void> _delete(Personality p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        title: const Text('حذف الشخصية',
            style: TextStyle(
                fontFamily: 'Cairo', color: AppColors.textPrimary)),
        content: Text('هل تريد حذف "${p.name}"؟',
            style: const TextStyle(
                fontFamily: 'Cairo', color: AppColors.textSecondary)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('إلغاء')),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('حذف',
                  style: TextStyle(color: AppColors.error))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _repo.deletePersonality(p.id);
      if (mounted) showSuccessSnackbar(context, 'تم الحذف');
      await _load();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الحذف: $e');
    }
  }

  void _openCreate() {
    Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) => PersonalityFormScreen(onSaved: _load)),
    );
  }

  void _openEdit(Personality p) {
    Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) =>
              PersonalityFormScreen(existing: p, onSaved: _load)),
    );
  }

  void _openMemories(Personality p) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => MemoriesScreen(personality: p)),
    );
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
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 12),
                child: Row(
                  children: [
                    const Expanded(
                      child: Text('الشخصيات',
                          style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 22,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.refresh, color: AppColors.teal),
                      onPressed: _load,
                    ),
                    GestureDetector(
                      onTap: _openCreate,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          gradient: AppColors.tealGradient,
                          borderRadius: BorderRadius.circular(10),
                          boxShadow: [
                            BoxShadow(
                                color: AppColors.teal.withValues(alpha: 0.35),
                                blurRadius: 8)
                          ],
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.add, color: AppColors.bg, size: 18),
                            SizedBox(width: 4),
                            Text('جديد',
                                style: TextStyle(
                                    fontFamily: 'Cairo',
                                    color: AppColors.bg,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(
                            color: AppColors.teal))
                    : _personalities.isEmpty
                        ? _EmptyState(onAdd: _openCreate)
                        : RefreshIndicator(
                            color: AppColors.teal,
                            backgroundColor: AppColors.surface,
                            onRefresh: _load,
                            child: ListView.builder(
                              padding: const EdgeInsets.all(16),
                              itemCount: _personalities.length,
                              itemBuilder: (_, i) =>
                                  _PersonalityCard(
                                personality: _personalities[i],
                                onActivate: () =>
                                    _activate(_personalities[i]),
                                onEdit: () =>
                                    _openEdit(_personalities[i]),
                                onDelete: () =>
                                    _delete(_personalities[i]),
                                onMemories: () =>
                                    _openMemories(_personalities[i]),
                              ),
                            ),
                          ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onAdd;
  const _EmptyState({required this.onAdd});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.people_outline,
              color: AppColors.textMuted, size: 64),
          const SizedBox(height: 16),
          const Text('لا توجد شخصيات بعد',
              style: TextStyle(
                  fontFamily: 'Cairo',
                  color: AppColors.textSecondary,
                  fontSize: 15)),
          const SizedBox(height: 16),
          NebulaPrimaryButton(
              label: 'أضف أول شخصية', icon: Icons.add, onTap: onAdd),
        ],
      ),
    );
  }
}

class _PersonalityCard extends StatelessWidget {
  final Personality personality;
  final VoidCallback onActivate;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onMemories;

  const _PersonalityCard({
    required this.personality,
    required this.onActivate,
    required this.onEdit,
    required this.onDelete,
    required this.onMemories,
  });

  @override
  Widget build(BuildContext context) {
    final isActive = personality.isActive;
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: NebulaCard(
        glowing: isActive,
        borderColor: isActive
            ? AppColors.teal.withValues(alpha: 0.6)
            : AppColors.cardBorder,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: isActive
                        ? AppColors.tealGradient
                        : AppColors.purpleGradient,
                    boxShadow: [
                      BoxShadow(
                          color: (isActive ? AppColors.teal : AppColors.purple)
                              .withValues(alpha: 0.35),
                          blurRadius: 10)
                    ],
                  ),
                  child: const Icon(Icons.person_outline,
                      color: Colors.white, size: 24),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(personality.name,
                          style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontWeight: FontWeight.w700,
                              fontSize: 15,
                              color: AppColors.textPrimary)),
                      if (personality.description != null)
                        Text(personality.description!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 12,
                                fontFamily: 'Cairo')),
                    ],
                  ),
                ),
                if (isActive)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: AppColors.teal.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                          color: AppColors.teal.withValues(alpha: 0.5)),
                    ),
                    child: const Text('نشط',
                        style: TextStyle(
                            color: AppColors.teal,
                            fontSize: 11,
                            fontFamily: 'Cairo')),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                _Tag(label: personality.dialect),
                const SizedBox(width: 6),
                _Tag(label: personality.languageMix),
                if (personality.voiceSamplePath != null) ...[
                  const SizedBox(width: 6),
                  _Tag(
                      label: 'صوت مرفق',
                      color: AppColors.success),
                ],
              ],
            ),
            const SizedBox(height: 14),
            const Divider(color: AppColors.cardBorder, height: 1),
            const SizedBox(height: 12),
            // Action row
            Row(
              children: [
                if (!isActive)
                  _ActionBtn(
                      icon: Icons.check_circle_outline,
                      label: 'تفعيل',
                      color: AppColors.teal,
                      onTap: onActivate),
                if (!isActive) const SizedBox(width: 8),
                _ActionBtn(
                    icon: Icons.edit_outlined,
                    label: 'تعديل',
                    color: AppColors.textSecondary,
                    onTap: onEdit),
                const SizedBox(width: 8),
                _ActionBtn(
                    icon: Icons.psychology_outlined,
                    label: 'الذاكرة',
                    color: AppColors.purple,
                    onTap: onMemories),
                _VoiceUploadBtn(personality: personality),
                const Spacer(),
                _ActionBtn(
                    icon: Icons.delete_outline,
                    label: 'حذف',
                    color: AppColors.error,
                    onTap: onDelete),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  final String label;
  final Color? color;
  const _Tag({required this.label, this.color});

  @override
  Widget build(BuildContext context) {
    final c = color ?? AppColors.tealDim;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.withValues(alpha: 0.3)),
      ),
      child: Text(label,
          style: TextStyle(
              color: c, fontSize: 11, fontFamily: 'Cairo')),
    );
  }
}

class _ActionBtn extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _ActionBtn(
      {required this.icon,
      required this.label,
      required this.color,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 14),
            const SizedBox(width: 4),
            Text(label,
                style: TextStyle(
                    color: color,
                    fontSize: 12,
                    fontFamily: 'Cairo')),
          ],
        ),
      ),
    );
  }
}

class _VoiceUploadBtn extends StatefulWidget {
  final Personality personality;
  const _VoiceUploadBtn({required this.personality});

  @override
  State<_VoiceUploadBtn> createState() => _VoiceUploadBtnState();
}

class _VoiceUploadBtnState extends State<_VoiceUploadBtn> {
  bool _uploading = false;

  Future<void> _pick() async {
    final picker = ImagePicker();
    final picked = await picker.pickVideo(source: ImageSource.gallery);
    if (picked == null) return;

    setState(() => _uploading = true);
    try {
      await NebulaRepository.instance
          .uploadVoiceSample(widget.personality.id, File(picked.path));
      if (mounted) {
        showSuccessSnackbar(context, 'تم رفع عينة الصوت');
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الرفع: $e');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_uploading) {
      return const SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(
              strokeWidth: 2, color: AppColors.teal));
    }
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: _ActionBtn(
          icon: Icons.mic_outlined,
          label: 'صوت',
          color: AppColors.warning,
          onTap: _pick),
    );
  }
}

// ─── Personality Form ────────────────────────────────────────────────────────

class PersonalityFormScreen extends StatefulWidget {
  final Personality? existing;
  final VoidCallback onSaved;

  const PersonalityFormScreen(
      {super.key, this.existing, required this.onSaved});

  @override
  State<PersonalityFormScreen> createState() =>
      _PersonalityFormScreenState();
}

class _PersonalityFormScreenState extends State<PersonalityFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameCtrl;
  late TextEditingController _descCtrl;
  late TextEditingController _promptCtrl;
  String _dialect = 'cairo';
  String _langMix = 'ar_en';
  bool _saving = false;

  final _dialects = ['cairo', 'gulf', 'levantine', 'msa'];
  final _langMixes = ['ar_en', 'ar', 'en'];

  @override
  void initState() {
    super.initState();
    _nameCtrl =
        TextEditingController(text: widget.existing?.name ?? '');
    _descCtrl = TextEditingController(
        text: widget.existing?.description ?? '');
    _promptCtrl =
        TextEditingController(text: widget.existing?.systemPrompt ?? '');
    _dialect = widget.existing?.dialect ?? 'cairo';
    _langMix = widget.existing?.languageMix ?? 'ar_en';
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    _promptCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final body = {
        'name': _nameCtrl.text.trim(),
        'description': _descCtrl.text.trim().isEmpty
            ? null
            : _descCtrl.text.trim(),
        'system_prompt': _promptCtrl.text.trim(),
        'dialect': _dialect,
        'language_mix': _langMix,
      };
      if (widget.existing == null) {
        await NebulaRepository.instance.createPersonality(
            Personality(
                id: 0,
                name: _nameCtrl.text.trim(),
                description: _descCtrl.text.trim().isEmpty
                    ? null
                    : _descCtrl.text.trim(),
                systemPrompt: _promptCtrl.text.trim(),
                dialect: _dialect,
                languageMix: _langMix,
                isActive: false));
      } else {
        await NebulaRepository.instance
            .updatePersonality(widget.existing!.id, body);
      }
      if (!mounted) return;
      showSuccessSnackbar(context, 'تم الحفظ');
      widget.onSaved();
      Navigator.pop(context);
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الحفظ: $e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
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
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: const Icon(Icons.arrow_back_ios,
                          color: AppColors.teal, size: 20),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      widget.existing == null
                          ? 'شخصية جديدة'
                          : 'تعديل الشخصية',
                      style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: AppColors.textPrimary),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        NebulaCard(
                          child: Column(
                            children: [
                              TextFormField(
                                controller: _nameCtrl,
                                textAlign: TextAlign.right,
                                style: const TextStyle(
                                    color: AppColors.textPrimary,
                                    fontFamily: 'Cairo'),
                                decoration: const InputDecoration(
                                    labelText: 'اسم الشخصية',
                                    prefixIcon: Icon(
                                        Icons.badge_outlined)),
                                validator: (v) =>
                                    (v == null || v.trim().isEmpty)
                                        ? 'الاسم مطلوب'
                                        : null,
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _descCtrl,
                                textAlign: TextAlign.right,
                                maxLines: 2,
                                style: const TextStyle(
                                    color: AppColors.textPrimary,
                                    fontFamily: 'Cairo'),
                                decoration: const InputDecoration(
                                    labelText: 'الوصف (اختياري)',
                                    prefixIcon: Icon(
                                        Icons.description_outlined)),
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _promptCtrl,
                                textAlign: TextAlign.right,
                                maxLines: 5,
                                style: const TextStyle(
                                    color: AppColors.textPrimary,
                                    fontFamily: 'Cairo'),
                                decoration: const InputDecoration(
                                  labelText: 'نص النظام (System Prompt)',
                                  alignLabelWithHint: true,
                                  prefixIcon: Icon(
                                      Icons.psychology_outlined),
                                ),
                              ),
                              const SizedBox(height: 14),
                              Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const Text('اللهجة',
                                            style: TextStyle(
                                                color:
                                                    AppColors.textSecondary,
                                                fontFamily: 'Cairo',
                                                fontSize: 12)),
                                        const SizedBox(height: 6),
                                        DropdownButtonFormField<String>(
                                          initialValue: _dialect,
                                          dropdownColor: AppColors.card,
                                          style: const TextStyle(
                                              color: AppColors.textPrimary,
                                              fontFamily: 'Cairo'),
                                          decoration: InputDecoration(
                                            contentPadding:
                                                const EdgeInsets.symmetric(
                                                    horizontal: 12,
                                                    vertical: 10),
                                            border: OutlineInputBorder(
                                                borderRadius:
                                                    BorderRadius.circular(
                                                        10)),
                                          ),
                                          items: _dialects
                                              .map((d) =>
                                                  DropdownMenuItem(
                                                      value: d,
                                                      child: Text(d)))
                                              .toList(),
                                          onChanged: (v) => setState(
                                              () => _dialect = v!),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const Text('اللغة',
                                            style: TextStyle(
                                                color:
                                                    AppColors.textSecondary,
                                                fontFamily: 'Cairo',
                                                fontSize: 12)),
                                        const SizedBox(height: 6),
                                        DropdownButtonFormField<String>(
                                          initialValue: _langMix,
                                          dropdownColor: AppColors.card,
                                          style: const TextStyle(
                                              color: AppColors.textPrimary,
                                              fontFamily: 'Cairo'),
                                          decoration: InputDecoration(
                                            contentPadding:
                                                const EdgeInsets.symmetric(
                                                    horizontal: 12,
                                                    vertical: 10),
                                            border: OutlineInputBorder(
                                                borderRadius:
                                                    BorderRadius.circular(
                                                        10)),
                                          ),
                                          items: _langMixes
                                              .map((l) =>
                                                  DropdownMenuItem(
                                                      value: l,
                                                      child: Text(l)))
                                              .toList(),
                                          onChanged: (v) =>
                                              setState(() => _langMix = v!),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),
                        NebulaPrimaryButton(
                          label: 'حفظ الشخصية',
                          icon: Icons.save_outlined,
                          onTap: _save,
                          loading: _saving,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
