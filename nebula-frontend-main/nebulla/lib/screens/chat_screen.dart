import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/nebula_repository.dart';
import '../services/avatar_audio_service.dart';
import '../widgets/common_widgets.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';

class ChatScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;
  const ChatScreen({super.key, this.onNavigate});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatMessageItem {
  final String id;
  final String role; // 'user' | 'assistant'
  final String content;
  final String time;
  final List<String>? quickActions; // e.g. suggestion pills below welcome msg
  final List<String>? orderedSteps; // numbered bullet list
  final String? emotion;
  final double? latencyMs;
  final bool isWelcome;
  final String? verifiedSpeaker;
  final bool isVoiceMessage;

  _ChatMessageItem({
    required this.id,
    required this.role,
    required this.content,
    required this.time,
    this.quickActions,
    this.orderedSteps,
    this.emotion,
    this.latencyMs,
    this.isWelcome = false,
    this.verifiedSpeaker,
    this.isVoiceMessage = false,
  });
}

class _ChatScreenState extends State<ChatScreen> {
  final GlobalKey<ScaffoldState> _chatScaffoldKey = GlobalKey<ScaffoldState>();
  final _repo = NebulaRepository.instance;
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();

  final List<_ChatMessageItem> _messages = [];
  String? _sessionId;
  bool _sending = false;
  String _assistantName = 'المساعد الذكي';
  int? _activePersonalityId;

  // Liked/disliked message state for the thumb icons
  final Set<String> _likedMessages = {};

  @override
  void initState() {
    super.initState();
    // Immediate welcome message so it renders instantly
    _messages.add(
      _ChatMessageItem(
        id: 'welcome_1',
        role: 'assistant',
        content:
            'مرحباً بك! أنا مساعدك الذكي. كيف يمكنني مساعدتك اليوم؟ يمكنك سؤالي عن كتابة النصوص، تنظيم المهام، أو توليد أفكار إبداعية.',
        time: 'اليوم، 10:30 ص',
        isWelcome: true,
        quickActions: [
          'تلخيص نص طويل',
          'اقتراح أفكار إبداعية',
          'المساعدة في كتابة محتوى',
        ],
      ),
    );
    _loadActivePersonalityAndGreeting();
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadActivePersonalityAndGreeting() async {
    try {
      final personalities = await _repo.getPersonalities();
      final active = personalities.where((p) => p.isActive).firstOrNull ??
          personalities.firstOrNull;
      if (active != null && mounted) {
        setState(() {
          _assistantName = active.name;
          _activePersonalityId = active.id;
        });
      }
    } catch (_) {}

    // Add initial mockup welcome message
    if (mounted && _messages.isEmpty) {
      setState(() {
        _messages.add(
          _ChatMessageItem(
            id: 'welcome_1',
            role: 'assistant',
            content:
                'مرحباً بك! أنا مساعدك الذكي. كيف يمكنني مساعدتك اليوم؟ يمكنك سؤالي عن كتابة النصوص، تنظيم المهام، أو توليد أفكار إبداعية.',
            time: 'اليوم، 10:30 ص',
            isWelcome: true,
            quickActions: [
              'تلخيص نص طويل',
              'اقتراح أفكار إبداعية',
              'المساعدة في كتابة محتوى',
            ],
          ),
        );
      });
    }
  }

  void _startNewSession() {
    setState(() {
      _messages.clear();
      _sessionId = null;
    });
    _loadActivePersonalityAndGreeting();
    showSuccessSnackbar(context, 'تم بدء جلسة محادثة جديدة');
  }

  String _formatCurrentTime() {
    final now = DateTime.now();
    final hour = now.hour % 12 == 0 ? 12 : now.hour % 12;
    final minute = now.minute.toString().padLeft(2, '0');
    final period = now.hour >= 12 ? 'م' : 'ص';
    return '$hour:$minute $period';
  }

  Future<void> _sendMessage([
    String? presetText,
    String? verifiedSpeaker,
    bool isVoiceMessage = false,
  ]) async {
    final text = (presetText ?? _inputCtrl.text).trim();
    if (text.isEmpty || _sending) return;

    final userTime = _formatCurrentTime();
    final userMsgId = 'u_${DateTime.now().millisecondsSinceEpoch}';

    setState(() {
      _messages.add(
        _ChatMessageItem(
          id: userMsgId,
          role: 'user',
          content: text,
          time: userTime,
          verifiedSpeaker: verifiedSpeaker,
          isVoiceMessage: isVoiceMessage,
        ),
      );
      _sending = true;
    });

    if (presetText == null) {
      _inputCtrl.clear();
    }
    _scrollToBottom();

    try {
      final data = await _repo.chat(
        text,
        sessionId: _sessionId,
        personalityId: _activePersonalityId,
      );

      final reply = data['reply'] as String? ??
          data['response'] as String? ??
          '';
      _sessionId = data['session_id'] as String? ?? _sessionId;
      final emotion = data['emotion'] as String?;
      final latency = (data['llm_latency_ms'] as num?)?.toDouble();

      // Check if the reply contains numbered points (1, 2, 3...)
      List<String>? parsedSteps;
      final stepsRegex = RegExp(r'(?:^|\n)\s*(\d+)[\.\-\)]\s*(.+)', multiLine: true);
      final matches = stepsRegex.allMatches(reply).toList();
      if (matches.length >= 2) {
        parsedSteps = matches.map((m) => m.group(2)!.trim()).toList();
      }

      if (!mounted) return;
      setState(() {
        _messages.add(
          _ChatMessageItem(
            id: 'a_${DateTime.now().millisecondsSinceEpoch}',
            role: 'assistant',
            content: reply,
            time: _formatCurrentTime(),
            orderedSteps: parsedSteps,
            emotion: emotion,
            latencyMs: latency,
          ),
        );
      });

      // Synchronize backend speech audio with animated character lip-sync and expressions
      AvatarAudioService.instance.speak(
        reply,
        emotion: emotion,
        personalityId: _activePersonalityId,
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackbar(context, 'فشل استلام الرد من الذكاء الاصطناعي: $e');
    } finally {
      if (mounted) {
        setState(() => _sending = false);
      }
      _scrollToBottom();
    }
  }

  Future<void> _pickAttachment() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['txt', 'pdf', 'docx', 'jpg', 'png', 'wav', 'mp3'],
      );
      if (result.isEmpty || result.first.path == null) return;
      final fileName = result.first.name;

      if (mounted) {
        showSuccessSnackbar(context, 'تم إرفاق الملف: $fileName');
        _inputCtrl.text = 'يرجى تحليل وتلخيص الملف المرفق: $fileName';
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر اختيار الملف: $e');
    }
  }

