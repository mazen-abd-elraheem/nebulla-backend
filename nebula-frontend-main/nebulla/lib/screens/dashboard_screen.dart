import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';

/// Full interactive animated avatar home screen matching Image 2 mockup.
class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const DashboardScreen({super.key, this.onNavigate});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _audioService = AvatarAudioService.instance;
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  void _openMenu() {
    NebulaSideMenu.show(
      context,
      activeIndex: 0,
      onNavigate: (idx) {
        if (widget.onNavigate != null && idx >= 0) {
          widget.onNavigate!(idx);
        }
      },
    );
  }

  void _triggerAvatarGreeting() {
    final isFemale = _audioService.activeAvatarType.value == 'female';
    final name = _audioService.activePersonaName.value;
    final greeting = isFemale
        ? 'مرحباً بك! أنا $name، جاهزة لمساعدتك في أي استفسار.'
        : 'أهلاً بك! أنا $name، مستعد لمساعدتك وإنجاز مهامك فوراً.';
    _audioService.speak(greeting, emotion: 'happy');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: Colors.white,
      drawer: Drawer(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: NebulaSideMenu(
          activeIndex: 0,
          onNavigate: (idx) {
            _scaffoldKey.currentState?.closeDrawer();
            if (widget.onNavigate != null && idx >= 0) {
              widget.onNavigate!(idx);
            }
          },
          onClose: () => _scaffoldKey.currentState?.closeDrawer(),
        ),
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Full-Screen Interactive Animated Character (Cleaned Background, Organic Motion)
          Positioned.fill(
            child: InteractiveAnimatedAvatar(
              fullScreen: true,
              onAvatarTapped: _triggerAvatarGreeting,
              onAvatarDoubleTapped: () {
                final current = _audioService.activeAvatarType.value;
                final next = current == 'female' ? 'male' : 'female';
                _audioService.switchAvatar(next);
                _triggerAvatarGreeting();
              },
            ),
          ),

          // 2. Top Header Bar matching Image 2 100%:
          // - LEFT: Hamburger Menu Button (opens side menu modal immediately)
          // - CENTER: Live Green Status Dot
          // - RIGHT: Notification Bell Button
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: Directionality(
                  textDirection: TextDirection.ltr, // Enforces Left=Menu, Right=Bell
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // LEFT: Circular Hamburger Menu Button -> Opens Side Menu
                      GestureDetector(
                        onTap: _openMenu,
                        behavior: HitTestBehavior.opaque,
                        child: Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.95),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFFE2E8F0),
                              width: 1.2,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.08),
                                blurRadius: 10,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.menu_rounded,
                            color: Color(0xFF1E293B),
                            size: 24,
                          ),
                        ),
                      ),

                      // CENTER: Green Online Status Dot with subtle pulse
                      Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                          color: const Color(0xFF10B981),
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF10B981).withValues(alpha: 0.7),
                              blurRadius: 8,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                      ),

                      // RIGHT: Circular Notification Bell Button
                      GestureDetector(
                        onTap: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                'النظام متصل وجاهز للعمل • التزامن الصوتي مفعّل 100%',
                                style: TextStyle(fontFamily: 'Cairo'),
                              ),
                              behavior: SnackBarBehavior.floating,
                              duration: Duration(seconds: 2),
                            ),
                          );
                        },
                        behavior: HitTestBehavior.opaque,
                        child: Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.95),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFFE2E8F0),
                              width: 1.2,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.08),
                                blurRadius: 10,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.notifications_none_rounded,
                            color: Color(0xFF1E293B),
                            size: 24,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // 3. Floating Persona Switcher Pill (Quick Switch between Persona 1 & Persona 2)
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.only(top: 58),
                child: ValueListenableBuilder<String>(
                  valueListenable: _audioService.activeAvatarType,
                  builder: (context, activeType, _) {
                    final isFemale = activeType == 'female';

                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.92),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.06),
                            blurRadius: 12,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Persona 1: Male
                          _buildPersonaOption(
                            title: 'الشخصية 1',
                            subtitle: 'AI - 01',
                            avatarPath: 'assets/images/avatar_male.jpg',
                            isSelected: !isFemale,
                            onTap: () {
                              _audioService.switchAvatar('male');
                              _triggerAvatarGreeting();
                            },
                          ),
                          const SizedBox(width: 4),
                          // Persona 2: Female
                          _buildPersonaOption(
                            title: 'الشخصية 2',
                            subtitle: 'AI - 02',
                            avatarPath: 'assets/images/avatar_female.png',
                            isSelected: isFemale,
                            onTap: () {
                              _audioService.switchAvatar('female');
                              _triggerAvatarGreeting();
                            },
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ),
          ),

          // 4. Interactive Voice & Action Card (Floating above bottom navigation)
          Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 92, left: 20, right: 20),
              child: _buildBottomInteractionCard(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPersonaOption({
    required String title,
    required String subtitle,
    required String avatarPath,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isSelected
              ? const Color(0xFF0284C7).withValues(alpha: 0.12)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? const Color(0xFF0284C7) : Colors.transparent,
            width: 1.2,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.asset(
                avatarPath,
                width: 22,
                height: 22,
                fit: BoxFit.cover,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              title,
              style: TextStyle(
                fontFamily: 'Cairo',
                fontSize: 11.5,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                color: isSelected ? const Color(0xFF0284C7) : const Color(0xFF64748B),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomInteractionCard() {
    return ValueListenableBuilder<bool>(
      valueListenable: _audioService.isSpeaking,
      builder: (context, isSpeaking, _) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.94),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0xFFE2E8F0)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            children: [
              // Voice / Speak Trigger Button
              GestureDetector(
                onTap: _triggerAvatarGreeting,
                behavior: HitTestBehavior.opaque,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: isSpeaking
                          ? [const Color(0xFF10B981), const Color(0xFF059669)]
                          : [const Color(0xFF0072FF), const Color(0xFF00C6FF)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: (isSpeaking
                                ? const Color(0xFF10B981)
                                : const Color(0xFF0072FF))
                            .withValues(alpha: 0.4),
                        blurRadius: 10,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
                  child: Icon(
                    isSpeaking ? Icons.graphic_eq_rounded : Icons.volume_up_rounded,
                    color: Colors.white,
                    size: 22,
                  ),
                ),
              ),
              const SizedBox(width: 12),

              // Status text
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isSpeaking ? 'الشخصية تتحدث الآن...' : 'اضغط للتحدث أو الاستماع',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                        color: Color(0xFF1E293B),
                      ),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      isSpeaking
                          ? 'تزامن صوتي وحركي نشط'
                          : 'توليد صوت ذكي متزامن مع حركة الشخصية',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 10.5,
                        color: Color(0xFF64748B),
                      ),
                    ),
                  ],
                ),
              ),

              // Chat quick action button
              GestureDetector(
                onTap: () {
                  if (widget.onNavigate != null) {
                    widget.onNavigate!(1); // Go to Chat
                  }
                },
                behavior: HitTestBehavior.opaque,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.chat_bubble_outline_rounded,
                        size: 15,
                        color: Color(0xFF0284C7),
                      ),
                      SizedBox(width: 4),
                      Text(
                        'دردشة',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF0284C7),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
