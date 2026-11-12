import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart' as fc;
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../services/phone_actions_service.dart';
import '../widgets/common_widgets.dart';

class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen>
    with SingleTickerProviderStateMixin {
  final _repo = NebulaRepository.instance;
  final _phoneService = PhoneActionsService.instance;

  late TabController _tabController;
  final TextEditingController _searchCtrl = TextEditingController();

  List<ContactModel> _robotContacts = [];
  List<fc.Contact> _deviceContacts = [];

  bool _loadingRobot = true;
  bool _loadingDevice = false;
  bool _syncing = false;
  bool _hasPermission = false;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(() {
      if (_tabController.index == 1 && _deviceContacts.isEmpty) {
        _checkAndLoadDeviceContacts();
      }
    });
    _searchCtrl.addListener(() {
      setState(() => _searchQuery = _searchCtrl.text.trim().toLowerCase());
    });
    _loadRobotContacts();
    _checkPermissionStatus();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _checkPermissionStatus() async {
    final granted = await _phoneService.hasContactsPermission();
    if (mounted) setState(() => _hasPermission = granted);
  }

  Future<void> _loadRobotContacts() async {
    setState(() => _loadingRobot = true);
    try {
      final list = await _repo.getContacts();
      if (mounted) {
        setState(() {
          _robotContacts = list;
          _loadingRobot = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loadingRobot = false);
        showErrorSnackbar(context, 'معرفناش نجيب جهات الاتصال من السيرفر: $e');
      }
    }
  }

  Future<void> _checkAndLoadDeviceContacts() async {
    setState(() => _loadingDevice = true);
    try {
      final granted = await _phoneService.requestContactsPermission();
      setState(() => _hasPermission = granted);

      if (granted) {
        final list = await _phoneService.fetchDeviceContacts();
        if (mounted) {
          setState(() {
            _deviceContacts = list;
            _loadingDevice = false;
          });
        }
      } else {
        if (mounted) {
          setState(() => _loadingDevice = false);
          showErrorSnackbar(
            context,
            'لازم توافق على صلاحية الوصول لجهات الاتصال في الموبايل',
          );
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loadingDevice = false);
        showErrorSnackbar(context, 'حصل خطأ أثناء قراءة جهات الاتصال: $e');
      }
    }
  }

  Future<void> _syncAllFromDevice() async {
    setState(() => _syncing = true);
    try {
      final granted = await _phoneService.requestContactsPermission();
      if (!granted) {
        if (mounted) {
          showErrorSnackbar(context, 'صلاحية جهات الاتصال غير مفعلة');
          setState(() => _syncing = false);
        }
        return;
      }

      final synced = await _phoneService.syncDeviceContactsToBackend(
        replaceExisting: false,
      );
      await _loadRobotContacts();

      if (mounted) {
        setState(() => _syncing = false);
        showSuccessSnackbar(
          context,
          'اتزامنت ${synced.length} جهة اتصال مع نيبولا بنجاح ✨',
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _syncing = false);
        showErrorSnackbar(context, 'فشلت المزامنة: $e');
      }
    }
  }

  Future<void> _toggleAllowlist(ContactModel contact, bool val) async {
    try {
      final updated = await _repo.updateContact(contact.id, {
        'is_allowlisted': val,
      });
      setState(() {
        final idx = _robotContacts.indexWhere((c) => c.id == contact.id);
        if (idx != -1) _robotContacts[idx] = updated;
      });
      if (mounted) {
        showSuccessSnackbar(
          context,
          val
              ? 'مسموح لنيبولا الاتصال بـ ${contact.name}'
              : 'تم تعطيل الاتصال بـ ${contact.name}',
        );
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل تحديث الحالة: $e');
    }
  }

  Future<void> _deleteContact(ContactModel contact) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.cardBorder),
        ),
        title: const Text(
          'حذف جهة الاتصال',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        content: Text(
          'متأكد إنك عاوز تحذف "${contact.name}" من قائمة نيبولا؟ الروبوت مش هيقدر يكلمه.',
          style: const TextStyle(
            fontFamily: 'Cairo',
            color: AppColors.textSecondary,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text(
              'إلغاء',
              style: TextStyle(fontFamily: 'Cairo', color: AppColors.textMuted),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text(
              'احذف',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    try {
      await _repo.deleteContact(contact.id);
      setState(() {
        _robotContacts.removeWhere((c) => c.id == contact.id);
      });
      if (mounted) {
        showSuccessSnackbar(context, 'اتحذفت جهة الاتصال بنجاح');
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'معرفناش نحذف: $e');
    }
  }

  void _showAddEditModal([ContactModel? existing]) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _ContactEditSheet(
        contact: existing,
        onSaved: (saved) {
          setState(() {
            final idx = _robotContacts.indexWhere((c) => c.id == saved.id);
            if (idx != -1) {
              _robotContacts[idx] = saved;
            } else {
              _robotContacts.insert(0, saved);
            }
          });
        },
      ),
    );
  }

  void _addDeviceContactToRobot(fc.Contact deviceContact) async {
    final name = deviceContact.displayName.trim();
    final phone = deviceContact.phones.isNotEmpty
        ? deviceContact.phones.first.number.trim()
        : '';

    if (name.isEmpty || phone.isEmpty) {
      showErrorSnackbar(context, 'جهة الاتصال لا تحتوي على رقم هاتف صالح');
      return;
    }

    try {
      final created = await _repo.createContact({
        'name': name,
        'phone_number': phone,
        'aliases': '',
        'relationship': null,
        'is_allowlisted': true,
        'requires_confirmation': true,
        'required_level': 1,
        'notify_on_missed': false,
      });
      setState(() {
        _robotContacts.insert(0, created);
      });
      if (mounted) {
        showSuccessSnackbar(context, 'اتضافت $name لقائمة نيبولا بنجاح! 📞');
      }
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الإضافة: $e');
    }
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
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(
                        Icons.arrow_forward_ios_rounded,
                        color: AppColors.textPrimary,
                        size: 20,
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'جهات الاتصال والتليفون',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          Text(
                            'تحكم في الأرقام اللي يقدر نيبولا يكلمها بصوتك',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              color: AppColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: _syncing
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppColors.teal,
                              ),
                            )
                          : const Icon(Icons.sync, color: AppColors.teal),
                      tooltip: 'مزامنة من الموبايل',
                      onPressed: _syncing ? null : _syncAllFromDevice,
                    ),
                  ],
                ),
              ),

              // Search bar
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 6,
                ),
                child: TextField(
                  controller: _searchCtrl,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontFamily: 'Cairo',
                  ),
                  decoration: InputDecoration(
                    hintText: 'ابحث بالاسم أو الرقم أو صلة القرابة...',
                    hintStyle: const TextStyle(
                      color: AppColors.textMuted,
                      fontFamily: 'Cairo',
                      fontSize: 13,
                    ),
                    prefixIcon: const Icon(
                      Icons.search,
                      color: AppColors.teal,
                      size: 20,
                    ),
                    suffixIcon: _searchQuery.isNotEmpty
                        ? IconButton(
                            icon: const Icon(
                              Icons.clear,
                              color: AppColors.textMuted,
                              size: 18,
                            ),
                            onPressed: () => _searchCtrl.clear(),
                          )
                        : null,
                    filled: true,
                    fillColor: AppColors.card,
                    contentPadding: const EdgeInsets.symmetric(
                      vertical: 10,
                      horizontal: 14,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: AppColors.cardBorder),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: AppColors.cardBorder),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(
                        color: AppColors.teal,
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
              ),

              // Tabs
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.cardBorder),
                ),
                child: TabBar(
                  controller: _tabController,
                  indicator: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    color: AppColors.teal.withValues(alpha: 0.15),
                    border: Border.all(
                      color: AppColors.teal.withValues(alpha: 0.5),
                    ),
                  ),
                  labelColor: AppColors.teal,
                  unselectedLabelColor: AppColors.textMuted,
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                  tabs: [
                    Tab(
                      text:
                          'جهات الروبوت (${_robotContacts.where((c) => c.isAllowlisted).length})',
                    ),
                    const Tab(text: 'دليل الهاتف بالموبايل'),
                  ],
                ),
              ),

              // Tab Views
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildRobotContactsTab(),
                    _buildDeviceContactsTab(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: AppColors.teal,
        foregroundColor: Colors.black,
        elevation: 4,
        icon: const Icon(Icons.person_add_alt_1),
        label: const Text(
          'جهة جديدة',
          style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.w700),
        ),
        onPressed: () => _showAddEditModal(),
      ),
    );
  }

  Widget _buildRobotContactsTab() {
    if (_loadingRobot) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.teal),
      );
    }

    final filtered = _robotContacts.where((c) {
      if (_searchQuery.isEmpty) return true;
      return c.name.toLowerCase().contains(_searchQuery) ||
          c.phoneNumber.contains(_searchQuery) ||
          c.aliases.toLowerCase().contains(_searchQuery) ||
          (c.relationship ?? '').toLowerCase().contains(_searchQuery);
    }).toList();

    if (filtered.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.contact_phone_outlined,
                size: 64,
                color: AppColors.teal.withValues(alpha: 0.4),
              ),
              const SizedBox(height: 16),
              const Text(
                'مفيش جهات اتصال مسجلة في نيبولا',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'اضغط على زرار المزامنة فوق عشان تسحب أرقامك من الموبايل أو ضيف جهة يدوياً.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  color: AppColors.textMuted,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.teal,
                  foregroundColor: Colors.black,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: _syncAllFromDevice,
                icon: const Icon(Icons.sync),
                label: const Text(
                  'مزامنة الأرقام من الموبايل دلوقتي',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      color: AppColors.teal,
      backgroundColor: AppColors.surface,
      onRefresh: _loadRobotContacts,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
        itemCount: filtered.length,
        separatorBuilder: (_, index) => const SizedBox(height: 12),
        itemBuilder: (context, index) {
          final c = filtered[index];
          return _RobotContactCard(
            contact: c,
            onToggleAllowlist: (val) => _toggleAllowlist(c, val),
            onEdit: () => _showAddEditModal(c),
            onDelete: () => _deleteContact(c),
            onCall: () => _phoneService.makePhoneCall(c.phoneNumber),
            onSms: () => _phoneService.sendSms(c.phoneNumber),
          );
        },
      ),
    );
  }

  Widget _buildDeviceContactsTab() {
    if (!_hasPermission) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.security, size: 64, color: AppColors.warning),
              const SizedBox(height: 16),
              const Text(
                'يلزم تفعيل صلاحية جهات الاتصال',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'نيبولا محتاج إذن الوصول لدليل الهاتف عشان يقرأ الأرقام ويسمح للروبوت يكلم أصحابك وعيلتك بأمر صوتي.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  color: AppColors.textMuted,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.teal,
                  foregroundColor: Colors.black,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: _checkAndLoadDeviceContacts,
                icon: const Icon(Icons.check_circle_outline),
                label: const Text(
                  'تفعيل الصلاحية وقراءة الأسماء',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (_loadingDevice) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.teal),
      );
    }

    final filtered = _deviceContacts.where((c) {
      if (_searchQuery.isEmpty) return true;
      final name = c.displayName.toLowerCase();
      final hasMatchingPhone = c.phones.any(
        (p) => p.number.contains(_searchQuery),
      );
      return name.contains(_searchQuery) || hasMatchingPhone;
    }).toList();

    if (filtered.isEmpty) {
      return const Center(
        child: Text(
          'مفيش جهات اتصال مطابقة في الهاتف',
          style: TextStyle(fontFamily: 'Cairo', color: AppColors.textMuted),
        ),
      );
    }

    return Column(
      children: [
        // Action banner
        Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.teal.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: AppColors.teal.withValues(alpha: 0.3)),
          ),
          child: Row(
            children: [
              const Icon(Icons.phone_iphone, color: AppColors.teal, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'تم العثور على ${filtered.length} جهة اتصال في الموبايل',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.teal,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                onPressed: _syncing ? null : _syncAllFromDevice,
                child: Text(
                  _syncing ? 'جاري...' : 'مزامنة الكل',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 80),
            itemCount: filtered.length,
            separatorBuilder: (_, index) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final dc = filtered[index];
              final phone = dc.phones.isNotEmpty
                  ? dc.phones.first.number
                  : 'بدون رقم';
              final alreadyInRobot = _robotContacts.any((rc) {
                final c1 = _phoneService.cleanPhoneNumber(rc.phoneNumber);
                final c2 = _phoneService.cleanPhoneNumber(phone);
                return c1.isNotEmpty &&
                    c2.isNotEmpty &&
                    (c1 == c2 || c1.endsWith(c2) || c2.endsWith(c1));
              });

              return NebulaCard(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 20,
                      backgroundColor: alreadyInRobot
                          ? AppColors.teal.withValues(alpha: 0.2)
                          : AppColors.surface,
                      child: Text(
                        dc.displayName.isNotEmpty
                            ? dc.displayName.characters.first
                            : '?',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.w700,
                          color: alreadyInRobot
                              ? AppColors.teal
                              : AppColors.textPrimary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            dc.displayName,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          Text(
                            phone,
                            textDirection: TextDirection.ltr,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              color: AppColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (alreadyInRobot)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.success.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: AppColors.success.withValues(alpha: 0.4),
                          ),
                        ),
                        child: const Text(
                          'مضاف للروبوت ✓',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: AppColors.success,
                          ),
                        ),
                      )
                    else
                      IconButton(
                        icon: const Icon(
                          Icons.add_circle_outline,
                          color: AppColors.teal,
                        ),
                        tooltip: 'إضافة لقائمة الروبوت',
                        onPressed: () => _addDeviceContactToRobot(dc),
                      ),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

// ── Robot Contact Card ────────────────────────────────────────────────────────

class _RobotContactCard extends StatelessWidget {
  final ContactModel contact;
  final ValueChanged<bool> onToggleAllowlist;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onCall;
  final VoidCallback onSms;

  const _RobotContactCard({
    required this.contact,
    required this.onToggleAllowlist,
    required this.onEdit,
    required this.onDelete,
    required this.onCall,
    required this.onSms,
  });

  @override
  Widget build(BuildContext context) {
    return NebulaCard(
      padding: const EdgeInsets.all(14),
      borderColor: contact.isAllowlisted
          ? AppColors.teal.withValues(alpha: 0.4)
          : AppColors.cardBorder,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: contact.isAllowlisted
                    ? AppColors.teal.withValues(alpha: 0.2)
                    : AppColors.textMuted.withValues(alpha: 0.1),
                child: Text(
                  contact.name.isNotEmpty ? contact.name.characters.first : '?',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: contact.isAllowlisted
                        ? AppColors.teal
                        : AppColors.textMuted,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            contact.name,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ),
                        if (contact.relationship != null &&
                            contact.relationship!.isNotEmpty) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.purple.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              contact.relationship!,
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: AppColors.purple,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      contact.phoneNumber,
                      textDirection: TextDirection.ltr,
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),

              // Allow switch
              Switch(
                value: contact.isAllowlisted,
                activeThumbColor: AppColors.teal,
                onChanged: onToggleAllowlist,
              ),
            ],
          ),

          // Aliases display
          if (contact.aliases.isNotEmpty) ...[
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.record_voice_over_outlined,
                  size: 14,
                  color: AppColors.textMuted,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'الأسماء الصوتية: ${contact.aliases}',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      color: AppColors.textMuted,
                    ),
                  ),
                ),
              ],
            ),
          ],

          const Divider(color: AppColors.cardBorder, height: 20),

          // Action row
          Row(
            children: [
              // Security level pill
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.cardBorder),
                ),
                child: Text(
                  contact.requiredLevel == 2
                      ? 'مستوى 2: بصمة صوت 🔒'
                      : 'مستوى 1: تأكيد بسيط 🛡️',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textMuted,
                  ),
                ),
              ),
              const Spacer(),

              // Direct dial button
              IconButton(
                icon: const Icon(Icons.phone, color: AppColors.teal, size: 20),
                tooltip: 'اتصال مباشر من الموبايل',
                onPressed: onCall,
              ),
              // Direct SMS button
              IconButton(
                icon: const Icon(
                  Icons.message_outlined,
                  color: AppColors.purple,
                  size: 20,
                ),
                tooltip: 'رسالة نصية',
                onPressed: onSms,
              ),
              // Edit button
              IconButton(
                icon: const Icon(
                  Icons.edit_outlined,
                  color: AppColors.textSecondary,
                  size: 20,
                ),
                tooltip: 'تعديل البيانات',
                onPressed: onEdit,
              ),
              // Delete button
              IconButton(
                icon: const Icon(
                  Icons.delete_outline,
                  color: AppColors.error,
                  size: 20,
                ),
                tooltip: 'حذف',
                onPressed: onDelete,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── Contact Add/Edit Bottom Sheet ─────────────────────────────────────────────

class _ContactEditSheet extends StatefulWidget {
  final ContactModel? contact;
  final ValueChanged<ContactModel> onSaved;

  const _ContactEditSheet({this.contact, required this.onSaved});

  @override
  State<_ContactEditSheet> createState() => _ContactEditSheetState();
}

class _ContactEditSheetState extends State<_ContactEditSheet> {
  final _repo = NebulaRepository.instance;
  final _formKey = GlobalKey<FormState>();

  late TextEditingController _nameCtrl;
  late TextEditingController _phoneCtrl;
  late TextEditingController _aliasesCtrl;
  String? _relationship;
  bool _isAllowlisted = true;
  bool _requiresConfirmation = true;
  int _requiredLevel = 1;
  bool _notifyOnMissed = false;
  bool _saving = false;

  final _relationships = [
    'ماما',
    'بابا',
    'أخ',
    'أخت',
    'ابن / ابنة',
    'صديق',
    'عمل',
    'طوارئ',
  ];

  @override
  void initState() {
    super.initState();
    final c = widget.contact;
    _nameCtrl = TextEditingController(text: c?.name ?? '');
    _phoneCtrl = TextEditingController(text: c?.phoneNumber ?? '');
    _aliasesCtrl = TextEditingController(text: c?.aliases ?? '');
    _relationship = c?.relationship;
    _isAllowlisted = c?.isAllowlisted ?? true;
    _requiresConfirmation = c?.requiresConfirmation ?? true;
    _requiredLevel = c?.requiredLevel ?? 1;
    _notifyOnMissed = c?.notifyOnMissed ?? false;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _phoneCtrl.dispose();
    _aliasesCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    try {
      final payload = {
        'name': _nameCtrl.text.trim(),
        'phone_number': _phoneCtrl.text.trim(),
        'aliases': _aliasesCtrl.text.trim(),
        'relationship': _relationship,
        'is_allowlisted': _isAllowlisted,
        'requires_confirmation': _requiresConfirmation,
        'required_level': _requiredLevel,
        'notify_on_missed': _notifyOnMissed,
      };

      ContactModel result;
      if (widget.contact != null) {
        result = await _repo.updateContact(widget.contact!.id, payload);
      } else {
        result = await _repo.createContact(payload);
      }

      widget.onSaved(result);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showErrorSnackbar(context, 'فشل حفظ جهة الاتصال: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.only(
        top: 20,
        left: 20,
        right: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.cardBorder,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                widget.contact != null
                    ? 'تعديل جهة الاتصال'
                    : 'إضافة جهة اتصال لنيبولا',
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 16),

              // Name
              TextFormField(
                controller: _nameCtrl,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontFamily: 'Cairo',
                ),
                decoration: const InputDecoration(
                  labelText: 'اسم جهة الاتصال *',
                  prefixIcon: Icon(Icons.person_outline),
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'لازم تكتب الاسم' : null,
              ),
              const SizedBox(height: 12),

              // Phone
              TextFormField(
                controller: _phoneCtrl,
                keyboardType: TextInputType.phone,
                textDirection: TextDirection.ltr,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontFamily: 'Cairo',
                ),
                decoration: const InputDecoration(
                  labelText: 'رقم الهاتف * (مثال: +201012345678 أو 010...)',
                  prefixIcon: Icon(Icons.phone_outlined),
                ),
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'لازم تكتب الرقم';
                  if (v.trim().length < 7) return 'الرقم قصير جداً';
                  return null;
                },
              ),
              const SizedBox(height: 12),

              // Relationship Dropdown
              DropdownButtonFormField<String>(
                initialValue: _relationship,
                dropdownColor: AppColors.card,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontFamily: 'Cairo',
                ),
                decoration: const InputDecoration(
                  labelText: 'صلة القرابة / العلاقة',
                  prefixIcon: Icon(Icons.family_restroom_outlined),
                ),
                items: _relationships
                    .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                    .toList(),
                onChanged: (v) => setState(() => _relationship = v),
              ),
              const SizedBox(height: 12),

              // Aliases
              TextFormField(
                controller: _aliasesCtrl,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontFamily: 'Cairo',
                ),
                decoration: const InputDecoration(
                  labelText: 'الأسماء البديلة في الصوت (مفصولة بفاصلة)',
                  hintText: 'مثال: مامي, أمي, الوالدة',
                  prefixIcon: Icon(Icons.record_voice_over_outlined),
                ),
              ),
              const SizedBox(height: 16),

              // Switches
              SwitchListTile(
                title: const Text(
                  'السماح لنيبولا بالاتصال بهذه الجهة',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    color: AppColors.textPrimary,
                  ),
                ),
                value: _isAllowlisted,
                activeThumbColor: AppColors.teal,
                onChanged: (v) => setState(() => _isAllowlisted = v),
                contentPadding: EdgeInsets.zero,
              ),
              SwitchListTile(
                title: const Text(
                  'طلب تأكيد صوتي قبل إجراء المكالمة',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    color: AppColors.textPrimary,
                  ),
                ),
                value: _requiresConfirmation,
                activeThumbColor: AppColors.teal,
                onChanged: (v) => setState(() => _requiresConfirmation = v),
                contentPadding: EdgeInsets.zero,
              ),
              SwitchListTile(
                title: const Text(
                  'إبلاغ هذه الجهة إذا نسيت جرعة الدواء',
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 13,
                    color: AppColors.textPrimary,
                  ),
                ),
                value: _notifyOnMissed,
                activeThumbColor: AppColors.teal,
                onChanged: (v) => setState(() => _notifyOnMissed = v),
                contentPadding: EdgeInsets.zero,
              ),
              const SizedBox(height: 20),

              NebulaPrimaryButton(
                label: widget.contact != null
                    ? 'حفظ التعديلات'
                    : 'إضافة للروبوت',
                icon: Icons.check,
                loading: _saving,
                onTap: _save,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
