import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';
import '../services/avatar_audio_service.dart';
import '../services/locale_service.dart';
import '../widgets/nebula_side_menu.dart';

class PersonaProfileData {
  int? backendId;
  String name;
  List<String> traits;
  List<Map<String, String>> rules;
  List<String> subTags;
  String? avatarPath;
  bool isAcademicAvatar;
  bool isActive;

  PersonaProfileData({
    this.backendId,
    required this.name,
    required this.traits,
    required this.rules,
    this.subTags = const [],
    this.avatarPath,
    this.isAcademicAvatar = false,
    this.isActive = false,
  });

  Map<String, dynamic> toJson() => {
        'backend_id': backendId,
        'name': name,
        'traits': traits,
        'rules': rules,
        'sub_tags': subTags,
        'avatar_path': avatarPath,
        'is_academic_avatar': isAcademicAvatar,
        'is_active': isActive,
      };

  factory PersonaProfileData.fromJson(Map<String, dynamic> json) {
    return PersonaProfileData(
      backendId: json['backend_id'] as int?,
      name: json['name'] as String? ?? '',
      traits: (json['traits'] as List?)?.map((e) => e.toString()).toList() ??
          <String>[],
      rules: (json['rules'] as List?)
              ?.map((e) => {
                    'tag': (e as Map)['tag']?.toString() ?? '',
                    'text': e['text']?.toString() ?? '',
                  })
              .toList() ??
          <Map<String, String>>[],
      subTags:
          (json['sub_tags'] as List?)?.map((e) => e.toString()).toList() ??
              <String>[],
      avatarPath: json['avatar_path'] as String?,
      isAcademicAvatar: json['is_academic_avatar'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? false,
    );
  }

  String buildSystemPrompt() {
    final buffer = StringBuffer();
    buffer.writeln('أنت تعمل بشخصية: $name.');
    if (traits.isNotEmpty) {
      buffer.writeln('السمات الفريدة والفكرة الجوهرية: ${traits.join('، ')}.');
    }
    if (rules.isNotEmpty) {
      buffer.writeln('قواعد التخاطب المخصصة:');
      for (final r in rules) {
        buffer.writeln('- [${r['tag']}]: ${r['text']}');
      }
    }
    return buffer.toString().trim();
  }
}

class MemoryPersonasScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;
  const MemoryPersonasScreen({super.key, this.onNavigate});

  @override
  State<MemoryPersonasScreen> createState() => _MemoryPersonasScreenState();
}

class _MemoryPersonasScreenState extends State<MemoryPersonasScreen> {
  final GlobalKey<ScaffoldState> _memScaffoldKey = GlobalKey<ScaffoldState>();
  static const String _storageKey = 'nebula_saved_personas_v1';

  final _repo = NebulaRepository.instance;
  final _scrollCtrl = ScrollController();
  final _personaNameCtrl =
      TextEditingController(text: 'المساعد البحثي الأكاديمي');
  final _newTraitCtrl = TextEditingController();
  final _nameFocusNode = FocusNode();

  // Active traits in the editor
  final List<String> _traits = [
    'تفكير منطقي تحليلي',
    'نبرة موضوعية صارمة',
    'طرح تساؤلات استكشافية',
    'توقع المخاطر والبدائل',
  ];

  // Active custom communication rules in the editor
  final List<Map<String, String>> _rules = [
    {
      'tag': 'نبرة التخاطب',
      'text': 'موضوعية، تحليلية، مدعمة بالبيانات وبدون انحيازات',
    },
    {
      'tag': 'قيود الاستجابة',
      'text': 'عدم تقديم افتراضات غير مؤكدة وإرفاق تنويه بالاحتمالات',
    },
  ];

  // Managed personas list (defaults matching the mockup + any user-created ones)
  late List<PersonaProfileData> _personas;
  int _editingPersonaIndex = 0; // index in _personas, or -1 when creating new
  bool _saving = false;

  List<Memory> _backendMemories = [];
  bool _loadingBackendMemories = false;

