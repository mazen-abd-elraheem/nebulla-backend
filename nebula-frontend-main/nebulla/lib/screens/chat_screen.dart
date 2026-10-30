import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../services/nebula_repository.dart';
import '../widgets/common_widgets.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatMessage {
  final String role; // 'user' | 'assistant'
  final String content;
  final String? emotion;
  final double? latencyMs;

  _ChatMessage(
      {required this.role,
      required this.content,
      this.emotion,
      this.latencyMs});
}

class _ChatScreenState extends State<ChatScreen> {
  final _repo = NebulaRepository.instance;
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();

  final List<_ChatMessage> _messages = [];
  String? _sessionId;
  bool _sending = false;

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _sending) return;

    setState(() {
      _messages.add(_ChatMessage(role: 'user', content: text));
      _sending = true;
    });
    _inputCtrl.clear();
    _scrollToBottom();

    try {
      final data = await _repo.chat(text, sessionId: _sessionId);
      _sessionId = data['session_id'] as String?;
      setState(() {
        _messages.add(_ChatMessage(
          role: 'assistant',
          content: data['reply'] as String? ?? '',
          emotion: data['emotion'] as String?,
          latencyMs: (data['llm_latency_ms'] as num?)?.toDouble(),
        ));
      });
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'خطأ في الإرسال: $e');
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
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
              // App bar
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 12),
                decoration: const BoxDecoration(
                  color: AppColors.surface,
                  border: Border(
                      bottom: BorderSide(
                          color: AppColors.cardBorder, width: 1)),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: AppColors.tealGradient,
                        boxShadow: [
                          BoxShadow(
                              color: AppColors.teal.withValues(alpha: 0.4),
                              blurRadius: 10)
                        ],
                      ),
                      child: Icon(Icons.smart_toy_outlined,
                          color: AppColors.bg, size: 20),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('محادثة نيبولا',
                              style: TextStyle(
                                  fontFamily: 'Cairo',
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.textPrimary,
                                  fontSize: 15)),
                          Text('مدعوم بالذكاء الاصطناعي',
                              style: TextStyle(
                                  fontFamily: 'Cairo',
                                  color: AppColors.teal,
                                  fontSize: 11)),
                        ],
                      ),
                    ),
                    if (_sessionId != null)
                      IconButton(
                        icon: const Icon(Icons.add_comment_outlined,
                            color: AppColors.teal, size: 20),
                        onPressed: () =>
                            setState(() {
                              _messages.clear();
                              _sessionId = null;
                            }),
                        tooltip: 'محادثة جديدة',
                      ),
                  ],
                ),
              ),
              // Messages
              Expanded(
                child: _messages.isEmpty
                    ? _EmptyChat()
                    : ListView.builder(
                        controller: _scrollCtrl,
                        padding: const EdgeInsets.all(16),
                        itemCount: _messages.length,
                        itemBuilder: (_, i) =>
                            _MessageBubble(msg: _messages[i]),
                      ),
              ),
              // Typing indicator
              if (_sending) _TypingIndicator(),
              // Input bar
              _InputBar(
                controller: _inputCtrl,
                onSend: _send,
                enabled: !_sending,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyChat extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: [
                AppColors.teal.withValues(alpha: 0.15),
                AppColors.purple.withValues(alpha: 0.15),
              ]),
              border: Border.all(
                  color: AppColors.teal.withValues(alpha: 0.3)),
            ),
            child: const Icon(Icons.chat_outlined,
                color: AppColors.teal, size: 36),
          ),
          const SizedBox(height: 16),
          const Text('ابدأ محادثتك مع نيبولا',
              style: TextStyle(
                  fontFamily: 'Cairo',
                  color: AppColors.textSecondary,
                  fontSize: 15)),
          const SizedBox(height: 8),
          const Text('اكتب رسالتك في الأسفل',
              style: TextStyle(
                  fontFamily: 'Cairo',
                  color: AppColors.textMuted,
                  fontSize: 13)),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final _ChatMessage msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: AppColors.tealGradient,
              ),
              child: Icon(Icons.smart_toy_outlined,
                  color: AppColors.bg, size: 16),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment: isUser
                  ? CrossAxisAlignment.end
                  : CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    gradient: isUser
                        ? AppColors.tealGradient
                        : null,
                    color: isUser ? null : AppColors.card,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(16),
                      topRight: const Radius.circular(16),
                      bottomLeft: isUser
                          ? const Radius.circular(16)
                          : const Radius.circular(4),
                      bottomRight: isUser
                          ? const Radius.circular(4)
                          : const Radius.circular(16),
                    ),
                    border: isUser
                        ? null
                        : Border.all(color: AppColors.cardBorder),
                    boxShadow: isUser
                        ? [
                            BoxShadow(
                                color:
                                    AppColors.teal.withValues(alpha: 0.3),
                                blurRadius: 8,
                                offset: const Offset(0, 2))
                          ]
                        : null,
                  ),
                  child: Text(
                    msg.content,
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      color: isUser ? AppColors.bg : AppColors.textPrimary,
                      fontSize: 14,
                      height: 1.6,
                    ),
                    textDirection: TextDirection.rtl,
                  ),
                ),
                if (!isUser && (msg.emotion != null || msg.latencyMs != null))
                  Padding(
                    padding: const EdgeInsets.only(top: 4, right: 4, left: 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (msg.emotion != null)
                          Text(
                            '${_emotionEmoji(msg.emotion!)} ${msg.emotion}',
                            style: const TextStyle(
                                color: AppColors.textMuted,
                                fontSize: 11,
                                fontFamily: 'Cairo'),
                          ),
                        if (msg.latencyMs != null) ...[
                          const SizedBox(width: 8),
                          Text(
                            '${msg.latencyMs!.toStringAsFixed(0)} ms',
                            style: const TextStyle(
                                color: AppColors.textMuted, fontSize: 11),
                          ),
                        ],
                      ],
                    ),
                  ),
              ],
            ),
          ),
          if (isUser) const SizedBox(width: 8),
        ],
      ),
    );
  }

  String _emotionEmoji(String emotion) {
    const map = {
      'happy': '😊',
      'sad': '😢',
      'curious': '🤔',
      'excited': '🤩',
      'neutral': '😐',
      'angry': '😤',
    };
    return map[emotion.toLowerCase()] ?? '💬';
  }
}

