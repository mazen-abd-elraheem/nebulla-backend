import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';

class MemoriesScreen extends StatefulWidget {
  final Personality personality;
  const MemoriesScreen({super.key, required this.personality});

  @override
  State<MemoriesScreen> createState() => _MemoriesScreenState();
}

class _MemoriesScreenState extends State<MemoriesScreen> {
  final _repo = NebulaRepository.instance;
  final _searchCtrl = TextEditingController();

  List<Memory> _memories = [];
  bool _loading = true;
  bool _searching = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _memories = await _repo.getMemories(widget.personality.id);
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في التحميل: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _search(String q) async {
    if (q.trim().isEmpty) {
      _load();
      return;
    }
    setState(() => _searching = true);
    try {
      _memories =
          await _repo.searchMemories(q.trim(), widget.personality.id);
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في البحث: $e');
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _deleteMemory(Memory m) async {
    try {
      await _repo.deleteMemory(m.id);
      if (mounted) showSuccessSnackbar(context, 'تم الحذف');
      await _load();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الحذف: $e');
    }
  }

  void _showAddDialog() {
    final contentCtrl = TextEditingController();
    int importance = 5;

    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, ss) => AlertDialog(
          backgroundColor: AppColors.card,
          title: const Text('إضافة ذاكرة',
              style: TextStyle(
                  fontFamily: 'Cairo', color: AppColors.textPrimary)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: contentCtrl,
                textDirection: TextDirection.rtl,
                maxLines: 4,
                style: const TextStyle(
                    color: AppColors.textPrimary, fontFamily: 'Cairo'),
                decoration: InputDecoration(
                  hintText: 'اكتب المحتوى هنا...',
                  hintStyle: const TextStyle(
                      color: AppColors.textMuted, fontFamily: 'Cairo'),
                  filled: true,
                  fillColor: AppColors.surface,
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide:
                          const BorderSide(color: AppColors.cardBorder)),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  const Text('الأهمية:',
                      style: TextStyle(
                          color: AppColors.textSecondary,
                          fontFamily: 'Cairo')),
                  Expanded(
                    child: Slider(
                      value: importance.toDouble(),
                      min: 1,
                      max: 10,
                      divisions: 9,
                      activeColor: AppColors.teal,
                      inactiveColor: AppColors.cardBorder,
                      label: importance.toString(),
                      onChanged: (v) => ss(() => importance = v.round()),
                    ),
                  ),
                  Text(importance.toString(),
                      style: const TextStyle(
                          color: AppColors.teal, fontFamily: 'Cairo')),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('إلغاء')),
            TextButton(
              onPressed: () async {
                final text = contentCtrl.text.trim();
                if (text.isEmpty) return;
                Navigator.pop(ctx);
                try {
                  await _repo.addMemory(
                      text, widget.personality.id, importance);
                  if (mounted) {
                    showSuccessSnackbar(context, 'تمت الإضافة');
                  }
                  await _load();
                } catch (e) {
                  if (mounted) {
                    showErrorSnackbar(context, 'فشل الحفظ: $e');
                  }
                }
              },
              child: const Text('حفظ',
                  style: TextStyle(color: AppColors.teal)),
            ),
          ],
        ),
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
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('الذاكرة',
                              style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 20,
                                  fontWeight: FontWeight.w800,
                                  color: AppColors.textPrimary)),
                          Text(widget.personality.name,
                              style: const TextStyle(
                                  color: AppColors.teal,
                                  fontSize: 12,
                                  fontFamily: 'Cairo')),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: _showAddDialog,
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          gradient: AppColors.tealGradient,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.add,
                            color: AppColors.bg, size: 22),
                      ),
                    ),
                  ],
                ),
              ),
              // Search
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TextField(
                  controller: _searchCtrl,
                  textDirection: TextDirection.rtl,
                  style: const TextStyle(
                      color: AppColors.textPrimary, fontFamily: 'Cairo'),
                  decoration: InputDecoration(
                    hintText: 'بحث دلالي في الذاكرة...',
                    prefixIcon: _searching
                        ? const Padding(
                            padding: EdgeInsets.all(12),
                            child: SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: AppColors.teal),
                            ),
                          )
                        : const Icon(Icons.search),
                    suffixIcon: _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: () {
                              _searchCtrl.clear();
                              _load();
                            },
                          )
                        : null,
                  ),
                  onSubmitted: _search,
                ),
              ),
              const SizedBox(height: 12),
              // List
              Expanded(
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(
                            color: AppColors.teal))
                    : _memories.isEmpty
                        ? const Center(
                            child: Text('لا توجد ذكريات',
                                style: TextStyle(
                                    color: AppColors.textMuted,
                                    fontFamily: 'Cairo')))
                        : RefreshIndicator(
                            color: AppColors.teal,
                            backgroundColor: AppColors.surface,
                            onRefresh: _load,
                            child: ListView.builder(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 4),
                              itemCount: _memories.length,
                              itemBuilder: (_, i) => _MemoryTile(
                                memory: _memories[i],
                                onDelete: () =>
                                    _deleteMemory(_memories[i]),
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

class _MemoryTile extends StatelessWidget {
  final Memory memory;
  final VoidCallback onDelete;
  const _MemoryTile({required this.memory, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final importanceColor = memory.importance >= 8
        ? AppColors.error
        : memory.importance >= 5
            ? AppColors.warning
            : AppColors.textMuted;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: NebulaCard(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Importance indicator
            Container(
              width: 4,
              height: 50,
              decoration: BoxDecoration(
                color: importanceColor,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    memory.content,
                    style: const TextStyle(
                        color: AppColors.textPrimary,
                        fontFamily: 'Cairo',
                        fontSize: 13,
                        height: 1.6),
                    textDirection: TextDirection.rtl,
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: importanceColor.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(
                              color:
                                  importanceColor.withValues(alpha: 0.4)),
                        ),
                        child: Text('أهمية: ${memory.importance}',
                            style: TextStyle(
                                color: importanceColor,
                                fontSize: 10,
                                fontFamily: 'Cairo')),
                      ),
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(memory.source,
                            style: const TextStyle(
                                color: AppColors.textMuted,
                                fontSize: 10,
                                fontFamily: 'Cairo')),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.delete_outline,
                  color: AppColors.error, size: 18),
              onPressed: onDelete,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ],
        ),
      ),
    );
  }
}
