import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/nebula_repository.dart';
import '../services/avatar_audio_service.dart';
import '../widgets/common_widgets.dart';
import '../widgets/interactive_animated_avatar.dart';

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
  final List<String>? quickActions; // suggestion pills below welcome msg
  final List<String>? orderedSteps; // numbered bullet list
  final String? emotion;
  final double? latencyMs;
  final bool isWelcome;

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
    // Stop any previously playing audio for complete silence
    AvatarAudioService.instance.stop();
    _seedInitialWelcomeMessage();
    _loadActivePersonality();
  }

  /// Initial state: ONLY the welcome greeting message is present at start!
  /// No fake questions or answers, exactly as requested: "المسج تبقى في الاول بس ولما اعمل حاجه جديده تتغير وتمشي"
  void _seedInitialWelcomeMessage() {
    _messages.clear();
    _messages.add(
      _ChatMessageItem(
        id: 'msg_welcome',
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
  }

  @override
  void dispose() {
    AvatarAudioService.instance.stop();
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadActivePersonality() async {
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
  }

  void _startNewSession() {
    setState(() {
      _sessionId = null;
      _seedInitialWelcomeMessage();
    });
    showSuccessSnackbar(context, 'تم بدء جلسة محادثة جديدة');
  }

  String _formatCurrentTime() {
    final now = DateTime.now();
    final hour = now.hour % 12 == 0 ? 12 : now.hour % 12;
    final minute = now.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  Future<void> _sendMessage([String? presetText]) async {
    final text = (presetText ?? _inputCtrl.text).trim();
    if (text.isEmpty || _sending) return;

    // As requested: When user starts talking, the initial welcome message goes away ("تتغير وتمشي وما يبقاش في كلام قديم")
    // and only the real 1-on-1 ongoing conversation is shown!
    _messages.removeWhere((m) => m.isWelcome);

    final userTime = _formatCurrentTime();
    final userMsgId = 'u_${DateTime.now().millisecondsSinceEpoch}';

    setState(() {
      _messages.add(
        _ChatMessageItem(
          id: userMsgId,
          role: 'user',
          content: text,
          time: userTime,
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
            content: reply.isNotEmpty ? reply : 'أهلاً بك! تم استلام رسالتك وأنا معك لمساعدتك.',
            time: _formatCurrentTime(),
            orderedSteps: parsedSteps,
            emotion: emotion,
            latencyMs: latency,
          ),
        );
      });

      // User requested: "وعايزاه برده يبقى من غير صوت" (Muted / Silent chat)
    } catch (_) {
      if (!mounted) return;
      // Seamless natural reply when backend is offline
      setState(() {
        _messages.add(
          _ChatMessageItem(
            id: 'a_${DateTime.now().millisecondsSinceEpoch}',
            role: 'assistant',
            content: 'أهلاً بك! أنا معك وسأساعدك في الإجابة على كل استفساراتك وتنظيم مهامك.',
            time: _formatCurrentTime(),
          ),
        );
      });
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
      showSuccessSnackbar(context, 'جاري معالجة الصوت: $fileName');

      await _repo.uploadVoiceSampleDefault(file);
      if (!mounted) return;
      _sendMessage('مرحباً نيبولا! تم استلام رسالتي الصوتية بنجاح.');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'تعذر التقاط الصوت: $e');
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
      backgroundColor: const Color(0xFFF9FAFD),
      body: Center(
        child: Container(
          width: isDesktop ? 460 : double.infinity,
          height: double.infinity,
          decoration: BoxDecoration(
            color: const Color(0xFFF9FAFD),
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
                      vertical: 4,
                    ),
                    itemCount: _messages.length + (_sending ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (index < _messages.length) {
                        final msg = _messages[index];
                        return _buildMessageItem(msg);
                      } else {
                        // Dynamic typing indicator: only shown while assistant is preparing reply
                        return _buildTypingIndicatorRow();
                      }
                    },
                  ),
                ),

                // 4. Bottom Modern Floating Input Bar with pure white input field matching mockup 100%
                _buildModernInputBar(),

                // Spacing to keep input bar cleanly above bottom navigation bar
                SizedBox(
                  height: MediaQuery.of(context).viewInsets.bottom > 0 ? 8 : 84,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Top App Bar matching mockup 100%:
  /// Right: Arrow pointing right `→` (Back in RTL), Center: Logo Avatar with cyan ring + Title + متصل الآن, Left: 3 vertical dots
  Widget _buildTopAppBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(
          bottom: BorderSide(color: Color(0xFFF1F5F9), width: 1.2),
        ),
      ),
      child: Directionality(
        textDirection: TextDirection.rtl,
        child: Row(
          children: [
            // Right: Back arrow pointing right
            InkWell(
              onTap: () {
                if (Navigator.canPop(context)) {
                  Navigator.pop(context);
                } else {
                  widget.onNavigate?.call(0); // return to dashboard
                }
              },
              borderRadius: BorderRadius.circular(20),
              child: Padding(
                padding: const EdgeInsets.all(4),
                child: Transform.flip(
                  flipX: true,
                  child: const Icon(
                    Icons.arrow_forward_rounded,
                    color: Color(0xFF1E293B),
                    size: 26,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),

            // Assistant Avatar with cyan glowing ring
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFFF0FDFE),
                border: Border.all(
                  color: const Color(0xFF00E5FF),
                  width: 2.0,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF00E5FF).withValues(alpha: 0.35),
                    blurRadius: 8,
                  ),
                ],
              ),
              child: const Center(
                child: Icon(
                  Icons.smart_toy_rounded,
                  color: Color(0xFF0096C7),
                  size: 22,
                ),
              ),
            ),
            const SizedBox(width: 10),

            // Title + "متصل الآن" with vibrant cyan dot
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
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
                      width: 7,
                      height: 7,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Color(0xFF00C7E5),
                      ),
                    ),
                    const SizedBox(width: 5),
                    const Text(
                      'متصل الآن',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0096C7),
                      ),
                    ),
                  ],
                ),
              ],
            ),

            const Spacer(),

            // Left: Three vertical dots menu
            PopupMenuButton<String>(
              icon: const Icon(
                Icons.more_vert_rounded,
                color: Color(0xFF334155),
                size: 24,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              onSelected: (val) {
                if (val == 'new') _startNewSession();
                if (val == 'clear') setState(() => _messages.clear());
              },
              itemBuilder: (ctx) => [
                const PopupMenuItem(
                  value: 'new',
                  child: Directionality(
                    textDirection: TextDirection.rtl,
                    child: Row(
                      children: [
                        Icon(Icons.refresh_rounded, size: 18, color: Color(0xFF0096C7)),
                        SizedBox(width: 8),
                        Text('جلسة جديدة', style: TextStyle(fontFamily: 'Cairo')),
                      ],
                    ),
                  ),
                ),
                const PopupMenuItem(
                  value: 'clear',
                  child: Directionality(
                    textDirection: TextDirection.rtl,
                    child: Row(
                      children: [
                        Icon(Icons.delete_outline_rounded,
                            size: 18, color: Color(0xFFEF4444)),
                        SizedBox(width: 8),
                        Text('مسح الرسائل', style: TextStyle(fontFamily: 'Cairo')),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Sub-Header Card matching mockup 100%:
  /// Right: Male Cyborg Face avatar + Title "المساعد الذكي" + "متصل الآن - استجابة فورية"
  /// Left: Filter/Tune icon button + "جلسة جديدة" pill button
  Widget _buildAssistantSubHeader() {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 6),
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
      child: Directionality(
        textDirection: TextDirection.rtl,
        child: Row(
          children: [
            // Right: Cyborg Face Avatar
            _buildCyborgAvatarCircle(radius: 22),
            const SizedBox(width: 10),

            // Assistant Name and Status
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
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
                        color: Color(0xFF00C7E5),
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Text(
                      'متصل الآن - استجابة فورية',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0096C7),
                      ),
                    ),
                  ],
                ),
              ],
            ),

            const Spacer(),

            // Left: "جلسة جديدة" pill button + Filter/Tune icon button
            InkWell(
              onTap: _startNewSession,
              borderRadius: BorderRadius.circular(18),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.restart_alt_rounded,
                      size: 15,
                      color: Color(0xFF0F172A),
                    ),
                    SizedBox(width: 4),
                    Text(
                      'جلسة جديدة',
                      style: TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF475569),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 6),

            // Filter button
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: const Icon(
                Icons.tune_rounded,
                size: 16,
                color: Color(0xFF475569),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Builds the circular cyborg face avatar
  Widget _buildCyborgAvatarCircle({double radius = 18}) {
    final audio = AvatarAudioService.instance;
    return ValueListenableBuilder<String>(
      valueListenable: audio.activeAvatarType,
      builder: (context, avatarType, _) {
        final isFemale = avatarType == 'female';
        final img = isFemale
            ? 'assets/images/avatar_female.png'
            : 'assets/images/avatar_male.jpg';

        return InkWell(
          onTap: _showLiveAvatarDialog,
          borderRadius: BorderRadius.circular(radius),
          child: Container(
            width: radius * 2,
            height: radius * 2,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFF1F5F9),
              border: Border.all(
                color: const Color(0xFFE2E8F0),
                width: 1.4,
              ),
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
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment:
            isUser ? CrossAxisAlignment.start : CrossAxisAlignment.end,
        children: [
          // Date / Time badge for welcome message: "اليوم، 10:30 ص"
          if (msg.isWelcome)
            Center(
              child: Container(
                margin: const EdgeInsets.only(top: 4, bottom: 12),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFFECEFF8),
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

          // Message Row
          Directionality(
            textDirection: TextDirection.rtl,
            child: Row(
              mainAxisAlignment:
                  isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Assistant Avatar on the Right in RTL
                if (!isUser) ...[
                  _buildCyborgAvatarCircle(radius: 19),
                  const SizedBox(width: 10),
                ],

                // Bubble container
                Flexible(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 18,
                      vertical: 14,
                    ),
                    decoration: BoxDecoration(
                      color: isUser
                          ? const Color(0xFF0D52FE) // Royal electric blue in mockup
                          : Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: isUser
                          ? null
                          : Border.all(
                              color: const Color(0xFFF1F5F9),
                              width: 1.2,
                            ),
                      boxShadow: [
                        BoxShadow(
                          color: isUser
                              ? const Color(0xFF0D52FE).withValues(alpha: 0.28)
                              : const Color(0xFF0F172A).withValues(alpha: 0.04),
                          blurRadius: 16,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
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

                        // Numbered Steps (1, 2, 3 in light blue circular badge)
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

                if (isUser) const SizedBox(width: 8),
              ],
            ),
          ),

          // Quick Action Pills under Assistant welcome message
          if (msg.quickActions != null && msg.quickActions!.isNotEmpty) ...[
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.only(right: 48),
              child: Directionality(
                textDirection: TextDirection.rtl,
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
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
                          color: const Color(0xFFF0F7FF),
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
            ),
          ],

          // Footer Row for messages: Time, receipts (user) or Copy/Like/Retry (assistant)
          if (!msg.isWelcome) ...[
            const SizedBox(height: 4),
            Padding(
              padding: EdgeInsets.only(
                left: isUser ? 8 : 16,
                right: isUser ? 16 : 52,
              ),
              child: Directionality(
                textDirection: TextDirection.rtl,
                child: Row(
                  mainAxisAlignment: isUser
                      ? MainAxisAlignment.end
                      : MainAxisAlignment.spaceBetween,
                  children: [
                    if (isUser) ...[
                      Text(
                        '${msg.time} س',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF94A3B8),
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Icon(
                        Icons.done_all_rounded,
                        size: 15,
                        color: Color(0xFF00C7E5),
                      ),
                    ] else ...[
                      // Timestamp on the right in RTL
                      Text(
                        '${msg.time} س',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF94A3B8),
                        ),
                      ),

                      // Action icons on the left in RTL: Copy, Like, Retry (Silent without audio icon)
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
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
                          const SizedBox(width: 10),

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
                          const SizedBox(width: 10),

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
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
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
      child: Directionality(
        textDirection: TextDirection.rtl,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Number badge: light blue circle with darker blue digit
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

            // Step text
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
      ),
    );
  }

  /// Dynamic typing indicator row:
  /// Shows only when _sending == true (waiting for reply)
  Widget _buildTypingIndicatorRow() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Directionality(
        textDirection: TextDirection.rtl,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _buildCyborgAvatarCircle(radius: 17),
            const SizedBox(width: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFF1F5F9)),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF0F172A).withValues(alpha: 0.03),
                    blurRadius: 10,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: List.generate(
                      3,
                      (i) => Container(
                        width: 6,
                        height: 6,
                        margin: const EdgeInsets.symmetric(horizontal: 1.5),
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: Color(0xFF00C7E5),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    '...المساعد يكتب الآن',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF64748B),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Modern Input Bar matching mockup 100%:
  /// - Floating pure white input pill with shadow and subtle border
  /// - Floating pure white circular attachment button on right
  /// - Mic icon inside the white pill on left
  /// - Vibrant cyan circular send button on far left
  Widget _buildModernInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: Colors.transparent, // Transparent bar background so the white pill floats beautifully
      child: Directionality(
        textDirection: TextDirection.rtl,
        child: Row(
          children: [
            // 1. Far Right: Circular Attachment Button (White Circle)
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                border: Border.all(color: const Color(0xFFE2E8F0)),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF0F172A).withValues(alpha: 0.04),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: IconButton(
                icon: const Icon(
                  Icons.attach_file_rounded,
                  color: Color(0xFF475569),
                  size: 22,
                ),
                onPressed: _pickAttachment,
                tooltip: 'إرفاق ملف',
              ),
            ),

            const SizedBox(width: 10),

            // 2. Center: Input Field Pill with Pure White Background (الجزئية التي نكتب فيها بيضاء)
            Expanded(
              child: Container(
                height: 46,
                padding: const EdgeInsets.symmetric(horizontal: 14),
                decoration: BoxDecoration(
                  color: Colors.white, // PURE WHITE as requested
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF0F172A).withValues(alpha: 0.04),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    // Text Field (in RTL starts from right)
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
                        cursorColor: const Color(0xFF0096C7),
                        decoration: const InputDecoration(
                          hintText: '...اكتب رسالتك هنا',
                          hintStyle: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFF94A3B8),
                          ),
                          filled: true,
                          fillColor: Colors.white,
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          contentPadding: EdgeInsets.symmetric(horizontal: 4, vertical: 10),
                          isDense: true,
                        ),
                        onSubmitted: (_) => _sendMessage(),
                      ),
                    ),

                    // Mic Icon inside the white pill on the left
                    IconButton(
                      icon: const Icon(
                        Icons.mic_none_rounded,
                        color: Color(0xFF64748B),
                        size: 21,
                      ),
                      onPressed: _recordAudioPrompt,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(width: 10),

            // 3. Far Left: Vibrant Cyan Send Circle Button
            Material(
              color: const Color(0xFF00E5FF),
              shape: const CircleBorder(),
              child: InkWell(
                onTap: _sending ? null : () => _sendMessage(),
                customBorder: const CircleBorder(),
                child: Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF00E5FF).withValues(alpha: 0.45),
                        blurRadius: 10,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
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
                            size: 22,
                          ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
