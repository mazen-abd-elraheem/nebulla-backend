import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../services/locale_service.dart';
import '../services/storage_service.dart';
import '../widgets/nebula_side_menu.dart';
import '../widgets/common_widgets.dart';

/// Dedicated Persona Memory & Specifications Screen
/// - Displays each persona fetched from the backend
/// - Displays full specifications: prompt, dialect, language mix, active status
/// - Displays RAG memory items with add/delete support connected to FastAPI backend
/// - Includes transparent Menu button on left and Exit arrow on right
class PersonaMemorySpecsScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;
  final bool isActive;

  const PersonaMemorySpecsScreen({
    super.key,
    this.onNavigate,
    this.isActive = false,
  });

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

  @override
  void didUpdateWidget(covariant PersonaMemorySpecsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      _loadData();
    }
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
      final isConnError = e.toString().contains('SocketException') ||
          e.toString().contains('refused') ||
          e.toString().contains('1225');
      setState(() {
        _error = isConnError
            ? 'تعذر الاتصال بخادم نيبولا (127.0.0.1:8000)\nيرجى التأكد من تشغيل خادم الباك إند والمحاولة مجدداً.'
            : 'تعذر تحميل الشخصيات: $e';
        _loading = false;
        if (_personalities.isEmpty) {
          final u = StorageService.instance.getUser();
          final twinName = u != null && u.fullName.isNotEmpty
              ? u.fullName
              : 'المستخدم';
          _personalities = [
            Personality(
              id: 1,
              name: twinName,
              description:
                  'التوأم الرقمي الرسمي لمستخدم نيبولا، قادر على التفاعل الصوتي والتحدث بأسلوبك ولهجتك.',
              dialect: 'اللهجة المصرية والإنجليزية',
              languageMix: 'ar-EG',
              systemPrompt:
                  'أنت $twinName والمساعد الذكي الرسمي المتقدم لنظام نيبولا.',
              isActive: true,
            ),
          ];
        }
      });
    }
  }

  Future<void> _loadMemoriesForSelected() async {
    setState(() => _loadingMemories = true);
    try {
      // Fetch all memories belonging to the logged-in user directly from FastAPI backend
      final mems = await _repo.getMemories();
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
      builder: (ctx) => Theme(
        data: ThemeData.light().copyWith(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF00B4D8),
            brightness: Brightness.light,
          ),
        ),
        child: StatefulBuilder(
          builder: (ctx, setDialogState) => Directionality(
            textDirection: LocaleService.instance.textDirection,
            child: AlertDialog(
              backgroundColor: Colors.white,
              surfaceTintColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
              title: Row(
                children: [
                  const Icon(Icons.psychology_rounded, color: Color(0xFF00B4D8)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'إضافة معلومة لذاكرة ${persona.name}',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                        color: Color(0xFF0F172A),
                      ),
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
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF334155),
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: textCtrl,
                    maxLines: 3,
                    cursorColor: const Color(0xFF00B4D8),
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0F172A),
                    ),
                    decoration: InputDecoration(
                      hintText: 'مثال: مكان مفاتيح البيت في الدرج الأيمن...',
                      hintStyle: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11.5,
                        color: Color(0xFF94A3B8),
                      ),
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: Color(0xFFCBD5E1), width: 1.2),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: Color(0xFF00B4D8), width: 1.6),
                      ),
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
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF334155),
                        ),
                      ),
                      const SizedBox(width: 8),
                      DropdownButton<int>(
                        value: importance,
                        dropdownColor: Colors.white,
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0F172A),
                        ),
                        items: List.generate(10, (i) => i + 1)
                            .map(
                              (val) => DropdownMenuItem(
                                value: val,
                                child: Text('$val'),
                              ),
                            )
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
                      showSuccessSnackbar(
                        context,
                        'تمت إضافة المعلومة للذاكرة',
                      );
                      _loadMemoriesForSelected();
                    }
                  } catch (e) {
                    if (mounted) {
                      showErrorSnackbar(context, 'فشل الحفظ: $e');
                    }
                  }
                },
                child: const Text(
                  'حفظ في الذاكرة',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
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

  Future<void> _deleteMemory(int memoryId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: AlertDialog(
          backgroundColor: Colors.white,
          surfaceTintColor: Colors.transparent,
          title: const Text(
            'حذف المعلومة',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontWeight: FontWeight.w800,
              color: Color(0xFF0F172A),
            ),
          ),
          content: const Text(
            'هل أنت متأكد من حذف هذه المعلومة من الذاكرة؟',
            style: TextStyle(
              fontFamily: 'Cairo',
              fontWeight: FontWeight.w600,
              color: Color(0xFF334155),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
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
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFEF4444),
                foregroundColor: Colors.white,
              ),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text(
                'حذف',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
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
        activeIndex: 3,
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
                      LocaleService.instance.tr(
                        'ذاكرة ومواصفات الشخصية',
                        'Memory & Persona Specs',
                      ),
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
                        widget.onNavigate!(2); // return to home (index 2)
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
                      children: [leftSide, titleWidget, rightSide],
                    ),
                  );
                },
              ),
            ),

            // 2. Main Content
            Expanded(
              child: _loading
                  ? const Center(
                      child: CircularProgressIndicator(
                        color: Color(0xFF00B4D8),
                      ),
                    )
                  : _error != null && _personalities.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 64,
                              height: 64,
                              decoration: BoxDecoration(
                                color: const Color(0xFFFEE2E2),
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(
                                Icons.wifi_off_rounded,
                                color: Color(0xFFDC2626),
                                size: 32,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              _error!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                color: Color(0xFF991B1B),
                                fontSize: 13,
                                height: 1.5,
                              ),
                            ),
                            const SizedBox(height: 16),
                            ElevatedButton.icon(
                              onPressed: _loadData,
                              icon: const Icon(Icons.refresh_rounded, size: 18),
                              label: const Text(
                                'إعادة المحاولة',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF00B4D8),
                                foregroundColor: Colors.white,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 24,
                                  vertical: 12,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                  : Column(
                      children: [
                        if (_error != null)
                          Container(
                            margin: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 6,
                            ),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 10,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFEF2F2),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: const Color(0xFFFECACA),
                              ),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.info_outline_rounded,
                                  color: Color(0xFFDC2626),
                                  size: 18,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _error!,
                                    style: const TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 11,
                                      color: Color(0xFF991B1B),
                                    ),
                                  ),
                                ),
                                InkWell(
                                  onTap: _loadData,
                                  child: const Padding(
                                    padding: EdgeInsets.all(4),
                                    child: Icon(
                                      Icons.refresh_rounded,
                                      color: Color(0xFF00B4D8),
                                      size: 18,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        Expanded(child: _buildPersonaContent()),
                      ],
                    ),
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
      child: RefreshIndicator(
        onRefresh: _loadData,
        color: const Color(0xFF00B4D8),
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
                            fontWeight: isSel
                                ? FontWeight.bold
                                : FontWeight.w600,
                            color: isSel
                                ? Colors.white
                                : const Color(0xFF1E293B),
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

          // RAM & System Memory Card (moved from Personas screen)
          _buildRamCard(),
          const SizedBox(height: 16),

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
                            Text(
                              LocaleService.instance.tr(
                                'الذاكرة الشخصية',
                                'Personal Memory (RAG)',
                              ),
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 15,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                            Text(
                              LocaleService.instance.tr(
                                '${_memories.length} حقائق مسجلة في ذاكرتك الخاصة',
                                '${_memories.length} facts stored in your memory',
                              ),
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
                          horizontal: 10,
                          vertical: 6,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      onPressed: _showAddMemoryDialog,
                      icon: const Icon(Icons.add_rounded, size: 15),
                      label: Text(
                        LocaleService.instance.tr('إضافة معلومة', 'Add Fact'),
                        style: const TextStyle(fontFamily: 'Cairo', fontSize: 11),
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
                        strokeWidth: 2,
                        color: Color(0xFF00B4D8),
                      ),
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
                        const Icon(
                          Icons.psychology_outlined,
                          size: 38,
                          color: Color(0xFF94A3B8),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'لا توجد معلومات محفوظة في ذاكرتك الشخصية بعد.',
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
                              fontFamily: 'Cairo',
                              fontWeight: FontWeight.bold,
                            ),
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
          const SizedBox(height: 18),
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
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFDCFCE7),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFF86EFAC)),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.check_circle_rounded,
                              size: 14,
                              color: Color(0xFF16A34A),
                            ),
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
                            horizontal: 10,
                            vertical: 6,
                          ),
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
                if (persona.description != null &&
                    persona.description!.isNotEmpty) ...[
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
                      label:
                          'اللهجة: ${persona.dialect == 'cairo' ? 'قاهرية عامية' : persona.dialect}',
                    ),
                    _buildSpecChip(
                      icon: Icons.translate_rounded,
                      label:
                          'اللغات: ${persona.languageMix == 'ar_en' ? 'عربي + مصطلحات إنجليزي' : persona.languageMix}',
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
                          Icon(
                            Icons.terminal_rounded,
                            size: 14,
                            color: Color(0xFF0284C7),
                          ),
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
          const SizedBox(height: 110),
        ],
      ),
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

  Widget _buildRamCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 14,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Flexible(
                child: Text(
                  'ذاكرة الوصول العشوائي',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(20),
                  border:
                      Border.all(color: const Color(0xFFA7F3D0), width: 1.2),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: Color(0xFF10B981),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Text(
                      'افضل 60%',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF059669),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFF1F5F9)),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 62,
                  height: 62,
                  child: CustomPaint(
                    painter: _GaugeArcPainter(
                      percentage: 0.60,
                      activeColor: const Color(0xFF06B6D4),
                      trackColor: const Color(0xFFE2E8F0),
                    ),
                    child: const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            '60%',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 14,
                              fontWeight: FontWeight.w900,
                              color: Color(0xFF0F172A),
                              height: 1.05,
                            ),
                          ),
                          Text(
                            'USED',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 8,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF94A3B8),
                              letterSpacing: 0.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Flexible(
                            child: Text(
                              'الاستهلاك / السعة:',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF64748B),
                              ),
                            ),
                          ),
                          SizedBox(width: 6),
                          Text(
                            '38.4 / 64 GB',
                            textDirection: TextDirection.ltr,
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12.5,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF0F172A),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: const LinearProgressIndicator(
                          value: 0.60,
                          minHeight: 6.5,
                          backgroundColor: Color(0xFFE2E8F0),
                          valueColor:
                              AlwaysStoppedAnimation<Color>(Color(0xFF06B6D4)),
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Flexible(
                            child: Text(
                              'نقل البيانات: 800 GB/s',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF334155),
                              ),
                            ),
                          ),
                          SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              'الاستجابة: 0.2ms',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF10B981),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GaugeArcPainter extends CustomPainter {
  final double percentage;
  final Color activeColor;
  final Color trackColor;

  _GaugeArcPainter({
    required this.percentage,
    required this.activeColor,
    required this.trackColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    const strokeWidth = 6.0;
    final rect = Offset(strokeWidth / 2, strokeWidth / 2) &
        Size(size.width - strokeWidth, size.height - strokeWidth);

    const startAngle = 135 * math.pi / 180;
    const sweepTotal = 270 * math.pi / 180;

    final trackPaint = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final activePaint = Paint()
      ..color = activeColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(rect, startAngle, sweepTotal, false, trackPaint);
    canvas.drawArc(
      rect,
      startAngle,
      sweepTotal * percentage,
      false,
      activePaint,
    );
  }

  @override
  bool shouldRepaint(covariant _GaugeArcPainter oldDelegate) {
    return oldDelegate.percentage != percentage ||
        oldDelegate.activeColor != activeColor ||
        oldDelegate.trackColor != trackColor;
  }
}
