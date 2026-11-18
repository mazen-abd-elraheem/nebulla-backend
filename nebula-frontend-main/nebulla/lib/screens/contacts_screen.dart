import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart' as fc;
import '../models/models.dart';
import '../services/locale_service.dart';
import '../services/nebula_repository.dart';
import '../services/phone_actions_service.dart';
import '../widgets/common_widgets.dart';
import '../widgets/nebula_side_menu.dart';

class ContactsScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;
  const ContactsScreen({super.key, this.onNavigate});

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
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر تحميل جهات الاتصال من الخادم حالياً.',
            'Could not load contacts from server right now.',
          ),
        );
      }
    }
  }

  Future<void> _checkAndLoadDeviceContacts() async {
    if (!_phoneService.supportsDeviceContacts) {
      if (mounted) {
        setState(() {
          _hasPermission = false;
          _loadingDevice = false;
        });
      }
      return;
    }
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
            LocaleService.instance.tr(
              'يجب منح صلاحية الوصول لجهات الاتصال في الهاتف',
              'Contacts permission is required to read your phone book.',
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loadingDevice = false);
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر قراءة جهات الاتصال من الهاتف حالياً.',
            'Could not read device contacts right now.',
          ),
        );
      }
    }
  }

  Future<void> _syncAllFromDevice() async {
    if (!_phoneService.supportsDeviceContacts) {
      if (mounted) {
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'مزامنة دليل الموبايل متاحة على الهاتف فقط، يمكنك إضافة الأرقام من زر «جهة جديدة».',
            'Phone book sync is available on mobile only. Use "New Contact" to add numbers manually.',
          ),
        );
      }
      return;
    }
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
          'تمت مزامنة ${synced.length} جهة اتصال مع نيبولا بنجاح ✨',
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _syncing = false);
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر إتمام مزامنة جهات الاتصال حالياً.',
            'Could not complete contacts sync right now.',
          ),
        );
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
      if (mounted) {
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر تحديث إذن الاتصال بجهة الاتصال.',
            'Could not update contact call permission.',
          ),
        );
      }
    }
  }

  Future<void> _deleteContact(ContactModel contact) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text(
          'حذف جهة الاتصال',
          style: TextStyle(
            fontFamily: 'Cairo',
            fontWeight: FontWeight.w800,
            fontSize: 16,
            color: Color(0xFF0F172A),
          ),
        ),
        content: Text(
          'هل أنت متأكد من حذف "${contact.name}" من قائمة نيبولا؟ لن يتمكن المساعد من الاتصال بهذه الجهة.',
          style: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 13,
            color: Color(0xFF475569),
            height: 1.5,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text(
              'إلغاء',
              style: TextStyle(
                fontFamily: 'Cairo',
                color: Color(0xFF64748B),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFEF4444),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
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
    );

    if (confirm != true) return;

    try {
      await _repo.deleteContact(contact.id);
      setState(() {
        _robotContacts.removeWhere((c) => c.id == contact.id);
      });
      if (mounted) {
        showSuccessSnackbar(context, 'تم حذف جهة الاتصال بنجاح');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر حذف جهة الاتصال، حاول مرة أخرى.',
            'Could not delete contact. Please try again.',
          ),
        );
      }
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
        showSuccessSnackbar(context, 'تمت إضافة $name لقائمة نيبولا بنجاح! 📞');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر إضافة جهة الاتصال الجديدة حالياً.',
            'Could not add new contact right now.',
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = LocaleService.instance.isArabic;
    final t = LocaleService.instance.tr;

    // Header buttons
    final menuBtn = GestureDetector(
      onTap: () {
        NebulaSideMenu.show(
          context,
          activeIndex: 7,
          onNavigate: (idx) {
            if (widget.onNavigate != null && idx >= 0) {
              widget.onNavigate!(idx);
            }
          },
        );
      },
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: 42,
        height: 42,
        decoration: BoxDecoration(
          color: Colors.transparent,
          shape: BoxShape.circle,
          border: Border.all(color: const Color(0xFFCBD5E1), width: 1.4),
        ),
        child: const Icon(
          Icons.menu_rounded,
          color: Color(0xFF0F172A),
          size: 22,
        ),
      ),
    );

    final titleWidget = Expanded(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            t('جهات الاتصال والتليفون', 'Contacts & Phone'),
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 16.5,
              fontWeight: FontWeight.w900,
              color: Color(0xFF0F172A),
            ),
          ),
          const SizedBox(height: 1),
          Text(
            t(
              'تحكم في الأرقام التي يتواصل معها نيبولا بصوتك',
              'Manage contacts Nebula can call by voice',
            ),
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 11,
              color: Color(0xFF64748B),
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );

    final actionsSection = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Sync Button
        GestureDetector(
          onTap: _syncing ? null : _syncAllFromDevice,
          behavior: HitTestBehavior.opaque,
          child: Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: Colors.transparent,
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFCBD5E1), width: 1.4),
            ),
            child: _syncing
                ? const Center(
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFF00B4D8),
                      ),
                    ),
                  )
                : const Icon(
                    Icons.sync_rounded,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
          ),
        ),
        const SizedBox(width: 8),
        // Back / Exit Button
        GestureDetector(
          onTap: () {
            if (Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            } else {
              widget.onNavigate?.call(2);
            }
          },
          behavior: HitTestBehavior.opaque,
          child: Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: Colors.transparent,
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFCBD5E1), width: 1.4),
            ),
            child: Icon(
              isArabic ? Icons.arrow_forward_rounded : Icons.arrow_back_rounded,
              color: const Color(0xFF0F172A),
              size: 20,
            ),
          ),
        ),
      ],
    );

    final leftSide = isArabic ? menuBtn : actionsSection;
    final rightSide = isArabic ? actionsSection : menuBtn;

    return Directionality(
      textDirection: LocaleService.instance.textDirection,
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        body: SafeArea(
          child: Column(
            children: [
              // 1. Top Header Row (Menu on Left, Title Centered, Actions on Right)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: Directionality(
                  textDirection: TextDirection.ltr,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [leftSide, titleWidget, rightSide],
                  ),
                ),
              ),

              // 2. Search Bar
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFCBD5E1)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.03),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(15),
                  child: TextField(
                    controller: _searchCtrl,
                    cursorColor: const Color(0xFF00B4D8),
                    style: const TextStyle(
                      color: Color(0xFF0F172A),
                      fontFamily: 'Cairo',
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                    ),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.white,
                      hintText: t(
                        'ابحث بالاسم أو الرقم أو صلة القرابة...',
                        'Search by name, phone, or relation...',
                      ),
                      hintStyle: const TextStyle(
                        color: Color(0xFF64748B),
                        fontFamily: 'Cairo',
                        fontSize: 12.5,
                      ),
                      prefixIcon: const Icon(
                        Icons.search_rounded,
                        color: Color(0xFF00B4D8),
                        size: 20,
                      ),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(
                                Icons.clear_rounded,
                                color: Color(0xFF64748B),
                                size: 18,
                              ),
                              onPressed: () => _searchCtrl.clear(),
                            )
                          : null,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(
                        vertical: 12,
                        horizontal: 14,
                      ),
                    ),
                  ),
                ),
              ),

              // 3. Segmented Control Tabs
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: TabBar(
                  controller: _tabController,
                  indicator: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.05),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  indicatorSize: TabBarIndicatorSize.tab,
                  dividerColor: Colors.transparent,
                  labelColor: const Color(0xFF0F172A),
                  unselectedLabelColor: const Color(0xFF64748B),
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w800,
                    fontSize: 13,
                  ),
                  unselectedLabelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                  tabs: [
                    Tab(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.smart_toy_rounded,
                            size: 16,
                            color: Color(0xFF00B4D8),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            t(
                              'جهات نيبولا (${_robotContacts.where((c) => c.isAllowlisted).length})',
                              'Nebula (${_robotContacts.where((c) => c.isAllowlisted).length})',
                            ),
                          ),
                        ],
                      ),
                    ),
                    Tab(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.phone_iphone_rounded,
                            size: 16,
                            color: Color(0xFF64748B),
                          ),
                          const SizedBox(width: 6),
                          Text(t('دليل الموبايل', 'Phone Book')),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              // 4. Tab Views
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
        floatingActionButton: Padding(
          padding: const EdgeInsets.only(bottom: 92),
          child: FloatingActionButton.extended(
            backgroundColor: const Color(0xFF00B4D8),
            foregroundColor: Colors.white,
            elevation: 4,
            icon: const Icon(Icons.person_add_rounded, size: 20),
            label: Text(
              t('جهة جديدة', 'New Contact'),
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.w800,
                fontSize: 13.5,
              ),
            ),
            onPressed: () => _showAddEditModal(),
          ),
        ),
      ),
    );
  }

  Widget _buildRobotContactsTab() {
    if (_loadingRobot) {
      return const Center(
        child: CircularProgressIndicator(color: Color(0xFF00B4D8)),
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
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F2FE),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFBAE6FD)),
                ),
                child: const Icon(
                  Icons.contact_phone_rounded,
                  size: 36,
                  color: Color(0xFF0284C7),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'لا توجد جهات اتصال مسجلة في نيبولا',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'اضغط على زر المزامنة بالأعلى لسحب أرقامك من الموبايل أو أضف جهة يدوياً.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  color: Color(0xFF64748B),
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 22,
                    vertical: 12,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                onPressed: _syncAllFromDevice,
                icon: const Icon(Icons.sync_rounded, size: 18),
                label: const Text(
                  'مزامنة الأرقام من الموبايل الآن',
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
    }

    return RefreshIndicator(
      color: const Color(0xFF00B4D8),
      backgroundColor: Colors.white,
      onRefresh: _loadRobotContacts,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 170),
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
    final t = LocaleService.instance.tr;
    if (!_phoneService.supportsDeviceContacts) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 140),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: const Color(0xFFE0F2FE),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFBAE6FD)),
                ),
                child: const Icon(
                  Icons.phone_iphone_rounded,
                  size: 36,
                  color: Color(0xFF0284C7),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                t('دليل الموبايل متاح على الهاتف فقط', 'Phone Book Available on Mobile'),
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                t(
                  'أنت تستخدم التطبيق على الكمبيوتر حالياً. يمكنك إضافة وتنظيم كل جهات الاتصال بسهولة من الزر بالأسفل.',
                  'You are currently on desktop. You can add and organize all your contacts easily using the button below.',
                ),
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  color: Color(0xFF64748B),
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 22,
                    vertical: 12,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                onPressed: () => _showAddEditModal(),
                icon: const Icon(Icons.person_add_rounded, size: 18),
                label: Text(
                  t('إضافة جهة اتصال يدوياً', 'Add Contact Manually'),
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (!_hasPermission) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: const Color(0xFFFEF3C7),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFFDE68A)),
                ),
                child: const Icon(
                  Icons.security_rounded,
                  size: 36,
                  color: Color(0xFFD97706),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'يلزم تفعيل صلاحية جهات الاتصال',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'نيبولا يحتاج إذن الوصول لدليل الهاتف حتى يتمكن المساعد من قراءة الأرقام والتواصل مع أصحابك وعائلتك بأمر صوتي.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 13,
                  color: Color(0xFF64748B),
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 22,
                    vertical: 12,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                onPressed: _checkAndLoadDeviceContacts,
                icon: const Icon(Icons.check_circle_outline_rounded, size: 18),
                label: const Text(
                  'تفعيل الصلاحية وقراءة الأسماء',
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
    }

    if (_loadingDevice) {
      return const Center(
        child: CircularProgressIndicator(color: Color(0xFF00B4D8)),
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
          'لا توجد جهات اتصال مطابقة في الهاتف',
          style: TextStyle(
            fontFamily: 'Cairo',
            color: Color(0xFF64748B),
            fontSize: 14,
          ),
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
            color: const Color(0xFFE0F2FE),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFBAE6FD)),
          ),
          child: Row(
            children: [
              const Icon(
                Icons.phone_iphone_rounded,
                color: Color(0xFF0284C7),
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'تم العثور على ${filtered.length} جهة اتصال في الموبايل',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0369A1),
                  ),
                ),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                onPressed: _syncing ? null : _syncAllFromDevice,
                child: Text(
                  _syncing ? 'جاري...' : 'مزامنة الكل',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),

        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 170),
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

              return Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.02),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: alreadyInRobot
                            ? const Color(0xFFDCFCE7)
                            : const Color(0xFFF1F5F9),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: alreadyInRobot
                              ? const Color(0xFF86EFAC)
                              : const Color(0xFFE2E8F0),
                        ),
                      ),
                      child: Center(
                        child: Text(
                          dc.displayName.isNotEmpty
                              ? dc.displayName.characters.first
                              : '?',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontWeight: FontWeight.w800,
                            fontSize: 15,
                            color: alreadyInRobot
                                ? const Color(0xFF16A34A)
                                : const Color(0xFF0F172A),
                          ),
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
                              fontWeight: FontWeight.w800,
                              fontSize: 14,
                              color: Color(0xFF0F172A),
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            phone,
                            textDirection: TextDirection.ltr,
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 12,
                              color: Color(0xFF64748B),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (alreadyInRobot)
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
                              'مضاف ✓',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF16A34A),
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      InkWell(
                        onTap: () => _addDeviceContactToRobot(dc),
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: const Color(0xFFE0F2FE),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: const Color(0xFFBAE6FD)),
                          ),
                          child: const Icon(
                            Icons.add_rounded,
                            color: Color(0xFF0284C7),
                            size: 20,
                          ),
                        ),
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

  Widget _buildActionIconButton({
    required IconData icon,
    required Color color,
    required Color bgColor,
    required String tooltip,
    required VoidCallback onTap,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: color, size: 17),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: contact.isAllowlisted
              ? const Color(0xFFBAE6FD)
              : const Color(0xFFE2E8F0),
          width: contact.isAllowlisted ? 1.5 : 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: contact.isAllowlisted
                ? const Color(0xFF00B4D8).withValues(alpha: 0.06)
                : Colors.black.withValues(alpha: 0.02),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: contact.isAllowlisted
                      ? const Color(0xFFE0F2FE)
                      : const Color(0xFFF1F5F9),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: contact.isAllowlisted
                        ? const Color(0xFFBAE6FD)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
                child: Center(
                  child: Text(
                    contact.name.isNotEmpty
                        ? contact.name.characters.first
                        : '?',
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: contact.isAllowlisted
                          ? const Color(0xFF0284C7)
                          : const Color(0xFF64748B),
                    ),
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
                              color: Color(0xFF0F172A),
                            ),
                          ),
                        ),
                        if (contact.relationship != null &&
                            contact.relationship!.isNotEmpty) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF3E8FF),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: const Color(0xFFE9D5FF),
                              ),
                            ),
                            child: Text(
                              contact.relationship!,
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF9333EA),
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
                        fontSize: 12.5,
                        color: Color(0xFF64748B),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),

              // Allow switch
              Switch(
                value: contact.isAllowlisted,
                activeThumbColor: const Color(0xFF00B4D8),
                activeTrackColor: const Color(0xFFBAE6FD),
                onChanged: onToggleAllowlist,
              ),
            ],
          ),

          // Aliases display
          if (contact.aliases.isNotEmpty) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.record_voice_over_rounded,
                    size: 15,
                    color: Color(0xFF0284C7),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'الأسماء الصوتية: ${contact.aliases}',
                      style: const TextStyle(
                        fontFamily: 'Cairo',
                        fontSize: 11.5,
                        color: Color(0xFF475569),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          const Padding(
            padding: EdgeInsets.symmetric(vertical: 10),
            child: Divider(color: Color(0xFFF1F5F9), height: 1),
          ),

          // Action row
          Row(
            children: [
              // Security level pill
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Text(
                  contact.requiredLevel == 2
                      ? 'مستوى 2: بصمة صوت 🔒'
                      : 'مستوى 1: تأكيد بسيط 🛡️',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
              const Spacer(),

              // Direct dial button
              _buildActionIconButton(
                icon: Icons.phone_rounded,
                color: const Color(0xFF0284C7),
                bgColor: const Color(0xFFE0F2FE),
                tooltip: 'اتصال مباشر',
                onTap: onCall,
              ),
              const SizedBox(width: 6),
              // Direct SMS button
              _buildActionIconButton(
                icon: Icons.message_rounded,
                color: const Color(0xFF9333EA),
                bgColor: const Color(0xFFF3E8FF),
                tooltip: 'رسالة نصية',
                onTap: onSms,
              ),
              const SizedBox(width: 6),
              // Edit button
              _buildActionIconButton(
                icon: Icons.edit_rounded,
                color: const Color(0xFF475569),
                bgColor: const Color(0xFFF1F5F9),
                tooltip: 'تعديل البيانات',
                onTap: onEdit,
              ),
              const SizedBox(width: 6),
              // Delete button
              _buildActionIconButton(
                icon: Icons.delete_outline_rounded,
                color: const Color(0xFFDC2626),
                bgColor: const Color(0xFFFEE2E2),
                tooltip: 'حذف',
                onTap: onDelete,
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
        showErrorSnackbar(
          context,
          LocaleService.instance.tr(
            'تعذر حفظ بيانات جهة الاتصال حالياً.',
            'Could not save contact details right now.',
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: EdgeInsets.only(
        top: 16,
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
                  width: 44,
                  height: 4.5,
                  decoration: BoxDecoration(
                    color: const Color(0xFFCBD5E1),
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
              const SizedBox(height: 16),
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
                      Icons.person_pin_rounded,
                      color: Color(0xFF0284C7),
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    widget.contact != null
                        ? 'تعديل بيانات جهة الاتصال'
                        : 'إضافة جهة اتصال لنيبولا',
                    style: const TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 16.5,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF0F172A),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),

              // Name
              TextFormField(
                controller: _nameCtrl,
                style: const TextStyle(
                  color: Color(0xFF0F172A),
                  fontFamily: 'Cairo',
                  fontSize: 13.5,
                ),
                decoration: InputDecoration(
                  labelText: 'اسم جهة الاتصال *',
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                  prefixIcon: const Icon(
                    Icons.person_outline_rounded,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: Color(0xFF00B4D8),
                      width: 1.5,
                    ),
                  ),
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
                  color: Color(0xFF0F172A),
                  fontFamily: 'Cairo',
                  fontSize: 13.5,
                ),
                decoration: InputDecoration(
                  labelText: 'رقم الهاتف * (مثال: +201012345678 أو 010...)',
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                  prefixIcon: const Icon(
                    Icons.phone_outlined,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: Color(0xFF00B4D8),
                      width: 1.5,
                    ),
                  ),
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
                dropdownColor: Colors.white,
                style: const TextStyle(
                  color: Color(0xFF0F172A),
                  fontFamily: 'Cairo',
                  fontSize: 13.5,
                ),
                decoration: InputDecoration(
                  labelText: 'صلة القرابة / العلاقة',
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                  prefixIcon: const Icon(
                    Icons.family_restroom_rounded,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: Color(0xFF00B4D8),
                      width: 1.5,
                    ),
                  ),
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
                  color: Color(0xFF0F172A),
                  fontFamily: 'Cairo',
                  fontSize: 13.5,
                ),
                decoration: InputDecoration(
                  labelText: 'الأسماء البديلة في الصوت (مفصولة بفاصلة)',
                  hintText: 'مثال: مامي, أمي, الوالدة',
                  hintStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF94A3B8),
                    fontSize: 12,
                  ),
                  labelStyle: const TextStyle(
                    fontFamily: 'Cairo',
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                  prefixIcon: const Icon(
                    Icons.record_voice_over_rounded,
                    color: Color(0xFF00B4D8),
                    size: 20,
                  ),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: Color(0xFF00B4D8),
                      width: 1.5,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Switches
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Column(
                  children: [
                    SwitchListTile(
                      title: const Text(
                        'السماح لنيبولا بالاتصال بهذه الجهة',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      value: _isAllowlisted,
                      activeThumbColor: const Color(0xFF00B4D8),
                      onChanged: (v) => setState(() => _isAllowlisted = v),
                    ),
                    const Divider(height: 1, color: Color(0xFFE2E8F0)),
                    SwitchListTile(
                      title: const Text(
                        'طلب تأكيد صوتي قبل إجراء المكالمة',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      value: _requiresConfirmation,
                      activeThumbColor: const Color(0xFF00B4D8),
                      onChanged: (v) =>
                          setState(() => _requiresConfirmation = v),
                    ),
                    const Divider(height: 1, color: Color(0xFFE2E8F0)),
                    SwitchListTile(
                      title: const Text(
                        'إبلاغ هذه الجهة إذا نسيت جرعة الدواء',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      value: _notifyOnMissed,
                      activeThumbColor: const Color(0xFF00B4D8),
                      onChanged: (v) => setState(() => _notifyOnMissed = v),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00B4D8),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.check_rounded, size: 20),
                label: Text(
                  widget.contact != null ? 'حفظ التعديلات' : 'إضافة لنيبولا',
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