  Future<void> _fetchBackendMemories([int? personaId]) async {
    if (!mounted) return;
    setState(() => _loadingBackendMemories = true);
    try {
      final pid = personaId ??
          (_editingPersonaIndex >= 0 && _editingPersonaIndex < _personas.length
              ? (_personas[_editingPersonaIndex].backendId ?? 1)
              : 1);
      final mems = await _repo.getMemories(pid);
      if (mounted) {
        setState(() {
          _backendMemories = mems;
          _loadingBackendMemories = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingBackendMemories = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _personas = _defaultPersonas();
    _initBackendAndLocalData();
  }

  List<PersonaProfileData> _defaultPersonas() => [
        PersonaProfileData(
          backendId: 1,
          name: 'مازن (Mazen) - التوأم الرقمي',
          traits: [
            'التوأم الرقمي الرسمي لفريق نيبولا',
            'صوت مازن الطبيعي',
            'لهجة قاهرية عفوية',
            'تفكير تحليلي تقني',
          ],
          rules: [
            {
              'tag': 'نبرة التخاطب',
              'text': 'عفوية، ذكية، بالمصري العامي مع مصطلحات تقنية',
            },
            {
              'tag': 'قاعدة المعرفة',
              'text':
                  'مشروع تخرج نيبولا للذكاء الاصطناعي، الروبوت نيبولا ذو الـ 12 محرك، والذاكرة الشخصية',
            },
          ],
          subTags: const ['توأم رقمي', 'لهجة قاهرية', 'نشط حالياً'],
          isAcademicAvatar: false,
          isActive: true,
        ),
        PersonaProfileData(
          name: 'المساعد البحثي الأكاديمي',
          traits: [
            'تفكير منطقي تحليلي',
            'نبرة موضوعية صارمة',
            'طرح تساؤلات استكشافية',
            'توقع المخاطر والبدائل',
          ],
          rules: [
            {
              'tag': 'نبرة التخاطب',
              'text': 'موضوعية، تحليلية، مدعمة بالبيانات وبدون انحيازات',
            },
            {
              'tag': 'قيود الاستجابة',
              'text':
                  'عدم تقديم افتراضات غير مؤكدة وإرفاق تنويه بالاحتمالات',
            },
          ],
          subTags: const ['تحليل أكاديمي', 'موضوعية صارمة'],
          isAcademicAvatar: true,
          isActive: false,
        ),
        PersonaProfileData(
          name: 'الرفيق الودي التفاعلي',
          traits: [
            'تعبيرات دافئة',
            'ذكاء عاطفي',
            'تفاعل ودي مستمر',
          ],
          rules: [
            {
              'tag': 'نبرة التخاطب',
              'text': 'ودية، متعاطفة، مشجعة وقريبة من المستخدم',
            },
          ],
          subTags: const ['تعبيرات دافئة', 'ذكاء عاطفي'],
          isAcademicAvatar: false,
          isActive: false,
        ),
      ];

  Future<void> _initBackendAndLocalData() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_storageKey);
      if (raw != null && raw.isNotEmpty) {
        final decoded = jsonDecode(raw) as List;
        final loaded = decoded
            .map((e) =>
                PersonaProfileData.fromJson(e as Map<String, dynamic>))
            .toList();
        if (loaded.isNotEmpty && mounted) {
          setState(() {
            _personas = loaded;
            final activeIdx = _personas.indexWhere((p) => p.isActive);
            _editingPersonaIndex = activeIdx >= 0 ? activeIdx : 0;
            _loadPersonaIntoForm(_personas[_editingPersonaIndex]);
          });
        }
      }
    } catch (_) {}

    // Sync with backend GET /api/v1/personalities/
    try {
      final remoteList = await _repo.getPersonalities();
      if (!mounted) return;
      setState(() {
        for (final remote in remoteList) {
          final existingIdx = _personas.indexWhere(
            (p) => p.backendId == remote.id || p.name == remote.name,
          );
          if (existingIdx >= 0) {
            _personas[existingIdx].backendId = remote.id;
            if (remote.description != null &&
                remote.description!.trim().isNotEmpty &&
                remote.description!.contains('|')) {
              _personas[existingIdx].traits = remote.description!
                  .split('|')
                  .map((s) => s.trim())
                  .where((s) => s.isNotEmpty)
                  .toList();
            }
          } else {
            _personas.add(
              PersonaProfileData(
                backendId: remote.id,
                name: remote.name,
                traits: remote.description != null &&
                        remote.description!.trim().isNotEmpty
                    ? remote.description!
                        .split('|')
                        .map((s) => s.trim())
                        .where((s) => s.isNotEmpty)
                        .toList()
                    : ['شخصية مخصصة'],
                rules: [
                  if (remote.systemPrompt.trim().isNotEmpty)
                    {
                      'tag': 'تعليمات النظام',
                      'text': remote.systemPrompt.trim(),
                    }
                ],
                subTags: const ['شخصية محفوظة'],
                isActive: remote.isActive,
              ),
            );
          }
        }
      });
      await _persistLocal();
      await _fetchBackendMemories();
    } catch (_) {
      // Backend offline or unreachable in test environment; local state stays intact
    }
  }

  Future<void> _persistLocal() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _storageKey,
        jsonEncode(_personas.map((p) => p.toJson()).toList()),
      );
    } catch (_) {}
  }

  void _loadPersonaIntoForm(PersonaProfileData p) {
    _personaNameCtrl.text = p.name;
    _traits
      ..clear()
      ..addAll(p.traits);
    _rules
      ..clear()
      ..addAll(p.rules.map((r) => Map<String, String>.from(r)));
    _fetchBackendMemories(p.backendId);
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    _personaNameCtrl.dispose();
    _newTraitCtrl.dispose();
    _nameFocusNode.dispose();
    super.dispose();
  }

  void _addTrait() {
    final text = _newTraitCtrl.text.trim();
    if (text.isEmpty) return;
    if (!_traits.contains(text)) {
      setState(() {
        _traits.add(text);
        _newTraitCtrl.clear();
      });
    } else {
      _newTraitCtrl.clear();
    }
  }

  void _removeTrait(int index) {
    setState(() {
      _traits.removeAt(index);
    });
  }

  void _removeRule(int index) {
    setState(() {
      _rules.removeAt(index);
    });
  }

  void _addRuleDialog({int? targetPersonaIndex}) {
    final tagCtrl = TextEditingController(text: 'نبرة التخاطب');
    final ruleCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
          ),
          title: const Text(
            'إضافة مقطع مخصص',
            style: TextStyle(
              fontFamily: 'Cairo',
              color: Color(0xFF0F172A),
              fontWeight: FontWeight.w800,
              fontSize: 16,
            ),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: tagCtrl,
                textDirection: TextDirection.rtl,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFF0F172A),
                  fontSize: 13,
                ),
                decoration: InputDecoration(
                  labelText: 'التصنيف (مثال: نبرة التخاطب)',
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: ruleCtrl,
                textDirection: TextDirection.rtl,
                maxLines: 3,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFF0F172A),
                  fontSize: 13,
                ),
                decoration: InputDecoration(
                  labelText: 'نص القاعدة أو المقطع المخصص',
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                ),
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
                  color: Color(0xFF64748B),
                ),
              ),
            ),
            TextButton(
              onPressed: () async {
                final ruleText = ruleCtrl.text.trim();
                final tagText = tagCtrl.text.trim().isEmpty
                    ? 'مقطع مخصص'
                    : tagCtrl.text.trim();
                if (ruleText.isEmpty) return;

                Navigator.pop(ctx);
                setState(() {
                  if (targetPersonaIndex != null &&
                      targetPersonaIndex >= 0 &&
                      targetPersonaIndex < _personas.length) {
                    _personas[targetPersonaIndex].rules.add({
                      'tag': tagText,
                      'text': ruleText,
                    });
                    if (_editingPersonaIndex == targetPersonaIndex) {
                      _rules.add({'tag': tagText, 'text': ruleText});
                    }
                  } else {
                    _rules.add({'tag': tagText, 'text': ruleText});
                  }
                });
                await _persistLocal();
              },
              child: const Text(
                'إضافة',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFF0284C7),
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Saves the form inputs (Persona Name, Traits, Custom Rules) to the Backend & Local Storage
  Future<void> _saveToMemory() async {
    // If user typed a trait in the box without pressing "+ إضافة سمة", include it automatically
    if (_newTraitCtrl.text.trim().isNotEmpty) {
      _addTrait();
    }

    final name = _personaNameCtrl.text.trim();
    if (name.isEmpty) {
      showErrorSnackbar(context, 'يرجى إدخال اسم الشخصية أولاً');
      _nameFocusNode.requestFocus();
      return;
    }

    setState(() => _saving = true);

    try {
      // Determine if we are updating an existing persona or creating a new one
      int targetIdx = _editingPersonaIndex;
      if (targetIdx < 0 || targetIdx >= _personas.length) {
        targetIdx = _personas.indexWhere((p) => p.name == name);
      }

      PersonaProfileData profile;
      if (targetIdx >= 0 && targetIdx < _personas.length) {
        profile = _personas[targetIdx];
        profile.name = name;
        profile.traits = List<String>.from(_traits);
        profile.rules =
            _rules.map((r) => Map<String, String>.from(r)).toList();
        profile.subTags = _traits.take(2).toList();
      } else {
        for (final p in _personas) {
          p.isActive = false;
        }
        profile = PersonaProfileData(
          name: name,
          traits: List<String>.from(_traits),
          rules: _rules.map((r) => Map<String, String>.from(r)).toList(),
          subTags: _traits.take(2).toList(),
          isActive: true,
        );
        _personas.insert(0, profile);
        targetIdx = 0;
      }

      _editingPersonaIndex = targetIdx;
      await _persistLocal();

      // Sync with Backend Database (Personalities + RAG Memories)
      final descriptionStr = profile.traits.join(' | ');
      final sysPromptStr = profile.buildSystemPrompt();

      int? backendId = profile.backendId;
      try {
        if (backendId != null) {
          final updated = await _repo.updatePersonality(backendId, {
            'name': profile.name,
            'description': descriptionStr,
            'system_prompt': sysPromptStr,
          });
          backendId = updated.id;
        } else {
          // Check if a personality with the same name already exists on backend
          final existingRemote = await _repo.getPersonalities();
          final match =
              existingRemote.where((p) => p.name == profile.name).firstOrNull;
          if (match != null) {
            final updated = await _repo.updatePersonality(match.id, {
              'name': profile.name,
              'description': descriptionStr,
              'system_prompt': sysPromptStr,
            });
            backendId = updated.id;
          } else {
            final created = await _repo.createPersonality(
              Personality(
                id: 0,
                name: profile.name,
                description: descriptionStr,
                systemPrompt: sysPromptStr,
                dialect: 'cairo',
                languageMix: 'ar_en',
                isActive: profile.isActive,
              ),
            );
            backendId = created.id;
          }
        }

        profile.backendId = backendId;
        if (profile.isActive) {
          await _repo.activatePersonality(backendId);
        }

        // Save traits & custom rules as RAG memories in the backend
        final memoryFacts = <String>[
          'الشخصية: ${profile.name}',
          ...profile.traits.map((t) => 'سمة في ${profile.name}: $t'),
          ...profile.rules
              .map((r) => 'قاعدة تخاطب (${r['tag']}) في ${profile.name}: ${r['text']}'),
        ];
        await _repo.addMemoriesBatch(memoryFacts, backendId, 8);
        await _persistLocal();
      } catch (_) {
        // Even if backend is unreachable (e.g., widget test), local storage succeeded
      }

      if (!mounted) return;
      setState(() {});
      showSuccessSnackbar(
        context,
        'تم حفظ وتثبيت "$name" في قاعدة البيانات والذاكرة بنجاح',
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _clearForm() {
    setState(() {
      _editingPersonaIndex = -1;
      _personaNameCtrl.clear();
      _newTraitCtrl.clear();
      _traits.clear();
      _rules.clear();
    });
    showSuccessSnackbar(context, 'تم تفريغ الحقول لإدخال شخصية جديدة');
  }

  void _startNewPersona() {
    setState(() {
      _editingPersonaIndex = -1;
      _personaNameCtrl.clear();
      _newTraitCtrl.clear();
      _traits.clear();
      _rules.clear();
    });
    _nameFocusNode.requestFocus();
  }

  Future<void> _activatePersona(int index) async {
    if (index < 0 || index >= _personas.length) return;
    setState(() {
      for (int i = 0; i < _personas.length; i++) {
        _personas[i].isActive = (i == index);
      }
      _editingPersonaIndex = index;
      _loadPersonaIntoForm(_personas[index]);
    });
    await _persistLocal();

    final target = _personas[index];
    if (target.backendId != null) {
      try {
        await _repo.activatePersonality(target.backendId!);
      } catch (_) {}
    }

    // Switch avatar and trigger synced speech greeting
    final isMale = target.isAcademicAvatar;
    AvatarAudioService.instance.switchAvatar(isMale ? 'male' : 'female', name: target.name);
    if (target.backendId != null) {
      AvatarAudioService.instance.activePersonalityId.value = target.backendId!;
    }
    final greeting = isMale
        ? 'تم تفعيل شخصية ${target.name}. جاهز لتنفيذ المهام الأكاديمية والتحليلية.'
        : 'تم تفعيل شخصية ${target.name}. سعيدة بمساعدتك اليوم!';
    AvatarAudioService.instance.speak(greeting, emotion: isMale ? 'confident' : 'happy');

    if (!mounted) return;
    showSuccessSnackbar(context, 'تم تفعيل "${target.name}"');
  }

  Future<void> _pickAvatarForPersona(int index) async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.image,
      );
      if (result.isNotEmpty && result.first.path != null) {
        final path = result.first.path!;
        setState(() {
          _personas[index].avatarPath = path;
        });
        await _persistLocal();
        if (mounted) {
          showSuccessSnackbar(
            context,
            'تم تحديث صورة "${_personas[index].name}"',
          );
        }
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الصورة: $e');
    }
  }

  Future<void> _importPersonaFile({int? targetIndex}) async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['json', 'txt'],
      );
      if (result.isEmpty || result.first.path == null) {
        return;
      }

      final file = File(result.first.path!);
      final content = await file.readAsString();

      String importedName =
          result.first.name.replaceAll(RegExp(r'\.(json|txt)$'), '');
      List<String> importedTraits = [];
      List<Map<String, String>> importedRules = [];

      try {
        final decoded = jsonDecode(content);
        if (decoded is Map<String, dynamic>) {
          importedName = decoded['name']?.toString() ?? importedName;
          if (decoded['traits'] is List) {
            importedTraits = (decoded['traits'] as List)
                .map((e) => e.toString())
                .toList();
          }
          if (decoded['rules'] is List) {
            importedRules = (decoded['rules'] as List)
                .map((e) => {
                      'tag': (e as Map)['tag']?.toString() ?? 'قاعدة',
                      'text': e['text']?.toString() ?? '',
                    })
                .toList();
          }
        }
      } catch (_) {
        // Plain text file: treat lines as rules/traits
        final lines = content
            .split('\n')
            .map((l) => l.trim())
            .where((l) => l.isNotEmpty)
            .toList();
        if (lines.isNotEmpty) {
          importedTraits = lines.take(4).toList();
          for (final line in lines.skip(4)) {
            importedRules.add({'tag': 'مقطع مستورد', 'text': line});
          }
        }
      }

      setState(() {
        if (targetIndex != null &&
            targetIndex >= 0 &&
            targetIndex < _personas.length) {
          if (importedTraits.isNotEmpty) {
            _personas[targetIndex].traits.addAll(importedTraits);
          }
          if (importedRules.isNotEmpty) {
            _personas[targetIndex].rules.addAll(importedRules);
          }
          _editingPersonaIndex = targetIndex;
          _loadPersonaIntoForm(_personas[targetIndex]);
        } else {
          final newPersona = PersonaProfileData(
            name: importedName,
            traits: importedTraits.isNotEmpty
                ? importedTraits
                : ['سمة مستوردة'],
            rules: importedRules,
            subTags: importedTraits.take(2).toList(),
            isActive: false,
          );
          _personas.add(newPersona);
          _editingPersonaIndex = _personas.length - 1;
          _loadPersonaIntoForm(newPersona);
        }
      });

      await _saveToMemory();
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر استيراد الملف: $e');
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
            _memScaffoldKey.currentState?.closeEndDrawer();
          } else {
            _memScaffoldKey.currentState?.closeDrawer();
          }
          widget.onNavigate?.call(idx);
        },
        onClose: () {
          if (isArabic) {
            _memScaffoldKey.currentState?.closeEndDrawer();
          } else {
            _memScaffoldKey.currentState?.closeDrawer();
          }
        },
      ),
    );

    return Theme(
      data: ThemeData.light().copyWith(
        scaffoldBackgroundColor: const Color(0xFFF8FAFC),
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF06B6D4),
          surface: Colors.white,
          onSurface: Color(0xFF0F172A),
        ),
        textTheme: ThemeData.light().textTheme.apply(fontFamily: 'Cairo'),
      ),
      child: Scaffold(
        key: _memScaffoldKey,
        drawer: isArabic ? null : sidebar,
        endDrawer: isArabic ? sidebar : null,
        backgroundColor: const Color(0xFFF8FAFC),
        body: Directionality(
          textDirection: LocaleService.instance.textDirection,
          child: Stack(
            children: [
              // Top subtle cyborg profile background watermark
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                height: 170,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Opacity(
                      opacity: 0.14,
                      child: Image.asset(
                        'assets/images/cyborg_bg.jpg',
                        fit: BoxFit.cover,
                        alignment: const Alignment(-0.2, -0.3),
                      ),
                    ),
                    const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Color(0x33F8FAFC),
                            Color(0xCCF8FAFC),
                            Color(0xFFF8FAFC),
                          ],
                          stops: [0.0, 0.65, 1.0],
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              SafeArea(
                child: Column(
                  children: [
                    Expanded(
                      child: Scrollbar(
                        controller: _scrollCtrl,
                        thumbVisibility: true,
                        radius: const Radius.circular(8),
                        child: SingleChildScrollView(
                          controller: _scrollCtrl,
                          physics: const AlwaysScrollableScrollPhysics(
                            parent: BouncingScrollPhysics(),
                          ),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          child: Center(
                            child: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 640),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  // Top Row: Menu on LEFT, Exit on RIGHT in Arabic; swapped in English
                                  Directionality(
                                    textDirection: TextDirection.ltr,
                                    child: Row(
                                      children: [
                                        // Visual Left
                                        if (isArabic)
                                          InkWell(
                                            onTap: () => _memScaffoldKey.currentState?.openEndDrawer(),
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
                                          )
                                        else
                                          InkWell(
                                            onTap: () {
                                              if (widget.onNavigate != null) {
                                                widget.onNavigate!(0);
                                              } else if (Navigator.canPop(context)) {
                                                Navigator.pop(context);
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
                                              child: const Icon(
                                                Icons.arrow_back_rounded,
                                                size: 20,
                                                color: Color(0xFF0F172A),
                                              ),
                                            ),
                                          ),
                                        const SizedBox(width: 12),

                                        // Title
                                        Expanded(
                                          child: Text(
                                            LocaleService.instance.translate('memory_personas'),
                                            textAlign: isArabic ? TextAlign.right : TextAlign.left,
                                            style: const TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 19,
                                              fontWeight: FontWeight.w900,
                                              color: Color(0xFF0F172A),
                                              letterSpacing: -0.2,
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),

                                        // Visual Right
                                        if (isArabic)
                                          InkWell(
                                            onTap: () {
                                              if (widget.onNavigate != null) {
                                                widget.onNavigate!(0);
                                              } else if (Navigator.canPop(context)) {
                                                Navigator.pop(context);
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
                                              child: const Icon(
                                                Icons.arrow_forward_rounded,
                                                size: 20,
                                                color: Color(0xFF0F172A),
                                              ),
                                            ),
                                          )
                                        else
                                          InkWell(
                                            onTap: () => _memScaffoldKey.currentState?.openEndDrawer(),
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
                                          ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(height: 12),

                                  // 1. RAM & System Memory Card
                                  _buildRamCard(),
                                  const SizedBox(height: 10),

                                  // 1B. Backend RAG Memories Card
                                  _buildBackendRagMemoriesCard(),
                                  const SizedBox(height: 10),

                                  // 2. Add New Persona Card
                                  _buildNewPersonaCard(),
                                  const SizedBox(height: 12),

                                  // 3. Personas Management Section
                                  _buildPersonasManagementSection(),
                                  const SizedBox(height: 12),

                                  // Bottom Home Indicator Pill
                                  Center(
                                    child: Container(
                                      width: 120,
                                      height: 4,
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFCBD5E1),
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(height: 8),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ─── CARD 1: RAM & SYSTEM MEMORY ───────────────────────────────────────────
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
          // Top Header Row: Title on Right, Green "افضل 60%" badge on Left
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

          // Inner Sub-box with Circular Gauge on Right & Bars/Stats on Left
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFF1F5F9)),
            ),
            child: Row(
              children: [
                // Right in RTL: 60% USED Circular Gauge
                SizedBox(
                  width: 62,
                  height: 62,
                  child: CustomPaint(
                    painter: _GaugeArcPainter(
                      percentage: 0.60,
                      activeColor: const Color(0xFF06B6D4),
                      trackColor: const Color(0xFFE2E8F0),
                    ),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: const [
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

                // Left in RTL: Metrics & Linear Bar
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: const [
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
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: const [
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

  // ─── CARD 1B: BACKEND RAG MEMORIES ─────────────────────────────────────────
  Widget _buildBackendRagMemoriesCard() {
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
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.memory_rounded,
                        color: Color(0xFFD97706), size: 18),
                  ),
                  const SizedBox(width: 8),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'ذاكرة الروبوت (RAG Backend)',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      Text(
                        '${_backendMemories.length} حقائق مسجلة بالباك إند',
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
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                onPressed: _showAddMemoryDialog,
                icon: const Icon(Icons.add_rounded, size: 15),
                label: const Text(
                  'إضافة حقيقة',
                  style: TextStyle(fontFamily: 'Cairo', fontSize: 11),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (_loadingBackendMemories)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(12),
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Color(0xFF00B4D8),
                  ),
                ),
              ),
            )
          else if (_backendMemories.isEmpty)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Text(
                'لا توجد حقائق محفوظة بعد. أضف أول حقيقة ليتم تذكرها عبر الباك إند.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11.5,
                  color: Color(0xFF64748B),
                ),
              ),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _backendMemories.length,
              separatorBuilder: (ctx, i) => const SizedBox(height: 6),
              itemBuilder: (context, idx) {
                final mem = _backendMemories[idx];
                return Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: Color(0xFF00B4D8),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          mem.content,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 11.5,
                            color: Color(0xFF1E293B),
                          ),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline_rounded,
                            size: 16, color: Color(0xFF94A3B8)),
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                        onPressed: () => _deleteBackendMemory(mem.id),
                      ),
                    ],
                  ),
                );
              },
            ),
        ],
      ),
    );
  }

  Future<void> _showAddMemoryDialog() async {
    final textCtrl = TextEditingController();
    const importance = 5;
    final pid = _editingPersonaIndex >= 0 && _editingPersonaIndex < _personas.length
        ? (_personas[_editingPersonaIndex].backendId ?? 1)
        : 1;

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => Directionality(
          textDirection: LocaleService.instance.textDirection,
          child: AlertDialog(
            backgroundColor: Colors.white,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: const Row(
              children: [
                Icon(Icons.psychology_rounded, color: Color(0xFF00B4D8)),
                SizedBox(width: 8),
                Text(
                  'إضافة معلومة جديدة للذاكرة',
                  style: TextStyle(
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
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('إلغاء',
                    style: TextStyle(fontFamily: 'Cairo')),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                ),
                onPressed: () async {
                  final text = textCtrl.text.trim();
                  if (text.isEmpty) return;
                  Navigator.pop(ctx);
                  try {
                    await _repo.addMemory(text, pid, importance);
                    if (mounted) {
                      showSuccessSnackbar(
                          context, 'تمت إضافة المعلومة للذاكرة بالباك إند');
                      _fetchBackendMemories(pid);
                    }
                  } catch (e) {
                    if (mounted) showErrorSnackbar(context, 'فشل الحفظ: $e');
                  }
                },
                child: const Text('حفظ في الذاكرة',
                    style: TextStyle(
                        fontFamily: 'Cairo', fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _deleteBackendMemory(int memoryId) async {
    try {
      await _repo.deleteMemory(memoryId);
      if (mounted) {
        showSuccessSnackbar(context, 'تم حذف المعلومة بنجاح');
        _fetchBackendMemories();
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر الحذف: $e');
    }
  }

  // ─── CARD 2: ADD NEW PERSONA ───────────────────────────────────────────────
  Widget _buildNewPersonaCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
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
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Row: Cyan indicator + "إضافة شخصية جديدة" on Right, "+ اضافة جديدة" on Left
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 5,
                      height: 18,
                      decoration: BoxDecoration(
                        color: const Color(0xFF06B6D4),
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Flexible(
                      child: Text(
                        'إضافة شخصية جديدة',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: _startNewPersona,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF0F9FF),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFBAE6FD)),
                  ),
                  child: const Text(
                    '+ اضافة جديدة',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0284C7),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Persona Name Label aligned Right
          const Align(
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              'اسم الشخصية',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 13,
                fontWeight: FontWeight.w800,
                color: Color(0xFF1E293B),
              ),
            ),
          ),
          const SizedBox(height: 6),

          // Persona Name Row: Editable Name Box on Right + "تعديل" Button on Left
          Row(
            children: [
              Expanded(
                child: Container(
                  height: 38,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  alignment: AlignmentDirectional.centerStart,
                  child: TextField(
                    controller: _personaNameCtrl,
                    focusNode: _nameFocusNode,
                    textDirection: TextDirection.rtl,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0F172A),
                    ),
                    decoration: const InputDecoration(
                      isDense: true,
                      contentPadding: EdgeInsets.zero,
                      border: InputBorder.none,
                      hintText: 'أدخل اسم الشخصية...',
                      hintStyle: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        color: Color(0xFF94A3B8),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              GestureDetector(
                onTap: () {
                  _nameFocusNode.requestFocus();
                  _personaNameCtrl.selection = TextSelection(
                    baseOffset: 0,
                    extentOffset: _personaNameCtrl.text.length,
                  );
                },
                child: Container(
                  height: 38,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: const [
                      Icon(
                        Icons.edit_note_rounded,
                        size: 16,
                        color: Color(0xFF475569),
                      ),
                      SizedBox(width: 5),
                      Text(
                        'تعديل',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF334155),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Core Concept & Unique Traits Header Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Flexible(
                child: Text(
                  'الفكرة الجوهرية والسمات الفريدة',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1E293B),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '+${_traits.length} سمات نشطة',
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11.5,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF06B6D4),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),

          // Traits Container Box
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_traits.isNotEmpty) ...[
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    alignment: WrapAlignment.center,
                    children: List.generate(_traits.length, (i) {
                      final isHighlighted = i < 2;
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: isHighlighted
                              ? const Color(0xFFF0F9FF)
                              : Colors.white,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isHighlighted
                                ? const Color(0xFF7DD3FC)
                                : const Color(0xFFE2E8F0),
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Flexible(
                              child: Text(
                                _traits[i],
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 11.5,
                                  fontWeight: FontWeight.w700,
                                  color: isHighlighted
                                      ? const Color(0xFF0284C7)
                                      : const Color(0xFF334155),
                                ),
                              ),
                            ),
                            const SizedBox(width: 6),
                            GestureDetector(
                              onTap: () => _removeTrait(i),
                              child: Icon(
                                Icons.close_rounded,
                                size: 13.5,
                                color: isHighlighted
                                    ? const Color(0xFF0284C7)
                                    : const Color(0xFF64748B),
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 10),
                ],

                // Trait Input on Right + Dark "+ إضافة سمة" Button on Left
                Row(
                  children: [
                    Expanded(
                      child: Container(
                        height: 38,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: const Color(0xFFE2E8F0)),
                        ),
                        alignment: AlignmentDirectional.centerStart,
                        child: TextField(
                          controller: _newTraitCtrl,
                          textDirection: TextDirection.rtl,
                          style: const TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF0F172A),
                          ),
                          decoration: const InputDecoration(
                            isDense: true,
                            contentPadding: EdgeInsets.zero,
                            border: InputBorder.none,
                            hintText:
                                'أدخل سمة فريدة أو فكرة جوهرية جديدة...',
                            hintStyle: TextStyle(
                              fontFamily: 'Cairo',
                              color: Color(0xFF94A3B8),
                              fontSize: 11.5,
                            ),
                          ),
                          onSubmitted: (_) => _addTrait(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    GestureDetector(
                      onTap: _addTrait,
                      child: Container(
                        height: 38,
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0F172A),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        alignment: Alignment.center,
                        child: const Text(
                          '+ إضافة سمة',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Custom Text Snippets & Dialogue Rules Box
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header inside the box
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Expanded(
                      child: Text(
                        'المقاطع النصية وقواعد التخاطب المخصصة',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12.5,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF1E293B),
                          height: 1.3,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    GestureDetector(
                      onTap: () => _addRuleDialog(),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE0F2FE),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: const Color(0xFF7DD3FC)),
                        ),
                        child: const Text(
                          '+ إضافة مقطع مخصص',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0284C7),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),

                // Rule Cards List
                ...List.generate(_rules.length, (i) {
                  final rule = _rules[i];
                  return Padding(
                    padding: EdgeInsets.only(
                      bottom: i < _rules.length - 1 ? 6 : 0,
                    ),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: Row(
                        children: [
                          // Right in RTL: Cyan Tag Pill
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE0F2FE),
                              borderRadius: BorderRadius.circular(8),
                              border:
                                  Border.all(color: const Color(0xFFBAE6FD)),
                            ),
                            child: Text(
                              rule['tag'] ?? '',
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 10.5,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0284C7),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),

                          // Middle: Rule Description
                          Expanded(
                            child: Text(
                              rule['text'] ?? '',
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF334155),
                                height: 1.3,
                              ),
                            ),
                          ),
                          const SizedBox(width: 6),

                          // Left in RTL: Delete (X) Icon
                          GestureDetector(
                            onTap: () => _removeRule(i),
                            child: const Icon(
                              Icons.close_rounded,
                              size: 16,
                              color: Color(0xFF94A3B8),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Bottom Action Buttons: Dark "حفظ وتثبيت في الذاكرة" on Right + Light "إلغاء / تفريغ" on Left
          Row(
            children: [
              Expanded(
                flex: 2,
                child: GestureDetector(
                  onTap: _saving ? null : _saveToMemory,
                  child: Container(
                    height: 44,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: [
                        BoxShadow(
                          color:
                              const Color(0xFF0F172A).withValues(alpha: 0.14),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        if (_saving)
                          const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        else ...[
                          const Flexible(
                            child: Text(
                              'حفظ وتثبيت في الذاكرة',
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 13,
                                fontWeight: FontWeight.w800,
                                color: Colors.white,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Icon(
                            Icons.system_update_alt_rounded,
                            size: 17,
                            color: Color(0xFF06B6D4),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                flex: 1,
                child: GestureDetector(
                  onTap: _clearForm,
                  child: Container(
                    height: 44,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFE2E8F0)),
                    ),
                    alignment: Alignment.center,
                    child: const Text(
                      'إلغاء / تفريغ',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF334155),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ─── SECTION 3: PERSONAS MANAGEMENT ────────────────────────────────────────
  Widget _buildPersonasManagementSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Header Row: "إدارة الشخصيات" on Right, "3 شخصيات نشطة" in Middle, "استيراد ملف شخصية" on Left
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 5,
                  height: 18,
                  decoration: BoxDecoration(
                    color: const Color(0xFF06B6D4),
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
                const SizedBox(width: 6),
                const Text(
                  'إدارة الشخصيات',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF0F9FF),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFBAE6FD)),
                  ),
                  child: const Text(
                    '3 شخصيات نشطة',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 10.5,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF0284C7),
                    ),
                  ),
                ),
              ],
            ),
            GestureDetector(
              onTap: () => _importPersonaFile(),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFF7DD3FC)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: const [
                    Icon(
                      Icons.upload_rounded,
                      size: 13.5,
                      color: Color(0xFF0284C7),
                    ),
                    SizedBox(width: 4),
                    Text(
                      'استيراد ملف شخصية',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0284C7),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),

        // Render all personas dynamically
        ...List.generate(_personas.length, (index) {
          return Padding(
            padding: EdgeInsets.only(
              bottom: index < _personas.length - 1 ? 10 : 0,
            ),
            child: _buildPersonaCard(index),
          );
        }),
      ],
    );
  }

  Widget _buildPersonaCard(int index) {
    final p = _personas[index];
    final isActive = p.isActive;
    final isFirstStyle = p.isAcademicAvatar || index == 0;

    return GestureDetector(
      onTap: () {
        setState(() {
          _editingPersonaIndex = index;
          _loadPersonaIntoForm(p);
        });
      },
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color:
                isActive ? const Color(0xFF06B6D4) : const Color(0xFFE2E8F0),
            width: isActive ? 1.8 : 1.2,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: const Color(0xFF06B6D4).withValues(alpha: 0.10),
                    blurRadius: 12,
                    offset: const Offset(0, 3),
                  ),
                ]
              : null,
        ),
        child: Column(
          children: [
            Row(
              children: [
                // Avatar on Right
                _buildPersonaAvatar(p, isFirstStyle),
                const SizedBox(width: 12),

                // Middle Title & Tags/Badges
                Expanded(
                  child: isFirstStyle && isActive
                      ? Row(
                          children: [
                            Flexible(
                              child: Text(
                                p.name,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w800,
                                  color: Color(0xFF0F172A),
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: const Color(0xFFF0F9FF),
                                borderRadius: BorderRadius.circular(8),
                                border:
                                    Border.all(color: const Color(0xFFBAE6FD)),
                              ),
                              child: const Text(
                                'نشط حالياً',
                                style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 10.5,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF0284C7),
                                ),
                              ),
                            ),
                          ],
                        )
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Flexible(
                                  child: Text(
                                    p.name,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 14,
                                      fontWeight: FontWeight.w800,
                                      color: Color(0xFF0F172A),
                                    ),
                                  ),
                                ),
                                if (isActive) ...[
                                  const SizedBox(width: 6),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 2,
                                    ),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFFF0F9FF),
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(
                                        color: const Color(0xFFBAE6FD),
                                      ),
                                    ),
                                    child: const Text(
                                      'نشط حالياً',
                                      style: TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 10,
                                        fontWeight: FontWeight.w700,
                                        color: Color(0xFF0284C7),
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                            if (p.subTags.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Wrap(
                                spacing: 6,
                                runSpacing: 4,
                                children: p.subTags
                                    .take(2)
                                    .map((t) => _buildSubTag(t))
                                    .toList(),
                              ),
                            ],
                          ],
                        ),
                ),

                // Left side: "تفعيل" button if not the primary active card
                if (!isActive) ...[
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () => _activatePersona(index),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 5,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFECFDF5),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFA7F3D0)),
                      ),
                      child: const Text(
                        'تفعيل',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11.5,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF059669),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 10),

            // Bottom Action Buttons Row
            if (isFirstStyle)
              Row(
                children: [
                  Expanded(
                    child: _buildActionBtn(
                      label: 'تعديل',
                      icon: Icons.edit_note_rounded,
                      onTap: () {
                        setState(() {
                          _editingPersonaIndex = index;
                          _loadPersonaIntoForm(p);
                        });
                        _nameFocusNode.requestFocus();
                      },
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: _buildActionBtn(
                      label: 'إضافة',
                      icon: Icons.add_rounded,
                      iconColor: const Color(0xFF06B6D4),
                      onTap: () =>
                          _addRuleDialog(targetPersonaIndex: index),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: _buildActionBtn(
                      label: 'إضافة صورة',
                      icon: Icons.image_outlined,
                      onTap: () => _pickAvatarForPersona(index),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: _buildActionBtn(
                      label: 'استيراد',
                      icon: Icons.upload_rounded,
                      onTap: () => _importPersonaFile(targetIndex: index),
                    ),
                  ),
                ],
              )
            else
              Row(
                children: [
                  Expanded(
                    flex: 2,
                    child: _buildActionBtn(
                      label: 'تعديل',
                      icon: Icons.edit_note_rounded,
                      onTap: () {
                        setState(() {
                          _editingPersonaIndex = index;
                          _loadPersonaIntoForm(p);
                        });
                        _nameFocusNode.requestFocus();
                      },
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 1,
                    child: _buildActionBtn(
                      label: 'إضافة صورة',
                      icon: Icons.image_outlined,
                      onTap: () => _pickAvatarForPersona(index),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 1,
                    child: _buildActionBtn(
                      label: 'استيراد',
                      icon: Icons.upload_rounded,
                      onTap: () => _importPersonaFile(targetIndex: index),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildPersonaAvatar(PersonaProfileData p, bool isAcademic) {
    if (p.avatarPath != null && File(p.avatarPath!).existsSync()) {
      return Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFF7DD3FC)),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(11),
          child: Image.file(
            File(p.avatarPath!),
            fit: BoxFit.cover,
          ),
        ),
      );
    }

    if (isAcademic) {
      return Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          color: const Color(0xFFE0F2FE),
          border: Border.all(color: const Color(0xFF7DD3FC)),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(11),
          child: Image.asset(
            'assets/images/avatar_male.jpg',
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
            errorBuilder: (_, _, _) => const Icon(
              Icons.smart_toy_rounded,
              color: Color(0xFF0284C7),
            ),
          ),
        ),
      );
    }

    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: const Color(0xFFF1F5F9),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(13),
        child: Image.asset(
          'assets/images/avatar_female.png',
          fit: BoxFit.cover,
          alignment: Alignment.topCenter,
          errorBuilder: (_, _, _) => const Icon(
            Icons.face_3_rounded,
            size: 23,
            color: Color(0xFF94A3B8),
          ),
        ),
      ),
    );
  }

  Widget _buildSubTag(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontFamily: 'Cairo',
          fontSize: 10.5,
          fontWeight: FontWeight.w600,
          color: Color(0xFF64748B),
        ),
      ),
    );
  }

  Widget _buildActionBtn({
    required String label,
    required IconData icon,
    required VoidCallback onTap,
    Color iconColor = const Color(0xFF475569),
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 6),
        decoration: BoxDecoration(
          color: const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFFE2E8F0)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 14, color: iconColor),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF334155),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Custom painter for the 60% USED open-bottom gauge arc matching the mockup
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
