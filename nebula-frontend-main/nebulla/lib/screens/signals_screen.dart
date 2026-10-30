import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';

class SignalsScreen extends StatefulWidget {
  const SignalsScreen({super.key});

  @override
  State<SignalsScreen> createState() => _SignalsScreenState();
}

class _SignalsScreenState extends State<SignalsScreen> {
  final _repo = NebulaRepository.instance;
  List<Signal> _signals = [];
  bool _loading = true;
  String? _firingName;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _signals = await _repo.getSignals();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في التحميل: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _fire(Signal s) async {
    setState(() => _firingName = s.name);
    try {
      await _repo.fireSignal(s.name);
      if (mounted) showSuccessSnackbar(context, '⚡ تم إطلاق ${s.name}');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الإطلاق: $e');
    } finally {
      if (mounted) setState(() => _firingName = null);
    }
  }

  Future<void> _delete(Signal s) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        title: const Text('حذف الإشارة',
            style: TextStyle(
                fontFamily: 'Cairo', color: AppColors.textPrimary)),
        content: Text('هل تريد حذف "${s.name}"؟',
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
      await _repo.deleteSignal(s.id);
      if (mounted) showSuccessSnackbar(context, 'تم الحذف');
      await _load();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل: $e');
    }
  }

  void _showCreate() {
    final nameCtrl = TextEditingController();
    final descCtrl = TextEditingController();
    final emotionCtrl = TextEditingController();
    final cmdsCtrl = TextEditingController(text: '[]');

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        title: const Text('إشارة جديدة',
            style: TextStyle(
                fontFamily: 'Cairo', color: AppColors.textPrimary)),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _dialogField(nameCtrl, 'الاسم (اسم فريد)', Icons.label_outline),
              const SizedBox(height: 10),
              _dialogField(descCtrl, 'الوصف (اختياري)',
                  Icons.description_outlined),
              const SizedBox(height: 10),
              _dialogField(emotionCtrl, 'العاطفة (اختياري)',
                  Icons.sentiment_satisfied_outlined),
              const SizedBox(height: 10),
              TextField(
                controller: cmdsCtrl,
                maxLines: 3,
                style: const TextStyle(
                    color: AppColors.textPrimary, fontFamily: 'Cairo'),
                decoration: InputDecoration(
                  labelText: 'أوامر المفاصل (JSON)',
                  labelStyle: const TextStyle(color: AppColors.textSecondary),
                  filled: true,
                  fillColor: AppColors.surface,
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide:
                          const BorderSide(color: AppColors.cardBorder)),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('إلغاء')),
          TextButton(
            onPressed: () async {
              if (nameCtrl.text.trim().isEmpty) return;
              Navigator.pop(context);
              try {
                await _repo.createSignal(Signal(
                  id: 0,
                  name: nameCtrl.text.trim(),
                  description: descCtrl.text.trim().isEmpty
                      ? null
                      : descCtrl.text.trim(),
                  jointCommandsJson: cmdsCtrl.text.trim(),
                  emotionTag: emotionCtrl.text.trim().isEmpty
                      ? null
                      : emotionCtrl.text.trim(),
                ));
                if (mounted) showSuccessSnackbar(context, 'تم الإنشاء');
                await _load();
              } catch (e) {
                if (mounted) showErrorSnackbar(context, 'خطأ: $e');
              }
            },
            child: const Text('إنشاء',
                style: TextStyle(color: AppColors.teal)),
          ),
        ],
      ),
    );
  }

  Widget _dialogField(
      TextEditingController ctrl, String label, IconData icon) {
    return TextField(
      controller: ctrl,
      style: const TextStyle(
          color: AppColors.textPrimary, fontFamily: 'Cairo'),
      decoration: InputDecoration(
        labelText: label,
        labelStyle:
            const TextStyle(color: AppColors.textSecondary, fontFamily: 'Cairo'),
        prefixIcon: Icon(icon, color: AppColors.textSecondary, size: 18),
        filled: true,
        fillColor: AppColors.surface,
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppColors.cardBorder)),
      ),
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
                    const Expanded(
                      child: Text('الإشارات والإيماءات',
                          style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.refresh, color: AppColors.teal),
                      onPressed: _load,
                    ),
                    GestureDetector(
                      onTap: _showCreate,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          gradient: AppColors.purpleGradient,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.add, color: Colors.white, size: 18),
                            SizedBox(width: 4),
                            Text('جديد',
                                style: TextStyle(
                                    fontFamily: 'Cairo',
                                    color: Colors.white,
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
                    : _signals.isEmpty
                        ? const Center(
                            child: Text('لا توجد إشارات بعد',
                                style: TextStyle(
                                    color: AppColors.textMuted,
                                    fontFamily: 'Cairo')))
                        : RefreshIndicator(
                            color: AppColors.teal,
                            backgroundColor: AppColors.surface,
                            onRefresh: _load,
                            child: ListView.builder(
                              padding: const EdgeInsets.all(16),
                              itemCount: _signals.length,
                              itemBuilder: (_, i) => _SignalCard(
                                signal: _signals[i],
                                firing: _firingName == _signals[i].name,
                                onFire: () => _fire(_signals[i]),
                                onDelete: () => _delete(_signals[i]),
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

class _SignalCard extends StatelessWidget {
  final Signal signal;
  final bool firing;
  final VoidCallback onFire;
  final VoidCallback onDelete;

  const _SignalCard({
    required this.signal,
    required this.firing,
    required this.onFire,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: NebulaCard(
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: AppColors.purple.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                    color: AppColors.purple.withValues(alpha: 0.35)),
              ),
              child: const Icon(Icons.gesture,
                  color: AppColors.purple, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(signal.name,
                      style: const TextStyle(
                          color: AppColors.textPrimary,
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w700,
                          fontSize: 14)),
                  if (signal.description != null)
                    Text(signal.description!,
                        style: const TextStyle(
                            color: AppColors.textSecondary,
                            fontFamily: 'Cairo',
                            fontSize: 12)),
                  if (signal.emotionTag != null)
                    Text('🎭 ${signal.emotionTag}',
                        style: const TextStyle(
                            color: AppColors.teal,
                            fontFamily: 'Cairo',
                            fontSize: 11)),
                ],
              ),
            ),
            // Fire button
            GestureDetector(
              onTap: firing ? null : onFire,
              child: Container(
                width: 44,
                height: 44,
                margin: const EdgeInsets.only(right: 6),
                decoration: BoxDecoration(
                  gradient: AppColors.tealGradient,
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(
                        color: AppColors.teal.withValues(alpha: 0.35),
                        blurRadius: 8)
                  ],
                ),
                child: firing
                    ? const Center(
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: AppColors.bg),
                        ),
                      )
                    : const Icon(Icons.play_arrow,
                        color: AppColors.bg, size: 22),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.delete_outline,
                  color: AppColors.error, size: 18),
              onPressed: onDelete,
            ),
          ],
        ),
      ),
    );
  }
}
