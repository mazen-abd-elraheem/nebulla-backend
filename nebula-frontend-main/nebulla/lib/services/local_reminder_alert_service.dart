import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import '../models/models.dart';
import 'nebula_repository.dart';

/// Client-side in-app reminder alert scheduler.
/// Checks pending tasks/reminders locally in the UI and raises an in-app
/// alert banner when a reminder's scheduled time arrives — without relying
/// on server-pushed notifications.
class LocalReminderAlertService {
  LocalReminderAlertService._();
  static final LocalReminderAlertService instance =
      LocalReminderAlertService._();

  final ValueNotifier<ReminderNoteItem?> activeAlert = ValueNotifier(null);
  final ValueNotifier<int> remindersVersion = ValueNotifier(0);

  List<ReminderNoteItem> _items = [];
  final Set<int> _dismissedIds = {};
  final Map<int, DateTime> _snoozedUntil = {};
  Timer? _tickTimer;
  bool _started = false;

  void start() {
    if (_started) return;
    _started = true;
    refreshFromBackend();
    _tickTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _checkDueReminders(),
    );
  }

  void stop() {
    _tickTimer?.cancel();
    _tickTimer = null;
    _started = false;
  }

  Future<void> refreshFromBackend() async {
    try {
      final fetched = await NebulaRepository.instance.getReminders(
        activeOnly: true,
      );
      syncItems(fetched);
    } catch (_) {
      // Silently ignore when offline or unauthenticated; local items still work.
    }
  }

  void syncItems(List<ReminderNoteItem> items) {
    _items = List<ReminderNoteItem>.from(items);
    // Clear dismissed state for items whose targetTime was rescheduled to the future.
    final now = DateTime.now();
    for (final item in _items) {
      if (item.targetTime.isAfter(now)) {
        _dismissedIds.remove(item.id);
      }
    }
    // If active alert was deleted or completed, close it.
    final current = activeAlert.value;
    if (current != null) {
      final stillPending = _items.any(
        (e) => e.id == current.id && !e.isCompleted && !e.isNote,
      );
      if (!stillPending) {
        activeAlert.value = null;
      }
    }
    _checkDueReminders();
  }

  void _checkDueReminders() {
    if (activeAlert.value != null) return;
    final now = DateTime.now();

    ReminderNoteItem? dueItem;
    for (final item in _items) {
      if (item.isNote || item.isCompleted) continue;
      if (_dismissedIds.contains(item.id)) continue;

      final snoozeTime = _snoozedUntil[item.id];
      if (snoozeTime != null && snoozeTime.isAfter(now)) continue;

      final target = item.targetTime;

      // Trigger if target time has arrived (and within last 24h so ancient stale items don't spam).
      final diff = now.difference(target);
      if (!target.isAfter(now) && diff.inHours < 24) {
        dueItem = item;
        break;
      }
    }

    if (dueItem != null) {
      activeAlert.value = dueItem;
      SystemSound.play(SystemSoundType.alert);
    }
  }

  void dismissCurrent() {
    final current = activeAlert.value;
    if (current != null) {
      _dismissedIds.add(current.id);
      activeAlert.value = null;
    }
  }

  void snoozeCurrent({Duration duration = const Duration(minutes: 10)}) {
    final current = activeAlert.value;
    if (current != null) {
      _snoozedUntil[current.id] = DateTime.now().add(duration);
      _dismissedIds.remove(current.id);
      activeAlert.value = null;
    }
  }

  Future<void> completeCurrent() async {
    final current = activeAlert.value;
    if (current == null) return;
    _dismissedIds.add(current.id);
    activeAlert.value = null;

    // Optimistically mark locally as completed
    final idx = _items.indexWhere((e) => e.id == current.id);
    if (idx >= 0) {
      _items[idx] = ReminderNoteItem(
        id: current.id,
        title: current.title,
        description: current.description,
        reminderType: current.reminderType,
        targetTime: current.targetTime,
        recurrence: current.recurrence,
        status: 'acknowledged',
        createdAt: current.createdAt,
      );
      remindersVersion.value++;
    }

    try {
      await NebulaRepository.instance.acknowledgeReminder(current.id);
    } catch (_) {
      // Keep local completion even if network fails temporarily.
    }
  }
}
