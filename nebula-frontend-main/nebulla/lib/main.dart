import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'core/theme.dart';
import 'services/storage_service.dart';
import 'services/locale_service.dart';
import 'screens/login_screen.dart';
import 'screens/main_shell.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock orientation to portrait
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  // Set system UI overlay style
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: AppColors.surface,
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  // Init storage & localization
  await StorageService.instance.init();
  await LocaleService.instance.init();

  runApp(const NebulaApp());
}

class NebulaApp extends StatelessWidget {
  const NebulaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: LocaleService.instance,
      builder: (context, _) {
        final localeService = LocaleService.instance;
        return MaterialApp(
          title: localeService.translate('brand_name'),
          debugShowCheckedModeBanner: false,
          theme: AppTheme.dark,
          scrollBehavior: const MaterialScrollBehavior().copyWith(
            dragDevices: {
              PointerDeviceKind.mouse,
              PointerDeviceKind.touch,
              PointerDeviceKind.stylus,
              PointerDeviceKind.trackpad,
              PointerDeviceKind.unknown,
            },
          ),
          locale: localeService.currentLocale,
          builder: (context, child) {
            return Directionality(
              textDirection: localeService.textDirection,
              child: child!,
            );
          },
          home: StorageService.instance.getToken() != null
              ? const MainShell()
              : const LoginScreen(),
        );
      },
    );
  }
}