class _TypingIndicator extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
                shape: BoxShape.circle, gradient: AppColors.tealGradient),
            child: Icon(Icons.smart_toy_outlined,
                color: AppColors.bg, size: 16),
          ),
          const SizedBox(width: 12),
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.cardBorder),
            ),
            child: const SizedBox(
              width: 40,
              height: 16,
              child: _DotsLoader(),
            ),
          ),
        ],
      ),
    );
  }
}

class _DotsLoader extends StatefulWidget {
  const _DotsLoader();

  @override
  State<_DotsLoader> createState() => _DotsLoaderState();
}

class _DotsLoaderState extends State<_DotsLoader>
    with TickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, child) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(3, (i) {
            final t = (_ctrl.value - i * 0.2).clamp(0.0, 1.0);
            final opacity = (t < 0.5 ? t * 2 : (1 - t) * 2).clamp(0.3, 1.0);
            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 2),
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                color: AppColors.teal.withValues(alpha: opacity),
                shape: BoxShape.circle,
              ),
            );
          }),
        );
      },
    );
  }
}

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  final bool enabled;

  const _InputBar(
      {required this.controller,
      required this.onSend,
      required this.enabled});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border:
            Border(top: BorderSide(color: AppColors.cardBorder, width: 1)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              textDirection: TextDirection.rtl,
              style: const TextStyle(
                  color: AppColors.textPrimary, fontFamily: 'Cairo'),
              maxLines: 3,
              minLines: 1,
              decoration: InputDecoration(
                hintText: 'اكتب رسالتك...',
                hintStyle: const TextStyle(
                    color: AppColors.textMuted, fontFamily: 'Cairo'),
                filled: true,
                fillColor: AppColors.card,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: const BorderSide(color: AppColors.cardBorder),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: const BorderSide(color: AppColors.cardBorder),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide:
                      const BorderSide(color: AppColors.teal, width: 1.5),
                ),
                contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 10),
              ),
              onSubmitted: (_) => onSend(),
            ),
          ),
          const SizedBox(width: 10),
          GestureDetector(
            onTap: enabled ? onSend : null,
            child: Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: enabled
                    ? AppColors.tealGradient
                    : const LinearGradient(
                        colors: [AppColors.tealDim, AppColors.tealDim]),
                boxShadow: enabled
                    ? [
                        BoxShadow(
                            color: AppColors.teal.withValues(alpha: 0.4),
                            blurRadius: 10)
                      ]
                    : null,
              ),
              child: const Icon(Icons.send, color: AppColors.bg, size: 20),
            ),
          ),
        ],
      ),
    );
  }
}

