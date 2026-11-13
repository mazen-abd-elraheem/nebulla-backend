import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../services/locale_service.dart';
import '../widgets/nebula_side_menu.dart';
import '../widgets/common_widgets.dart';

/// Dedicated Persona Memory & Specifications Screen
/// - Displays each persona fetched from the backend
/// - Displays full specifications: prompt, dialect, language mix, active status
/// - Displays RAG memory items with add/delete support connected to FastAPI backend
/// - Includes transparent Menu button on left and Exit arrow on right
class PersonaMemorySpecsScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const PersonaMemorySpecsScreen({super.key, this.onNavigate});

  @override
  State<PersonaMemorySpecsScreen> createState() =>
      _PersonaMemorySpecsScreenState();
}

class _PersonaMemorySpecsScreenState extends State<PersonaMemorySpecsScreen> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final _repo = NebulaRepository.instance;

  bool _loading = true;
  String? _error;
  List<Personality> _personalities = [];
  int _selectedPersonaIndex = 0;

  bool _loadingMemories = false;
  List<Memory> _memories = [];

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final list = await _repo.getPersonalities();
      if (!mounted) return;

      setState(() {
        _personalities = list;
        _loading = false;
        // Default to active persona if available
        final activeIdx = list.indexWhere((p) => p.isActive);
        _selectedPersonaIndex = activeIdx >= 0 ? activeIdx : 0;
      });

      if (_personalities.isNotEmpty) {
        await _loadMemoriesForSelected();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'تعذر تحميل الشخصيات: $e';
        _loading = false;
      });
    }
  }

  Future<void> _loadMemoriesForSelected() async {
    if (_personalities.isEmpty) return;
    final persona = _personalities[_selectedPersonaIndex];

    setState(() => _loadingMemories = true);
    try {
      final mems = await _repo.getMemories(persona.id);
      if (mounted) {
        setState(() {
          _memories = mems;
          _loadingMemories = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loadingMemories = false);
      }
    }
  }

  Future<void> _activateCurrentPersona() async {
    if (_personalities.isEmpty) return;
    final persona = _personalities[_selectedPersonaIndex];
    try {
      await _repo.activatePersonality(persona.id);
      if (mounted) {
        showSuccessSnackbar(context, 'تم تفعيل شخصية "${persona.name}" بنجاح');
        _loadData();
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(context, 'تعذر تفعيل الشخصية: $e');
      }
    }
  }

  Future<void> _showAddMemoryDialog() async {
    if (_personalities.isEmpty) return;
    final persona = _personalities[_selectedPersonaIndex];
    final textCtrl = TextEditingController();
    int importance = 5;

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => Directionality(
          textDirection: LocaleService.instance.textDirection,
          child: AlertDialog(
            backgroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(
              children: [
                const Icon(Icons.psychology_rounded, color: Color(0xFF00B4D8)),
                const SizedBox(width: 8),
                Text(
                  'إضافة معلومة لذاكرة ${persona.name}',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'المعلومة أو الحقيقة التي سيتذكرها الذكاء الاصطناعي:',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    color: Color(0xFF475569),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: textCtrl,
                  maxLines: 3,
                  style: const TextStyle(fontFamily: 'Cairo', fontSize: 13),
                  decoration: InputDecoration(
                    hintText: 'مثال: مكان مفاتيح البيت في الدرج الأيمن...',
                    hintStyle: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11.5,
                      color: Color(0xFF94A3B8),
                    ),
                    filled: true,
                    fillColor: const Color(0xFFF8FAFC),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFFCBD5E1)),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Text(
                      'مستوى الأهمية (1-10):',
                      style: TextStyle(fontFamily: 'Cairo', fontSize: 12),
                    ),
                    const SizedBox(width: 8),
                    DropdownButton<int>(
                      value: importance,
                      items: List.generate(10, (i) => i + 1)
                          .map((val) => DropdownMenuItem(
                                value: val,
                                child: Text('$val'),
                              ))
                          .toList(),
                      onChanged: (val) {
                        if (val != null) {
                          setDialogState(() => importance = val);
                        }
                      },
                    ),
                  ],
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: () async {
                  final text = textCtrl.text.trim();
                  if (text.isEmpty) return;
                  Navigator.pop(ctx);
                  try {
                    await _repo.addMemory(text, persona.id, importance);
                    if (mounted) {
                      showSuccessSnackbar(context, 'تمت إضافة المعلومة للذاكرة');
                      _loadMemoriesForSelected();
                    }
                  } catch (e) {
                    if (mounted) {
                      showErrorSnackbar(context, 'فشل الحفظ: $e');
                    }
                  }
                },
                child: const Text('حفظ في الذاكرة',
                    style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _deleteMemory(int memoryId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        title: const Text('حذف المعلومة',
            style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold)),
        content: const Text('هل أنت متأكد من حذف هذه المعلومة من الذاكرة؟',
            style: TextStyle(fontFamily: 'Cairo')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('إلغاء', style: TextStyle(fontFamily: 'Cairo')),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFEF4444),
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('حذف', style: TextStyle(fontFamily: 'Cairo')),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await _repo.deleteMemory(memoryId);
        if (mounted) {
          showSuccessSnackbar(context, 'تم حذف المعلومة بنجاح');
          _loadMemoriesForSelected();
        }
      } catch (e) {
        if (mounted) {
          showErrorSnackbar(context, 'تعذر الحذف: $e');
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = LocaleService.instance.isArabic;

    final sidebar = Drawer(
      backgroundColor: Colors.transparent,
      elevation: 0,
      child: NebulaSideMenu(
        activeIndex: 2,
        onNavigate: (idx) {
          if (isArabic) {
            _scaffoldKey.currentState?.closeEndDrawer();
          } else {
            _scaffoldKey.currentState?.closeDrawer();
          }
          widget.onNavigate?.call(idx);
        },
        onClose: () {
          if (isArabic) {
            _scaffoldKey.currentState?.closeEndDrawer();
          } else {
            _scaffoldKey.currentState?.closeDrawer();
          }
        },
      ),
    );

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: const Color(0xFFF8FAFC),
      drawer: isArabic ? null : sidebar,
      endDrawer: isArabic ? sidebar : null,
      body: SafeArea(
        child: Column(
          children: [
            // 1. Top Header Row (Menu on LEFT, Title in CENTER, Exit on RIGHT)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Builder(
                builder: (context) {
                  // Transparent Menu Button
                  final menuBtn = GestureDetector(
                    onTap: () {
                      if (isArabic) {
                        _scaffoldKey.currentState?.openEndDrawer();
                      } else {
                        _scaffoldKey.currentState?.openDrawer();
                      }
                    },
                    behavior: HitTestBehavior.opaque,
                    child: Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: const Color(0xFFCBD5E1),
                          width: 1.4,
                        ),
                      ),
                      child: const Icon(
                        Icons.menu_rounded,
                        color: Color(0xFF0F172A),
                        size: 22,
                      ),
                    ),
                  );

                  // Centered Title
                  final titleWidget = Expanded(
                    child: Text(
                      'ذاكرة ومواصفات الشخصية',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                  );

                  // Transparent Exit / Back Button
                  final exitBtn = GestureDetector(
                    onTap: () {
                      if (widget.onNavigate != null) {
                        widget.onNavigate!(0);
                      } else if (Navigator.canPop(context)) {
                        Navigator.pop(context);
                      }
                    },
                    behavior: HitTestBehavior.opaque,
                    child: Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: const Color(0xFFCBD5E1),
                          width: 1.4,
                        ),
                      ),
                      child: Icon(
                        isArabic
                            ? Icons.arrow_forward_rounded
                            : Icons.arrow_back_rounded,
                        color: const Color(0xFF0F172A),
                        size: 20,
                      ),
                    ),
                  );

                  final leftSide = isArabic ? menuBtn : exitBtn;
                  final rightSide = isArabic ? exitBtn : menuBtn;

                  return Directionality(
                    textDirection: TextDirection.ltr,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        leftSide,
                        titleWidget,
                        rightSide,
                      ],
                    ),
                  );
                },
              ),
            ),

            // 2. Main Content
            Expanded(
              child: _loading
                  ? const Center(
                      child: CircularProgressIndicator(color: Color(0xFF00B4D8)),
                    )
                  : _error != null
                      ? Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                _error!,
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  color: Color(0xFFEF4444),
                                ),
                              ),
                              const SizedBox(height: 12),
                              ElevatedButton(
                                onPressed: _loadData,
                                child: const Text('إعادة المحاولة',
                                    style: TextStyle(fontFamily: 'Cairo')),
                              ),
                            ],
                          ),
                        )
                      : _buildPersonaContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPersonaContent() {
    if (_personalities.isEmpty) {
      return const Center(
        child: Text(
          'لا توجد شخصيات مسجلة حالياً',
          style: TextStyle(fontFamily: 'Cairo', fontSize: 14),
        ),
      );
    }

    final persona = _personalities[_selectedPersonaIndex];

    return Directionality(
      textDirection: LocaleService.instance.textDirection,
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        children: [
          // A. Horizontal Persona Selector Chips
          SizedBox(
            height: 46,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: _personalities.length,
              separatorBuilder: (ctx, i) => const SizedBox(width: 8),
              itemBuilder: (context, idx) {
                final p = _personalities[idx];
                final isSel = idx == _selectedPersonaIndex;

                return GestureDetector(
                  onTap: () {
                    setState(() => _selectedPersonaIndex = idx);
                    _loadMemoriesForSelected();
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    decoration: BoxDecoration(
                      color: isSel ? const Color(0xFF00B4D8) : Colors.white,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: isSel
                            ? const Color(0xFF00B4D8)
                            : const Color(0xFFE2E8F0),
                        width: 1.4,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: isSel
                              ? const Color(0xFF00B4D8).withValues(alpha: 0.25)
                              : Colors.black.withValues(alpha: 0.02),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          p.isActive
                              ? Icons.verified_rounded
                              : Icons.account_circle_rounded,
                          size: 18,
                          color: isSel ? Colors.white : const Color(0xFF0284C7),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          p.name,
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12.5,
                            fontWeight:
                                isSel ? FontWeight.bold : FontWeight.w600,
                            color: isSel ? Colors.white : const Color(0xFF1E293B),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 16),

          // B. Specifications Card (المواصفات)
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFE2E8F0)),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 14,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: const Color(0xFFE0F2FE),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(
                            Icons.tune_rounded,
                            color: Color(0xFF0284C7),
                            size: 20,
                          ),
                        ),
                        const SizedBox(width: 10),
                        const Text(
                          'مواصفات الشخصية',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 15,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                      ],
                    ),
                    if (persona.isActive)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFFDCFCE7),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFF86EFAC)),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.check_circle_rounded,
                                size: 14, color: Color(0xFF16A34A)),
                            SizedBox(width: 4),
                            Text(
                              'الشخصية النشطة',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF16A34A),
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF00B4D8),
                          foregroundColor: Colors.white,
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 6),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        onPressed: _activateCurrentPersona,
                        icon: const Icon(Icons.flash_on_rounded, size: 14),
                        label: const Text(
                          'تفعيل',
                          style: TextStyle(fontFamily: 'Cairo', fontSize: 11.5),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 14),

                // Name & Tagline
                Text(
                  persona.name,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF0F172A),
                  ),
                ),
                if (persona.description != null && persona.description!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    persona.description!,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 12.5,
                      color: Color(0xFF64748B),
                    ),
                  ),
                ],
                const SizedBox(height: 12),

                // Specs Badges
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    _buildSpecChip(
                      icon: Icons.language_rounded,
                      label: 'اللهجة: ${persona.dialect == 'cairo' ? 'قاهرية عامية' : persona.dialect}',
                    ),
                    _buildSpecChip(
                      icon: Icons.translate_rounded,
                      label: 'اللغات: ${persona.languageMix == 'ar_en' ? 'عربي + مصطلحات إنجليزي' : persona.languageMix}',
                    ),
                    if (persona.voiceSamplePath != null)
                      _buildSpecChip(
                        icon: Icons.record_voice_over_rounded,
                        label: 'عينة صوتية مسجلة',
                        color: const Color(0xFF10B981),
                      ),
                  ],
                ),
                const SizedBox(height: 14),

                // System Prompt Accordion
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.terminal_rounded, size: 14, color: Color(0xFF0284C7)),
                          SizedBox(width: 6),
                          Text(
                            'توجيهات النظام (System Prompt):',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11.5,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF334155),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        persona.systemPrompt.isEmpty
                            ? 'لا توجد توجيهات إضافية'
                            : persona.systemPrompt,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          color: Color(0xFF475569),
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),

          // C. Memory Card (الذاكرة ومستودع المعرفة RAG)
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFE2E8F0)),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 14,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: const Color(0xFFFEF3C7),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(
                            Icons.memory_rounded,
                            color: Color(0xFFD97706),
                            size: 20,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'ذاكرة الشخصية (RAG)',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 15,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                            Text(
                              '${_memories.length} حقائق مسجلة بالباك إند',
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                color: Color(0xFF64748B),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF0F172A),
                        foregroundColor: Colors.white,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 6),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      onPressed: _showAddMemoryDialog,
                      icon: const Icon(Icons.add_rounded, size: 15),
                      label: const Text(
                        'إضافة معلومة',
                        style: TextStyle(fontFamily: 'Cairo', fontSize: 11),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                if (_loadingMemories)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Color(0xFF00B4D8)),
                    ),
                  )
                else if (_memories.isEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: const Color(0xFFE2E8F0),
                        style: BorderStyle.solid,
                      ),
                    ),
                    child: Column(
                      children: [
                        const Icon(Icons.psychology_outlined,
                            size: 38, color: Color(0xFF94A3B8)),
                        const SizedBox(height: 8),
                        const Text(
                          'لا توجد معلومات محفوظة في ذاكرة هذه الشخصية بعد.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12.5,
                            color: Color(0xFF64748B),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextButton.icon(
                          onPressed: _showAddMemoryDialog,
                          icon: const Icon(Icons.add_rounded, size: 16),
                          label: const Text(
                            'أضف أول معلومة الآن',
                            style: TextStyle(
                                fontFamily: 'Cairo', fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ),
                  )
                else
                  ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _memories.length,
                    separatorBuilder: (ctx, i) => const SizedBox(height: 8),
                    itemBuilder: (context, idx) {
                      final mem = _memories[idx];
                      return Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0xFFE2E8F0)),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              margin: const EdgeInsets.only(top: 2),
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(
                                color: Color(0xFF00B4D8),
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    mem.content,
                                    style: const TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 12.5,
                                      color: Color(0xFF1E293B),
                                      height: 1.35,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Row(
                                    children: [
                                      Text(
                                        'الأهمية: ${mem.importance}/10 • المصدر: ${mem.source == 'system' ? 'نظام' : 'يدوي'}',
                                        style: const TextStyle(
                                          fontFamily: 'Cairo',
                                          fontSize: 10.5,
                                          color: Color(0xFF94A3B8),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              icon: const Icon(
                                Icons.delete_outline_rounded,
                                size: 18,
                                color: Color(0xFF94A3B8),
                              ),
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                              onPressed: () => _deleteMemory(mem.id),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _buildSpecChip({
    required IconData icon,
    required String label,
    Color color = const Color(0xFF0284C7),
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Cairo',
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