  Future<void> _recordAudioPrompt() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['wav', 'mp3', 'm4a', 'aac', 'ogg'],
      );
      if (result.isEmpty || result.first.path == null) return;
      final file = File(result.first.path!);
      final fileName = result.first.name;

      if (!mounted) return;
      showSuccessSnackbar(context, 'جاري معالجة وبصمة الصوت: $fileName...');

      // 1. Identify Speaker via Biometrics
      String? verifiedSpeaker;
      try {
        final idRes = await _repo.identifySpeaker(file);
        final speaker = idRes['speaker'] as String? ?? idRes['name'] as String?;
        final confidence = (idRes['confidence'] as num?)?.toDouble() ?? 0.0;
        if (speaker != null && speaker != 'unknown' && speaker != 'مجهول') {
          final pct = (confidence * 100).toInt();
          verifiedSpeaker = '$speaker ($pct%)';
        }
      } catch (_) {}

      // 2. Transcribe Audio via STT
      String? transcript;
      try {
        transcript = await _repo.transcribeAudio(file);
      } catch (_) {}

      final messageText = (transcript != null && transcript.trim().isNotEmpty)
          ? transcript.trim()
          : '🎙️ [رسالة صوتية مُسجّلة]';

      if (!mounted) return;
      _sendMessage(
        messageText,
        verifiedSpeaker,
        true,
      );
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر معالجة الصوت: $e');
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 320),
          curve: Curves.easeOutQuad,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final isDesktop = size.width > 540;

    return Scaffold(
      key: _chatScaffoldKey,
      drawer: Drawer(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: NebulaSideMenu(
          activeIndex: 1,
          onNavigate: (idx) {
            _chatScaffoldKey.currentState?.closeDrawer();
            widget.onNavigate?.call(idx);
          },
          onClose: () => _chatScaffoldKey.currentState?.closeDrawer(),
        ),
      ),
      backgroundColor: const Color(0xFFF8FAFC),
      body: Center(
        child: Container(
          width: isDesktop ? 460 : double.infinity,
          height: double.infinity,
          decoration: BoxDecoration(
            color: const Color(0xFFF8FAFC),
            borderRadius: BorderRadius.circular(isDesktop ? 28 : 0),
            boxShadow: isDesktop
                ? [
                    BoxShadow(
                      color: const Color(0xFF0F172A).withValues(alpha: 0.08),
                      blurRadius: 36,
                      offset: const Offset(0, 14),
                    ),
                  ]
                : null,
          ),
          clipBehavior: Clip.antiAlias,
          child: SafeArea(
            bottom: false,
            child: Column(
              children: [
                // 1. Top App Bar matching mockup 100%
                _buildTopAppBar(),

                // 2. Chat Sub-Header Card (المساعد الذكي | متصل الآن - استجابة فورية | جلسة جديدة)
                _buildAssistantSubHeader(),

                // 3. Messages List
                Expanded(
                  child: ListView.builder(
                    controller: _scrollCtrl,
                    physics: const AlwaysScrollableScrollPhysics(
                      parent: BouncingScrollPhysics(),
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      return _buildMessageItem(msg);
                    },
                  ),
                ),

                // 4. Typing indicator bar ("المساعد يكتب الآن...")
                if (_sending) _buildTypingIndicatorBar(),

                // 5. Bottom Modern Floating Input Bar matching mockup 100%
                _buildModernInputBar(),

                // Bottom spacing to guarantee the input bar is 100% visible and sits cleanly above the bottom navigation bar
                SizedBox(
                  height: MediaQuery.of(context).viewInsets.bottom > 0 ? 8 : 88,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Top App Bar: Back arrow on right (RTL start), Title + Logo icon in middle, 3 dots on left
  Widget _buildTopAppBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(
          bottom: BorderSide(color: Color(0xFFF1F5F9), width: 1.2),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Right (RTL start): Back arrow
          IconButton(
            icon: const Icon(
              Icons.arrow_forward_rounded,
              color: Color(0xFF1E293B),
              size: 24,
            ),
            onPressed: () {
              if (Navigator.canPop(context)) {
                Navigator.pop(context);
              }
            },
          ),

          // Center: Logo Avatar + Assistant Name + Green/Cyan online dot
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Logo Avatar Circle with Cyan Ring & Neural Chip Glyphs
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFFE0F7FA),
                  border: Border.all(
                    color: const Color(0xFF00C7E5),
                    width: 1.8,
                  ),
                ),
                child: const Center(
                  child: Icon(
                    Icons.bubble_chart_rounded,
                    color: Color(0xFF0096C7),
                    size: 22,
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // Title and "متصل الآن" status
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _assistantName,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.w900,
                      color: Color(0xFF0F172A),
                      height: 1.2,
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: Color(0xFF00B4D8),
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Text(
                        'متصل الآن',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF00B4D8),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),

          // Left (RTL end): Side menu and settings
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                icon: const Icon(
                  Icons.menu_rounded,
                  color: Color(0xFF334155),
                  size: 24,
                ),
                onPressed: () {
                  _chatScaffoldKey.currentState?.openDrawer();
                },
              ),
              PopupMenuButton<String>(
                icon: const Icon(
                  Icons.more_vert_rounded,
                  color: Color(0xFF334155),
                  size: 22,
                ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
            onSelected: (val) {
              if (val == 'new') _startNewSession();
              if (val == 'clear') setState(() => _messages.clear());
            },
            itemBuilder: (ctx) => [
              const PopupMenuItem(
                value: 'new',
                child: Row(
                  children: [
                    Icon(Icons.refresh_rounded, size: 18, color: Color(0xFF0096C7)),
                    SizedBox(width: 8),
                    Text('جلسة جديدة', style: TextStyle(fontFamily: 'Cairo')),
                  ],
                ),
              ),
              const PopupMenuItem(
                value: 'clear',
                child: Row(
                  children: [
                    Icon(Icons.delete_outline_rounded,
                        size: 18, color: Color(0xFFEF4444)),
                    SizedBox(width: 8),
                    Text('مسح الرسائل', style: TextStyle(fontFamily: 'Cairo')),
                  ],
                ),
              ),
            ],
          ),
            ],
          ),
        ],
      ),
    );
  }

  /// Sub-Header: Large Cyborg Avatar on Left, Name & Subtitle, and "جلسة جديدة" pill button on Right
  Widget _buildAssistantSubHeader() {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFF1F5F9), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 8,
        runSpacing: 6,
        children: [
          // Right (RTL start): Session restart button ("جلسة جديدة" with restart icon)
          InkWell(
            onTap: _startNewSession,
            borderRadius: BorderRadius.circular(20),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.tune_rounded,
                    size: 14,
                    color: Color(0xFF64748B),
                  ),
                  SizedBox(width: 6),
                  Text(
                    'جلسة جديدة',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF475569),
                    ),
                  ),
                  SizedBox(width: 4),
                  Icon(
                    Icons.restart_alt_rounded,
                    size: 15,
                    color: Color(0xFF0F172A),
                  ),
                ],
              ),
            ),
          ),

          // Left (RTL end): Assistant Name, "متصل الآن - استجابة فورية" and Cyborg Face Avatar
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _assistantName,
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 15.5,
                      fontWeight: FontWeight.w900,
                      color: Color(0xFF0F172A),
                      height: 1.2,
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: Color(0xFF00B4D8),
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Text(
                        'متصل الآن - استجابة فورية',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF00B4D8),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(width: 10),
              _buildCyborgAvatarCircle(radius: 22),
            ],
          ),
        ],
      ),
    );
  }

  /// Builds the circular cyborg face avatar with live speaking pulse & interactive full-screen popup
  Widget _buildCyborgAvatarCircle({double radius = 18}) {
    final audio = AvatarAudioService.instance;
    return ValueListenableBuilder<String>(
      valueListenable: audio.activeAvatarType,
      builder: (context, avatarType, _) {
        final isFemale = avatarType == 'female';
        final img = isFemale
            ? 'assets/images/avatar_female.png'
            : 'assets/images/avatar_male.jpg';

        return ValueListenableBuilder<bool>(
          valueListenable: audio.isSpeaking,
          builder: (context, isSpeaking, _) {
            return InkWell(
              onTap: _showLiveAvatarDialog,
              borderRadius: BorderRadius.circular(radius),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                width: radius * 2,
                height: radius * 2,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFFF1F5F9),
                  border: Border.all(
                    color: isSpeaking
                        ? const Color(0xFF00E5FF)
                        : const Color(0xFFE2E8F0),
                    width: isSpeaking ? 2.4 : 1.4,
                  ),
                  boxShadow: isSpeaking
                      ? [
                          BoxShadow(
                            color: const Color(0xFF00E5FF).withValues(alpha: 0.55),
                            blurRadius: 12,
                            spreadRadius: 2,
                          ),
                        ]
                      : null,
                ),
                clipBehavior: Clip.antiAlias,
                child: Image.asset(
                  img,
                  fit: BoxFit.cover,
                  alignment: Alignment.topCenter,
                  errorBuilder: (_, _, _) => Icon(
                    Icons.smart_toy_rounded,
                    color: const Color(0xFF00B4D8),
                    size: radius * 1.1,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _showLiveAvatarDialog() {
    showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'LiveAvatar',
      barrierColor: Colors.black.withValues(alpha: 0.45),
      transitionDuration: const Duration(milliseconds: 260),
      transitionBuilder: (context, anim1, anim2, child) {
        return ScaleTransition(
          scale: CurvedAnimation(parent: anim1, curve: Curves.easeOutBack),
          child: child,
        );
      },
      pageBuilder: (context, anim1, anim2) {
        return Center(
          child: Container(
            width: 360,
            height: 520,
            margin: const EdgeInsets.symmetric(horizontal: 20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(28),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.25),
                  blurRadius: 32,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              children: [
                Positioned.fill(
                  child: InteractiveAnimatedAvatar(
                    onAvatarTapped: () {},
                  ),
                ),
                Positioned(
                  top: 14,
                  left: 14,
                  child: InkWell(
                    onTap: () => Navigator.of(context).pop(),
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.85),
                        shape: BoxShape.circle,
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: const Icon(Icons.close_rounded,
                          size: 20, color: Color(0xFF475569)),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMessageItem(_ChatMessageItem msg) {
    final isUser = msg.role == 'user';

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment:
            isUser ? CrossAxisAlignment.start : CrossAxisAlignment.end,
        children: [
          // Date / Time badge for welcome message: "اليوم، 10:30 ص"
          if (msg.isWelcome)
            Center(
              child: Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFFEEF2F6),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  msg.time,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
            ),

          // Biometric voice verification badge for verified user voice
          if (isUser && msg.verifiedSpeaker != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 6, right: 4),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFFF0FDF4),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF86EFAC), width: 1),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.verified_user_rounded, size: 13, color: Color(0xFF16A34A)),
                    const SizedBox(width: 5),
                    Text(
                      'تم التحقق من نبرة الصوت: ${msg.verifiedSpeaker} ✓',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 10.5,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF15803D),
                      ),
                    ),
                  ],
                ),
              ),
            ),

          // Message Bubble Row
          Row(
            mainAxisAlignment:
                isUser ? MainAxisAlignment.start : MainAxisAlignment.end,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Assistant Avatar on the Left (RTL side)
              if (!isUser) ...[
                _buildCyborgAvatarCircle(radius: 19),
                const SizedBox(width: 10),
              ],

              // The Message Content Card
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    color: isUser
                        ? const Color(0xFF0056D2) // Electric Blue in Mockup
                        : Colors.white,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(22),
                      topRight: const Radius.circular(22),
                      bottomLeft: isUser
                          ? const Radius.circular(6)
                          : const Radius.circular(22),
                      bottomRight: isUser
                          ? const Radius.circular(22)
                          : const Radius.circular(6),
                    ),
                    border: isUser
                        ? null
                        : Border.all(
                            color: const Color(0xFFF1F5F9),
                            width: 1.2,
                          ),
                    boxShadow: [
                      BoxShadow(
                        color: isUser
                            ? const Color(0xFF0056D2).withValues(alpha: 0.28)
                            : const Color(0xFF0F172A).withValues(alpha: 0.04),
                        blurRadius: 16,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Voice message wave indicator
                      if (msg.isVoiceMessage) ...[
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.graphic_eq_rounded,
                              size: 16,
                              color: isUser ? const Color(0xFF67E8F9) : const Color(0xFF0284C7),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'رسالة صوتية مُحللة',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: isUser ? const Color(0xFF67E8F9) : const Color(0xFF0284C7),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                      ],

                      // Text message content
                      Text(
                        msg.content,
                        textAlign: TextAlign.right,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13.5,
                          fontWeight: FontWeight.w600,
                          color: isUser ? Colors.white : const Color(0xFF0F172A),
                          height: 1.55,
                        ),
                      ),

                      // Numbered Steps (e.g. 1, 2, 3 in circular pills from mockup)
                      if (msg.orderedSteps != null &&
                          msg.orderedSteps!.isNotEmpty) ...[
                        const SizedBox(height: 14),
                        ...List.generate(
                          msg.orderedSteps!.length,
                          (i) => _buildNumberedStepRow(
                            stepNumber: i + 1,
                            text: msg.orderedSteps![i],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              if (isUser) const SizedBox(width: 10),
            ],
          ),

          // Quick Action Pills under Assistant welcome message
          if (msg.quickActions != null && msg.quickActions!.isNotEmpty) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                alignment: WrapAlignment.end,
                children: msg.quickActions!.map((action) {
                  return InkWell(
                    onTap: () => _sendMessage(action),
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF0F9FF),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: const Color(0xFFBAE6FD),
                          width: 1.1,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            action.contains('أفكار')
                                ? Icons.lightbulb_outline_rounded
                                : action.contains('كتابة')
                                    ? Icons.edit_note_rounded
                                    : Icons.article_outlined,
                            size: 15,
                            color: const Color(0xFF0284C7),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            action,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 11.5,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0369A1),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ],

          // Footer Row for messages: Time, read receipts (user) or Copy/Like/Retry (assistant)
          const SizedBox(height: 4),
          Padding(
            padding: EdgeInsets.only(
              left: isUser ? 4 : 46,
              right: isUser ? 4 : 46,
            ),
            child: Row(
              mainAxisAlignment:
                  isUser ? MainAxisAlignment.start : MainAxisAlignment.spaceBetween,
              children: [
                if (isUser) ...[
                  // Read receipt checkmark and timestamp
                  const Icon(
                    Icons.done_all_rounded,
                    size: 14,
                    color: Color(0xFF00B4D8),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${msg.time} س',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF94A3B8),
                    ),
                  ),
                ] else ...[
                  // Assistant Footer: Time on left, Actions (Copy, Like, Retry) on right
                  Text(
                    '${msg.time} س',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF94A3B8),
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Audio voice playback with live lip-sync
                      InkWell(
                        onTap: () {
                          AvatarAudioService.instance.speak(
                            msg.content,
                            emotion: msg.emotion,
                            personalityId: _activePersonalityId,
                          );
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: const Padding(
                          padding: EdgeInsets.all(4),
                          child: Icon(
                            Icons.volume_up_rounded,
                            size: 16,
                            color: Color(0xFF00B4D8),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),

                      // Retry / Resend prompt icon
                      InkWell(
                        onTap: () => _sendMessage(msg.content),
                        borderRadius: BorderRadius.circular(16),
                        child: const Padding(
                          padding: EdgeInsets.all(4),
                          child: Icon(
                            Icons.refresh_rounded,
                            size: 16,
                            color: Color(0xFF94A3B8),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),

                      // Like Thumb icon
                      InkWell(
                        onTap: () {
                          setState(() {
                            if (_likedMessages.contains(msg.id)) {
                              _likedMessages.remove(msg.id);
                            } else {
                              _likedMessages.add(msg.id);
                            }
                          });
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: Padding(
                          padding: const EdgeInsets.all(4),
                          child: Icon(
                            _likedMessages.contains(msg.id)
                                ? Icons.thumb_up_rounded
                                : Icons.thumb_up_outlined,
                            size: 16,
                            color: _likedMessages.contains(msg.id)
                                ? const Color(0xFF00B4D8)
                                : const Color(0xFF94A3B8),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),

                      // Copy text icon
                      InkWell(
                        onTap: () {
                          Clipboard.setData(ClipboardData(text: msg.content));
                          showSuccessSnackbar(context, 'تم نسخ الرسالة إلى الحافظة');
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: const Padding(
                          padding: EdgeInsets.all(4),
                          child: Icon(
                            Icons.copy_rounded,
                            size: 16,
                            color: Color(0xFF94A3B8),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Numbered item for assistant list responses (1, 2, 3...)
  Widget _buildNumberedStepRow({
    required int stepNumber,
    required String text,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Circular Number Badge matching the mockup (Light cyan background with blue number)
          Container(
            width: 26,
            height: 26,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: Color(0xFFE0F2FE),
            ),
            child: Center(
              child: Text(
                '$stepNumber',
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  color: Color(0xFF0284C7),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),

          // Step description text
          Expanded(
            child: Text(
              text,
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(0xFF1E293B),
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Typing indicator row: "المساعد يكتب الآن..." with animated cyan dots and avatar
  Widget _buildTypingIndicatorBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFFE2E8F0)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF0F172A).withValues(alpha: 0.04),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  '...المساعد يكتب الآن',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF64748B),
                  ),
                ),
                const SizedBox(width: 8),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: List.generate(
                    3,
                    (i) => Container(
                      width: 5.5,
                      height: 5.5,
                      margin: const EdgeInsets.symmetric(horizontal: 1.5),
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Color(0xFF00B4D8),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          _buildCyborgAvatarCircle(radius: 17),
        ],
      ),
    );
  }

  /// Modern Input Bar matching mockup:
  /// Cyan send circle on right (LTR left) + Mic button + Pill input field with attachment paperclip
  Widget _buildModernInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(
          top: BorderSide(color: Color(0xFFF1F5F9), width: 1.2),
        ),
      ),
      child: Row(
        children: [
          // Send Button: Vibrant Cyan Circle with Send Icon
          Material(
            color: const Color(0xFF00C7E5),
            shape: const CircleBorder(),
            child: InkWell(
              onTap: _sending ? null : () => _sendMessage(),
              customBorder: const CircleBorder(),
              child: SizedBox(
                width: 48,
                height: 48,
                child: Center(
                  child: _sending
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(
                          Icons.send_rounded,
                          color: Colors.white,
                          size: 20,
                        ),
                ),
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Microphone Button: Circular subtle grey button
          Material(
            color: const Color(0xFFF8FAFC),
            shape: const CircleBorder(),
            child: InkWell(
              onTap: _recordAudioPrompt,
              customBorder: const CircleBorder(),
              child: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: const Icon(
                  Icons.mic_none_rounded,
                  color: Color(0xFF475569),
                  size: 22,
                ),
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Message Input Field Pill with Attachment Clip
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: [
                  // Attachment Paperclip
                  IconButton(
                    icon: const Icon(
                      Icons.attach_file_rounded,
                      color: Color(0xFF64748B),
                      size: 21,
                    ),
                    onPressed: _pickAttachment,
                    tooltip: 'إرفاق ملف',
                  ),

                  // Text Field
                  Expanded(
                    child: TextField(
                      controller: _inputCtrl,
                      textDirection: TextDirection.rtl,
                      textAlign: TextAlign.right,
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 13.5,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF0F172A),
                      ),
                      textInputAction: TextInputAction.send,
                      decoration: const InputDecoration(
                        hintText: 'اكتب رسالتك هنا...', 
                        hintStyle: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: Color(0xFF94A3B8),
                        ),
                        border: InputBorder.none,
                        contentPadding: EdgeInsets.symmetric(vertical: 10),
                      ),
                      onSubmitted: (_) => _sendMessage(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
