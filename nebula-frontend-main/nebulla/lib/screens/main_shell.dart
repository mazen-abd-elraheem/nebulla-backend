import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/locale_service.dart';
import '../services/local_reminder_alert_service.dart';
import 'dashboard_screen.dart';
import 'chat_screen.dart';
import 'memory_personas_screen.dart';
import 'persona_memory_specs_screen.dart';
import 'profile_screen.dart';
import 'diagnostics_screen.dart';
import 'settings_screen.dart';
import 'contacts_screen.dart';
import 'notes_reminders_screen.dart';
import '../widgets/nebula_side_menu.dart';
import '../widgets/global_footer.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key, this.initialIndex = 2});
  final int initialIndex;

  static void navigateTo(BuildContext context, int index) {
    final state = context.findAncestorStateOfType<_MainShellState>();
    if (state != null) {
      state._onNavigate(index);
    } else {
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => MainShell(initialIndex: index)),
        (route) => false,
      );
    }
  }

  static void openSideMenu(BuildContext context) {
    final state = context.findAncestorStateOfType<_MainShellState>();
    state?._openDrawer();
  }

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  final GlobalKey<ScaffoldState> _shellScaffoldKey = GlobalKey<ScaffoldState>();
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    LocalReminderAlertService.instance.start();
  }

  @override
  void dispose() {
    LocalReminderAlertService.instance.stop();
    super.dispose();
  }

  void _onNavigate(int index) {
    if (index >= 0 && index < 9) {
      setState(() => _currentIndex = index);
    }
  }

  void _openDrawer() {
    _shellScaffoldKey.currentState?.openEndDrawer();
  }

  void _closeDrawer() {
    _shellScaffoldKey.currentState?.closeEndDrawer();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: LocaleService.instance,
      builder: (context, _) {
        final screens = [
          MemoryPersonasScreen(
            onNavigate: _onNavigate,
            isActive: _currentIndex == 0,
          ),
          ChatScreen(onNavigate: _onNavigate),
          DashboardScreen(onNavigate: _onNavigate),
          PersonaMemorySpecsScreen(
            onNavigate: _onNavigate,
            isActive: _currentIndex == 3,
          ),
          ProfileScreen(key: ValueKey('profile_${LocaleService.instance.languageCode}')),
          DiagnosticsScreen(key: ValueKey('diag_${LocaleService.instance.languageCode}')),
          SettingsScreen(key: ValueKey('settings_${LocaleService.instance.languageCode}')),
          ContactsScreen(onNavigate: _onNavigate),
          NotesRemindersScreen(
            onNavigate: _onNavigate,
            isActive: _currentIndex == 8,
          ),
        ];

        // Sidebar: In RTL (Arabic) endDrawer opens from LEFT.
        // In LTR (English) endDrawer opens from RIGHT.
        final sidebarDrawer = Drawer(
          backgroundColor: Colors.transparent,
          elevation: 0,
          child: NebulaSideMenu(
            activeIndex: _currentIndex,
            onNavigate: (idx) {
              _closeDrawer();
              _onNavigate(idx);
            },
            onClose: _closeDrawer,
          ),
        );

        return Scaffold(
          key: _shellScaffoldKey,
          backgroundColor: Colors.white,
          endDrawer: sidebarDrawer,
          body: Stack(
            children: [
              // Current active screen
              IndexedStack(index: _currentIndex, children: screens),

              // Client-side In-App Reminder Alert Banner (matches app light UI)
              ValueListenableBuilder<ReminderNoteItem?>(
                valueListenable: LocalReminderAlertService.instance.activeAlert,
                builder: (context, alertItem, _) {
                  if (alertItem == null) return const SizedBox.shrink();
                  return Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: SafeArea(
                      bottom: false,
                      child: _InAppReminderBanner(
                        item: alertItem,
                        onComplete: () =>
                            LocalReminderAlertService.instance.completeCurrent(),
                        onSnooze: () =>
                            LocalReminderAlertService.instance.snoozeCurrent(),
                        onDismiss: () =>
                            LocalReminderAlertService.instance.dismissCurrent(),
                        onOpenReminders: () {
                          LocalReminderAlertService.instance.dismissCurrent();
                          _onNavigate(8);
                        },
                      ),
                    ),
                  );
                },
              ),

              // Global Unified Glass Footer matching user reference image
              if (MediaQuery.of(context).viewInsets.bottom == 0)
                Align(
                  alignment: Alignment.bottomCenter,
                  child: GlobalNebulaFooter(
                    activeIndex: _currentIndex,
                    onNavigate: _onNavigate,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _InAppReminderBanner extends StatelessWidget {
  final ReminderNoteItem item;
  final VoidCallback onComplete;
  final VoidCallback onSnooze;
  final VoidCallback onDismiss;
  final VoidCallback onOpenReminders;

  const _InAppReminderBanner({
    required this.item,
    required this.onComplete,
    required this.onSnooze,
    required this.onDismiss,
    required this.onOpenReminders,
  });

  String _formatTime(DateTime? dt) {
    if (dt == null) return '';
    final h24 = dt.hour;
    final period = h24 >= 12 ? 'م' : 'ص';
    final h12 = (h24 % 12 == 0) ? 12 : (h24 % 12);
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h12:$m $period';
  }

  @override
  Widget build(BuildContext context) {
    final isMedicine = item.reminderType == 'medicine';
    final isAppointment = item.reminderType == 'appointment';
    final accentColor = isMedicine
        ? const Color(0xFFDB2777)
        : (isAppointment ? const Color(0xFF7C3AED) : const Color(0xFF0284C7));
    final badgeBg = isMedicine
        ? const Color(0xFFFCE7F3)
        : (isAppointment ? const Color(0xFFF3E8FF) : const Color(0xFFE0F2FE));
    final iconData = isMedicine
        ? Icons.medication_rounded
        : (isAppointment
              ? Icons.event_rounded
              : Icons.notifications_active_rounded);
    final typeLabel = isMedicine
        ? 'تذكير دواء'
        : (isAppointment ? 'تذكير موعد' : 'تذكير مهمة');

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: accentColor.withValues(alpha: 0.35),
                width: 1.4,
              ),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF0F172A).withValues(alpha: 0.12),
                  blurRadius: 22,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: badgeBg,
                        borderRadius: BorderRadius.circular(13),
                      ),
                      child: Icon(iconData, color: accentColor, size: 22),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: GestureDetector(
                        onTap: onOpenReminders,
                        behavior: HitTestBehavior.opaque,
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
                                    color: badgeBg,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Text(
                                    typeLabel,
                                    style: TextStyle(
                                      fontFamily: 'Cairo',
                                      fontSize: 10.5,
                                      fontWeight: FontWeight.w800,
                                      color: accentColor,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  _formatTime(item.targetTime),
                                  style: const TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF64748B),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              item.title,
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 14,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                            if ((item.description ?? '').trim().isNotEmpty) ...[
                              const SizedBox(height: 2),
                              Text(
                                (item.description ?? '').trim(),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 12,
                                  color: Color(0xFF475569),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                    InkWell(
                      onTap: onDismiss,
                      borderRadius: BorderRadius.circular(10),
                      child: const Padding(
                        padding: EdgeInsets.all(4),
                        child: Icon(
                          Icons.close_rounded,
                          size: 18,
                          color: Color(0xFF64748B),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: onComplete,
                        icon: const Icon(Icons.check_rounded, size: 16),
                        label: const Text(
                          'تم الإنجاز',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF00B4D8),
                          foregroundColor: Colors.white,
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton.icon(
                      onPressed: onSnooze,
                      icon: const Icon(Icons.snooze_rounded, size: 16),
                      label: const Text(
                        'تأجيل 10 د',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF334155),
                        side: const BorderSide(color: Color(0xFFCBD5E1)),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 8,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
