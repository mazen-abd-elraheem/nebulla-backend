import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../services/nebula_repository.dart';
import '../services/storage_service.dart';
import '../widgets/common_widgets.dart';
import 'login_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _repo = NebulaRepository.instance;
  final _store = StorageService.instance;

  AppSettings? _settings;
  bool _loading = true;
  bool _saving = false;

  late TextEditingController _baseUrlCtrl;
  late TextEditingController _llmBaseUrlCtrl;

  String? _sttProvider;
  String? _ttsProvider;
  String? _llmProvider;
  String? _llmModel;

  final _sttProviders = ['qwencleo', 'whisper', 'nemotron'];
  final _ttsProviders = ['xtts', 'voicetut', 'ar_eg_free'];
  final _llmProviders = ['local', 'openai', 'anthropic'];

  @override
  void initState() {
    super.initState();
    _baseUrlCtrl = TextEditingController(text: _store.getBaseUrl());
    _llmBaseUrlCtrl = TextEditingController();
    _load();
  }

  @override
  void dispose() {
    _baseUrlCtrl.dispose();
    _llmBaseUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _settings = await _repo.getSettings();
      setState(() {
        _sttProvider = _settings?.sttProvider;
        _ttsProvider = _settings?.ttsProvider;
        _llmProvider = _settings?.llmProvider;
        _llmModel = _settings?.llmModel;
        _llmBaseUrlCtrl.text = _settings?.llmBaseUrl ?? '';
      });
    } catch (e) {
      // Settings might fail if not authenticated; just skip
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await _store.setBaseUrl(_baseUrlCtrl.text.trim());
      final body = <String, dynamic>{};
      if (_sttProvider != null) body['stt_provider'] = _sttProvider;
      if (_ttsProvider != null) body['tts_provider'] = _ttsProvider;
      if (_llmProvider != null) body['llm_provider'] = _llmProvider;
      if (_llmModel != null && _llmModel!.isNotEmpty) {
        body['llm_model'] = _llmModel;
      }
      if (_llmBaseUrlCtrl.text.trim().isNotEmpty) {
        body['llm_base_url'] = _llmBaseUrlCtrl.text.trim();
      }
      if (body.isNotEmpty) {
        _settings = await _repo.updateProviders(body);
      }
      if (mounted) showSuccessSnackbar(context, 'تم حفظ الإعدادات');
    } catch (e) {
      if (mounted) showErrorSnackbar(context, 'فشل الحفظ: $e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _logout() async {
    await _repo.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.bgGradient),
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                child: Row(
                  children: [
                    const Expanded(
                      child: Text('الإعدادات',
                          style: TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 22,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.refresh, color: AppColors.teal),
                      onPressed: _load,
                    ),
                  ],
                ),
              ),
              Expanded(
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(
                            color: AppColors.teal))
                    : SingleChildScrollView(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            // Connection
                            NebulaCard(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  const SectionHeader(
                                      title: 'الاتصال بالخادم'),
                                  const SizedBox(height: 16),
                                  TextFormField(
                                    controller: _baseUrlCtrl,
                                    textDirection: TextDirection.ltr,
                                    style: const TextStyle(
                                        color: AppColors.textPrimary,
                                        fontFamily: 'Cairo'),
                                    decoration: const InputDecoration(
                                      labelText: 'عنوان الخادم',
                                      prefixIcon:
                                          Icon(Icons.dns_outlined),
                                      hintText:
                                          'http://192.168.1.x:8000',
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 16),
                            // AI Providers
                            NebulaCard(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  const SectionHeader(
                                      title: 'مزودو الذكاء الاصطناعي'),
                                  const SizedBox(height: 16),
                                  _ProviderRow(
                                    label: 'STT (التعرف على الكلام)',
                                    value: _sttProvider,
                                    options: _sttProviders,
                                    onChanged: (v) =>
                                        setState(() => _sttProvider = v),
                                  ),
                                  const SizedBox(height: 14),
                                  _ProviderRow(
                                    label: 'TTS (تحويل النص لكلام)',
                                    value: _ttsProvider,
                                    options: _ttsProviders,
                                    onChanged: (v) =>
                                        setState(() => _ttsProvider = v),
                                  ),
                                  const SizedBox(height: 14),
                                  _ProviderRow(
                                    label: 'LLM (نموذج اللغة)',
                                    value: _llmProvider,
                                    options: _llmProviders,
                                    onChanged: (v) =>
                                        setState(() => _llmProvider = v),
                                  ),
                                  const SizedBox(height: 14),
                                  TextFormField(
                                    initialValue: _llmModel,
                                    textDirection: TextDirection.ltr,
                                    style: const TextStyle(
                                        color: AppColors.textPrimary,
                                        fontFamily: 'Cairo'),
                                    decoration: const InputDecoration(
                                      labelText: 'اسم نموذج LLM',
                                      prefixIcon: Icon(
                                          Icons.model_training_outlined),
                                      hintText:
                                          'مثال: nebula-masri:latest',
                                    ),
                                    onChanged: (v) => _llmModel = v,
                                  ),
                                  const SizedBox(height: 14),
                                  TextFormField(
                                    controller: _llmBaseUrlCtrl,
                                    textDirection: TextDirection.ltr,
                                    style: const TextStyle(
                                        color: AppColors.textPrimary,
                                        fontFamily: 'Cairo'),
                                    decoration: const InputDecoration(
                                      labelText: 'عنوان Ollama/LLM',
                                      prefixIcon:
                                          Icon(Icons.hub_outlined),
                                      hintText:
                                          'http://localhost:11434',
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 20),
                            NebulaPrimaryButton(
                              label: 'حفظ الإعدادات',
                              icon: Icons.save_outlined,
                              onTap: _save,
                              loading: _saving,
                            ),
                            const SizedBox(height: 16),
                            // Version info
                            NebulaCard(
                              padding: const EdgeInsets.all(14),
                              child: Row(
                                children: [
                                  const Icon(Icons.info_outline,
                                      color: AppColors.textMuted, size: 18),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const Text('نيبولا',
                                            style: TextStyle(
                                                color:
                                                    AppColors.textPrimary,
                                                fontFamily: 'Cairo',
                                                fontWeight:
                                                    FontWeight.w600)),
                                        Text(
                                            'الخادم: ${_store.getBaseUrl()}',
                                            style: const TextStyle(
                                                color:
                                                    AppColors.textMuted,
                                                fontFamily: 'Cairo',
                                                fontSize: 12)),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 16),
                            // Logout
                            NebulaDangerButton(
                              label: 'تسجيل الخروج',
                              icon: Icons.logout,
                              onTap: _logout,
                            ),
                          ],
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

class _ProviderRow extends StatelessWidget {
  final String label;
  final String? value;
  final List<String> options;
  final ValueChanged<String?> onChanged;

  const _ProviderRow({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          flex: 2,
          child: Text(label,
              style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontFamily: 'Cairo',
                  fontSize: 13)),
        ),
        const SizedBox(width: 12),
        Expanded(
          flex: 2,
          child: DropdownButtonFormField<String>(
            initialValue: value,
            dropdownColor: AppColors.card,
            style: const TextStyle(
                color: AppColors.textPrimary,
                fontFamily: 'Cairo',
                fontSize: 13),
            decoration: InputDecoration(
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide:
                      const BorderSide(color: AppColors.cardBorder)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide:
                      const BorderSide(color: AppColors.cardBorder)),
              focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: const BorderSide(
                      color: AppColors.teal, width: 1.5)),
            ),
            items: options
                .map((o) =>
                    DropdownMenuItem(value: o, child: Text(o)))
                .toList(),
            onChanged: onChanged,
            hint: const Text('—',
                style: TextStyle(color: AppColors.textMuted)),
          ),
        ),
      ],
    );
  }
}
