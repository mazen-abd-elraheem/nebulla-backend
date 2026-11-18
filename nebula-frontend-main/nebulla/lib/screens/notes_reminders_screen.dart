import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/local_reminder_alert_service.dart';
import '../services/locale_service.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import 'main_shell.dart';

class NotesRemindersScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;
  final bool isActive;

  const NotesRemindersScreen({
    super.key,
    this.onNavigate,
    this.isActive = false,
  });

  @override
  State<NotesRemindersScreen> createState() => _NotesRemindersScreenState();
}

class _NotesRemindersScreenState extends State<NotesRemindersScreen>
    with SingleTickerProviderStateMixin {
  final _repo = NebulaRepository.instance;
  late final TabController _tabController;

  bool _loading = true;
  String? _error;
  List<ReminderNoteItem> _items = [];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(() {
      if (mounted) setState(() {});
    });
    LocalReminderAlertService.instance.remindersVersion.addListener(
      _onExternalReminderUpdate,
    );
    _loadItems();
  }

  void _onExternalReminderUpdate() {
    if (mounted) {
      _loadItems();
    }
  }

  @override
  void didUpdateWidget(covariant NotesRemindersScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      _loadItems();
    }
  }

  @override
  void dispose() {
    LocalReminderAlertService.instance.remindersVersion.removeListener(
      _onExternalReminderUpdate,
    );
    _tabController.dispose();
    super.dispose();
  }

  List<ReminderNoteItem> get _reminders =>
      _items.where((e) => !e.isNote).toList();

  List<ReminderNoteItem> get _notes => _items.where((e) => e.isNote).toList();

  Future<void> _loadItems() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final fetched = await _repo.getReminders(activeOnly: true);
      if (!mounted) return;
      setState(() {
        _items = fetched;
        _loading = false;
      });
      LocalReminderAlertService.instance.syncItems(_items);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e is ApiException
            ? e.message
            : 'تعذر تحميل الملاحظات والمهام من الخادم.';
      });
    }
  }

  Future<void> _toggleComplete(ReminderNoteItem item) async {
    try {
      ReminderNoteItem updated;
      if (item.isCompleted) {
        updated = await _repo.updateReminder(id: item.id, status: 'pending');
      } else {
        updated = await _repo.acknowledgeReminder(item.id);
      }
      if (!mounted) return;
      setState(() {
        final idx = _items.indexWhere((e) => e.id == item.id);
        if (idx >= 0) _items[idx] = updated;
      });
      LocalReminderAlertService.instance.syncItems(_items);
      showSuccessSnackbar(
        context,
        updated.isCompleted
            ? 'تم إنجاز المهمة بنجاح ✓'
            : 'تمت إعادة المهمة لقائمة الانتظار',
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(
        context,
        e is ApiException ? e.message : 'تعذر تحديث حالة المهمة.',
      );
    }
  }

  Future<void> _deleteItem(ReminderNoteItem item) async {
    try {
      await _repo.deleteReminder(item.id);
      if (!mounted) return;
      setState(() {
        _items.removeWhere((e) => e.id == item.id);
      });
      LocalReminderAlertService.instance.syncItems(_items);
      showSuccessSnackbar(
        context,
        item.isNote ? 'تم حذف الملاحظة بنجاح' : 'تم حذف التذكير بنجاح',
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(
        context,
        e is ApiException ? e.message : 'تعذر الحذف من الخادم.',
      );
    }
  }

  void _showAddOrEditDialog({
    required bool isNote,
    ReminderNoteItem? existing,
  }) {
    final titleCtrl = TextEditingController(text: existing?.title ?? '');
    final descCtrl = TextEditingController(text: existing?.description ?? '');
    String reminderType = existing?.reminderType ?? (isNote ? 'note' : 'task');
    String recurrence = existing?.recurrence ?? 'once';
    DateTime selectedDateTime =
        existing?.targetTime ?? DateTime.now().add(const Duration(hours: 1));
    bool saving = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheetState) {
          final bottomInset = MediaQuery.of(ctx).viewInsets.bottom;
          return Directionality(
            textDirection: TextDirection.rtl,
            child: Container(
              padding: EdgeInsets.fromLTRB(20, 16, 20, 20 + bottomInset),
              decoration: const BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Center(
                      child: Container(
                        width: 42,
                        height: 4,
                        decoration: BoxDecoration(
                          color: const Color(0xFFCBD5E1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            color: isNote
                                ? const Color(0xFFFEF3C7)
                                : const Color(0xFFE0F2FE),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            isNote
                                ? Icons.sticky_note_2_rounded
                                : Icons.alarm_add_rounded,
                            color: isNote
                                ? const Color(0xFFD97706)
                                : const Color(0xFF0284C7),
                            size: 20,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            existing != null
                                ? (isNote ? 'تعديل الملاحظة' : 'تعديل التذكير')
                                : (isNote
                                      ? 'إضافة ملاحظة جديدة'
                                      : 'إضافة تذكير مهمة'),
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 16,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF0F172A),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Title field
                    TextField(
                      controller: titleCtrl,
                      textDirection: TextDirection.rtl,
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0F172A),
                      ),
                      decoration: InputDecoration(
                        labelText: isNote
                            ? 'عنوان الملاحظة'
                            : 'عنوان المهمة أو التذكير',
                        hintText: isNote
                            ? 'مثال: أفكار المشروع'
                            : 'مثال: مراجعة التقرير أو موعد الدواء',
                        labelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                        floatingLabelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0284C7),
                        ),
                        hintStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF94A3B8),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFFCBD5E1),
                            width: 1.2,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFF00B4D8),
                            width: 1.6,
                          ),
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFFCBD5E1),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Description / Body field
                    TextField(
                      controller: descCtrl,
                      textDirection: TextDirection.rtl,
                      maxLines: isNote ? 4 : 2,
                      cursorColor: const Color(0xFF00B4D8),
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13.5,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF0F172A),
                      ),
                      decoration: InputDecoration(
                        labelText: isNote
                            ? 'تفاصيل الملاحظة'
                            : 'ملاحظات إضافية (اختياري)',
                        hintText: isNote
                            ? 'اكتب كل اللي حابب تفتكره هنا...'
                            : 'تفاصيل سريعة عن المهمة...',
                        labelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF334155),
                        ),
                        floatingLabelStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0284C7),
                        ),
                        hintStyle: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF94A3B8),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFFCBD5E1),
                            width: 1.2,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFF00B4D8),
                            width: 1.6,
                          ),
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: Color(0xFFCBD5E1),
                          ),
                        ),
                      ),
                    ),

                    if (!isNote) ...[
                      const SizedBox(height: 14),
                      const Text(
                        'نوع التذكير',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12.5,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF334155),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _buildChoiceChip(
                            label: 'مهمة',
                            icon: Icons.task_alt_rounded,
                            selected: reminderType == 'task',
                            onTap: () =>
                                setSheetState(() => reminderType = 'task'),
                          ),
                          const SizedBox(width: 8),
                          _buildChoiceChip(
                            label: 'دواء',
                            icon: Icons.medication_rounded,
                            selected: reminderType == 'medicine',
                            onTap: () =>
                                setSheetState(() => reminderType = 'medicine'),
                          ),
                          const SizedBox(width: 8),
                          _buildChoiceChip(
                            label: 'موعد',
                            icon: Icons.event_rounded,
                            selected: reminderType == 'appointment',
                            onTap: () => setSheetState(
                              () => reminderType = 'appointment',
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      const Text(
                        'موعد التذكير',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12.5,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF334155),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () async {
                                final now = DateTime.now();
                                final minDate = selectedDateTime.isBefore(now)
                                    ? selectedDateTime.subtract(
                                        const Duration(days: 1),
                                      )
                                    : now.subtract(const Duration(days: 1));
                                final pickedDate = await showDatePicker(
                                  context: ctx,
                                  initialDate: selectedDateTime,
                                  firstDate: minDate,
                                  lastDate: now.add(
                                    const Duration(days: 365 * 2),
                                  ),
                                  builder: (pickerCtx, child) => Theme(
                                    data: ThemeData.light().copyWith(
                                      colorScheme: const ColorScheme.light(
                                        primary: Color(0xFF00B4D8),
                                        onPrimary: Colors.white,
                                        surface: Colors.white,
                                        onSurface: Color(0xFF0F172A),
                                      ),
                                    ),
                                    child: child!,
                                  ),
                                );
                                if (pickedDate != null) {
                                  setSheetState(() {
                                    selectedDateTime = DateTime(
                                      pickedDate.year,
                                      pickedDate.month,
                                      pickedDate.day,
                                      selectedDateTime.hour,
                                      selectedDateTime.minute,
                                    );
                                  });
                                }
                              },
                              icon: const Icon(
                                Icons.calendar_today_rounded,
                                size: 16,
                              ),
                              label: Text(
                                _formatDate(selectedDateTime),
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 12,
                                ),
                              ),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFF0F172A),
                                side: const BorderSide(
                                  color: Color(0xFFCBD5E1),
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                padding: const EdgeInsets.symmetric(
                                  vertical: 11,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () async {
                                final pickedTime = await showTimePicker(
                                  context: ctx,
                                  initialTime: TimeOfDay.fromDateTime(
                                    selectedDateTime,
                                  ),
                                  builder: (pickerCtx, child) => Theme(
                                    data: ThemeData.light().copyWith(
                                      colorScheme: const ColorScheme.light(
                                        primary: Color(0xFF00B4D8),
                                        onPrimary: Colors.white,
                                        surface: Colors.white,
                                        onSurface: Color(0xFF0F172A),
                                      ),
                                    ),
                                    child: child!,
                                  ),
                                );
                                if (pickedTime != null) {
                                  setSheetState(() {
                                    selectedDateTime = DateTime(
                                      selectedDateTime.year,
                                      selectedDateTime.month,
                                      selectedDateTime.day,
                                      pickedTime.hour,
                                      pickedTime.minute,
                                    );
                                  });
                                }
                              },
                              icon: const Icon(
                                Icons.access_time_rounded,
                                size: 16,
                              ),
                              label: Text(
                                _formatTime(selectedDateTime),
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 12,
                                ),
                              ),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFF0F172A),
                                side: const BorderSide(
                                  color: Color(0xFFCBD5E1),
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                padding: const EdgeInsets.symmetric(
                                  vertical: 11,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      const Text(
                        'التكرار',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12.5,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF334155),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _buildChoiceChip(
                            label: 'مرة واحدة',
                            icon: Icons.looks_one_rounded,
                            selected: recurrence == 'once',
                            onTap: () =>
                                setSheetState(() => recurrence = 'once'),
                          ),
                          const SizedBox(width: 8),
                          _buildChoiceChip(
                            label: 'يومياً',
                            icon: Icons.repeat_rounded,
                            selected: recurrence == 'daily',
                            onTap: () =>
                                setSheetState(() => recurrence = 'daily'),
                          ),
                          const SizedBox(width: 8),
                          _buildChoiceChip(
                            label: 'أسبوعياً',
                            icon: Icons.date_range_rounded,
                            selected: recurrence == 'weekly',
                            onTap: () =>
                                setSheetState(() => recurrence = 'weekly'),
                          ),
                        ],
                      ),
                    ],

                    const SizedBox(height: 20),
                    ElevatedButton.icon(
                      onPressed: saving
                          ? null
                          : () async {
                              final title = titleCtrl.text.trim();
                              if (title.isEmpty) {
                                showErrorSnackbar(
                                  context,
                                  isNote
                                      ? 'يرجى كتابة عنوان الملاحظة.'
                                      : 'يرجى كتابة عنوان المهمة.',
                                );
                                return;
                              }
                              setSheetState(() => saving = true);
                              try {
                                if (existing != null) {
                                  final updated = await _repo.updateReminder(
                                    id: existing.id,
                                    title: title,
                                    description: descCtrl.text.trim(),
                                    reminderType: isNote
                                        ? 'note'
                                        : reminderType,
                                    targetTime: isNote
                                        ? null
                                        : selectedDateTime,
                                    recurrence: isNote ? 'once' : recurrence,
                                  );
                                  if (!mounted) return;
                                  setState(() {
                                    final i = _items.indexWhere(
                                      (e) => e.id == existing.id,
                                    );
                                    if (i >= 0) _items[i] = updated;
                                  });
                                } else {
                                  final created = await _repo.createReminder(
                                    title: title,
                                    description: descCtrl.text.trim(),
                                    reminderType: isNote
                                        ? 'note'
                                        : reminderType,
                                    targetTime: isNote
                                        ? null
                                        : selectedDateTime,
                                    recurrence: isNote ? 'once' : recurrence,
                                  );
                                  if (!mounted) return;
                                  setState(() {
                                    _items.insert(0, created);
                                  });
                                }
                                LocalReminderAlertService.instance.syncItems(
                                  _items,
                                );
                                if (ctx.mounted) Navigator.of(ctx).pop();
                                showSuccessSnackbar(
                                  context,
                                  existing != null
                                      ? 'تم حفظ التعديلات بنجاح ✨'
                                      : (isNote
                                            ? 'تم حفظ الملاحظة بنجاح 📝'
                                            : 'تم إضافة تذكير المهمة بنجاح ⏰'),
                                );
                              } catch (e) {
                                setSheetState(() => saving = false);
                                if (!mounted) return;
                                showErrorSnackbar(
                                  context,
                                  e is ApiException
                                      ? e.message
                                      : 'تعذر الحفظ في الخادم.',
                                );
                              }
                            },
                      icon: saving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              ),
                            )
                          : const Icon(Icons.check_rounded, size: 20),
                      label: Text(
                        existing != null
                            ? 'حفظ التعديلات'
                            : (isNote ? 'حفظ الملاحظة' : 'حفظ التذكير'),
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF00B4D8),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        elevation: 0,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildChoiceChip({
    required String label,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 6),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF00B4D8) : const Color(0xFFF8FAFC),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected
                  ? const Color(0xFF00B4D8)
                  : const Color(0xFFE2E8F0),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                size: 15,
                color: selected ? Colors.white : const Color(0xFF475569),
              ),
              const SizedBox(width: 4),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11.5,
                    fontWeight: FontWeight.bold,
                    color: selected ? Colors.white : const Color(0xFF334155),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime dt) {
    final d = dt.day.toString().padLeft(2, '0');
    final m = dt.month.toString().padLeft(2, '0');
    return '${dt.year}/$m/$d';
  }

  String _formatTime(DateTime dt) {
    final period = dt.hour >= 12 ? 'م' : 'ص';
    final h = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
    final min = dt.minute.toString().padLeft(2, '0');
    return '$h:$min $period';
  }

  String _recurrenceLabel(String r) {
    switch (r) {
      case 'daily':
        return 'يومياً';
      case 'weekly':
        return 'أسبوعياً';
      default:
        return 'مرة واحدة';
    }
  }

  (String, Color, Color, IconData) _typeMeta(String type) {
    switch (type) {
      case 'medicine':
        return (
          'دواء',
          const Color(0xFFDCFCE7),
          const Color(0xFF15803D),
          Icons.medication_rounded,
        );
      case 'appointment':
        return (
          'موعد',
          const Color(0xFFF3E8FF),
          const Color(0xFF7E22CE),
          Icons.event_rounded,
        );
      default:
        return (
          'مهمة',
          const Color(0xFFE0F2FE),
          const Color(0xFF0369A1),
          Icons.task_alt_rounded,
        );
    }
  }

  Widget _buildHeader() {
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
          border: Border.all(color: const Color(0xFFCBD5E1), width: 1.4),
        ),
        child: const Icon(
          Icons.menu_rounded,
          size: 20,
          color: Color(0xFF0F172A),
        ),
      ),
    );

    final backBtn = InkWell(
      onTap: () {
        if (Navigator.canPop(context)) {
          Navigator.pop(context);
        } else {
          widget.onNavigate?.call(2);
        }
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFCBD5E1), width: 1.4),
        ),
        child: Icon(
          isArabic ? Icons.arrow_forward_rounded : Icons.arrow_back_rounded,
          size: 20,
          color: const Color(0xFF0F172A),
        ),
      ),
    );

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(
          bottom: BorderSide(color: Color(0xFFF1F5F9), width: 1.2),
        ),
      ),
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Row(
          children: [
            isArabic ? menuBtn : backBtn,
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    isArabic ? 'الملاحظات وتذكير المهام' : 'Notes & Reminders',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.w900,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                  Text(
                    isArabic
                        ? 'نظم مهامك، مواعيدك، وملاحظاتك اليومية'
                        : 'Organize tasks, reminders, and personal notes',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: Color(0xFF64748B),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            isArabic ? backBtn : menuBtn,
          ],
        ),
      ),
    );
  }

  Widget _buildStatsStrip() {
    final t = LocaleService.instance.tr;
    final pendingCount = _reminders.where((e) => !e.isCompleted).length;
    final doneCount = _reminders.where((e) => e.isCompleted).length;
    final notesCount = _notes.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
      child: Row(
        children: [
          _buildStatPill(
            label: t('مهام قادمة', 'Upcoming'),
            count: pendingCount,
            color: const Color(0xFF0284C7),
            bg: const Color(0xFFE0F2FE),
          ),
          const SizedBox(width: 8),
          _buildStatPill(
            label: t('تم إنجازها', 'Completed'),
            count: doneCount,
            color: const Color(0xFF15803D),
            bg: const Color(0xFFDCFCE7),
          ),
          const SizedBox(width: 8),
          _buildStatPill(
            label: t('ملاحظات', 'Notes'),
            count: notesCount,
            color: const Color(0xFFD97706),
            bg: const Color(0xFFFEF3C7),
          ),
        ],
      ),
    );
  }

  Widget _buildStatPill({
    required String label,
    required int count,
    required Color color,
    required Color bg,
  }) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFE2E8F0)),
        ),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
              decoration: BoxDecoration(
                color: bg,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  color: color,
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: Color(0xFF475569),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRemindersTab() {
    if (_reminders.isEmpty) {
      return _buildEmptyState(
        icon: Icons.alarm_on_rounded,
        title: 'لا توجد مهام أو تذكيرات بعد',
        subtitle: 'أضف أول مهمة أو موعد دواء وسنقوم بتذكيرك في الوقت المحدد.',
        actionLabel: 'إضافة تذكير مهمة',
        onAction: () => _showAddOrEditDialog(isNote: false),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadItems,
      color: const Color(0xFF00B4D8),
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 160),
        itemCount: _reminders.length,
        separatorBuilder: (_, _) => const SizedBox(height: 10),
        itemBuilder: (context, idx) {
          final item = _reminders[idx];
          final (typeLabel, typeBg, typeColor, typeIcon) = _typeMeta(
            item.reminderType,
          );

          return Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: item.isCompleted ? const Color(0xFFF8FAFC) : Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: item.isCompleted
                    ? const Color(0xFFBBF7D0)
                    : const Color(0xFFE2E8F0),
              ),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF0F172A).withValues(alpha: 0.03),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Complete toggle button
                InkWell(
                  onTap: () => _toggleComplete(item),
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    width: 28,
                    height: 28,
                    margin: const EdgeInsets.only(top: 2),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: item.isCompleted
                          ? const Color(0xFF10B981)
                          : Colors.transparent,
                      border: Border.all(
                        color: item.isCompleted
                            ? const Color(0xFF10B981)
                            : const Color(0xFF94A3B8),
                        width: 2,
                      ),
                    ),
                    child: item.isCompleted
                        ? const Icon(
                            Icons.check_rounded,
                            size: 17,
                            color: Colors.white,
                          )
                        : null,
                  ),
                ),
                const SizedBox(width: 12),

                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: typeBg,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(typeIcon, size: 12, color: typeColor),
                                const SizedBox(width: 4),
                                Text(
                                  typeLabel,
                                  style: TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 10.5,
                                    fontWeight: FontWeight.bold,
                                    color: typeColor,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              _recurrenceLabel(item.recurrence),
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF475569),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        item.title,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: item.isCompleted
                              ? const Color(0xFF94A3B8)
                              : const Color(0xFF0F172A),
                          decoration: item.isCompleted
                              ? TextDecoration.lineThrough
                              : null,
                        ),
                      ),
                      if (item.description != null &&
                          item.description!.trim().isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          item.description!,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12,
                            color: Color(0xFF64748B),
                          ),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          const Icon(
                            Icons.schedule_rounded,
                            size: 14,
                            color: Color(0xFF0284C7),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '${_formatDate(item.targetTime)} • ${_formatTime(item.targetTime)}',
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11.5,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0284C7),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                Column(
                  children: [
                    IconButton(
                      icon: const Icon(
                        Icons.edit_rounded,
                        size: 18,
                        color: Color(0xFF0284C7),
                      ),
                      onPressed: () =>
                          _showAddOrEditDialog(isNote: false, existing: item),
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.delete_outline_rounded,
                        size: 18,
                        color: Color(0xFFEF4444),
                      ),
                      onPressed: () => _deleteItem(item),
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildNotesTab() {
    if (_notes.isEmpty) {
      return _buildEmptyState(
        icon: Icons.sticky_note_2_outlined,
        title: 'لا توجد ملاحظات محفوظة بعد',
        subtitle: 'سجّل أفكارك وملاحظاتك السريعة هنا لتحفظ مباشرة في حسابك.',
        actionLabel: 'إضافة ملاحظة جديدة',
        onAction: () => _showAddOrEditDialog(isNote: true),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadItems,
      color: const Color(0xFFD97706),
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 160),
        itemCount: _notes.length,
        separatorBuilder: (_, _) => const SizedBox(height: 10),
        itemBuilder: (context, idx) {
          final note = _notes[idx];
          return Container(
            padding: const EdgeInsets.all(15),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFFFDE68A), width: 1.2),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF0F172A).withValues(alpha: 0.03),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF3C7),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(
                        Icons.sticky_note_2_rounded,
                        size: 17,
                        color: Color(0xFFD97706),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        note.title,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 14.5,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.copy_rounded,
                        size: 17,
                        color: Color(0xFF64748B),
                      ),
                      onPressed: () {
                        final copyText =
                            (note.description != null &&
                                note.description!.isNotEmpty)
                            ? '${note.title}\n${note.description}'
                            : note.title;
                        Clipboard.setData(ClipboardData(text: copyText));
                        showSuccessSnackbar(context, 'تم نسخ الملاحظة.');
                      },
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.edit_rounded,
                        size: 17,
                        color: Color(0xFF0284C7),
                      ),
                      onPressed: () =>
                          _showAddOrEditDialog(isNote: true, existing: note),
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.delete_outline_rounded,
                        size: 18,
                        color: Color(0xFFEF4444),
                      ),
                      onPressed: () => _deleteItem(note),
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                    ),
                  ],
                ),
                if (note.description != null &&
                    note.description!.trim().isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFFBEB),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      note.description!,
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12.5,
                        color: Color(0xFF334155),
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                Text(
                  '${_formatDate(note.createdAt)} • ${_formatTime(note.createdAt)}',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10.5,
                    color: Color(0xFF94A3B8),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmptyState({
    required IconData icon,
    required String title,
    required String subtitle,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(28, 24, 28, 120),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFFE0F2FE),
                borderRadius: BorderRadius.circular(22),
              ),
              child: Icon(icon, size: 36, color: const Color(0xFF0284C7)),
            ),
            const SizedBox(height: 14),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 15.5,
                fontWeight: FontWeight.w800,
                color: Color(0xFF0F172A),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 12.5,
                color: Color(0xFF64748B),
              ),
            ),
            const SizedBox(height: 18),
            ElevatedButton.icon(
              onPressed: onAction,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: Text(
                actionLabel,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF00B4D8),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 12,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                elevation: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isNotesTab = _tabController.index == 1;
    final t = LocaleService.instance.tr;

    return Directionality(
      textDirection: LocaleService.instance.textDirection,
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        floatingActionButton: Padding(
          padding: const EdgeInsets.only(bottom: 92),
          child: FloatingActionButton.extended(
            heroTag: 'notes_reminders_fab',
            onPressed: () => _showAddOrEditDialog(isNote: isNotesTab),
            backgroundColor: isNotesTab
                ? const Color(0xFFD97706)
                : const Color(0xFF00B4D8),
            foregroundColor: Colors.white,
            elevation: 4,
            icon: Icon(
              isNotesTab ? Icons.note_add_rounded : Icons.alarm_add_rounded,
              size: 20,
            ),
            label: Text(
              isNotesTab
                  ? t('إضافة ملاحظة', 'Add Note')
                  : t('تذكير جديد', 'New Reminder'),
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.bold,
                fontSize: 13,
              ),
            ),
          ),
        ),
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              _buildHeader(),
              _buildStatsStrip(),

              // Clean Pill TabBar
              Container(
                margin: const EdgeInsets.fromLTRB(16, 8, 16, 6),
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: TabBar(
                  controller: _tabController,
                  indicator: BoxDecoration(
                    color: const Color(0xFF0F172A),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  indicatorSize: TabBarIndicatorSize.tab,
                  dividerColor: Colors.transparent,
                  labelColor: Colors.white,
                  unselectedLabelColor: const Color(0xFF475569),
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                  unselectedLabelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                  tabs: [
                    Tab(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.alarm_rounded, size: 17),
                          const SizedBox(width: 6),
                          Text(
                            t(
                              'تذكير المهام (${_reminders.length})',
                              'Reminders (${_reminders.length})',
                            ),
                          ),
                        ],
                      ),
                    ),
                    Tab(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.sticky_note_2_rounded, size: 17),
                          const SizedBox(width: 6),
                          Text(
                            t(
                              'الملاحظات (${_notes.length})',
                              'Notes (${_notes.length})',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              if (_error != null)
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 6,
                  ),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF2F2),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFFECACA)),
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.error_outline_rounded,
                          color: Color(0xFFDC2626),
                          size: 18,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _error!,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              color: Color(0xFF991B1B),
                            ),
                          ),
                        ),
                        IconButton(
                          icon: const Icon(
                            Icons.refresh_rounded,
                            size: 18,
                            color: Color(0xFF0284C7),
                          ),
                          onPressed: _loadItems,
                          constraints: const BoxConstraints(),
                          padding: EdgeInsets.zero,
                        ),
                      ],
                    ),
                  ),
                ),

              Expanded(
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(
                          color: Color(0xFF00B4D8),
                        ),
                      )
                    : TabBarView(
                        controller: _tabController,
                        children: [_buildRemindersTab(), _buildNotesTab()],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
