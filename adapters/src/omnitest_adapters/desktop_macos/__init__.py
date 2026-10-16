from omnitest_adapters.appium.adapter import AppiumAdapter

# Appium driver Mac2 trên máy macOS thật (cần quyền Accessibility cho Appium/WebDriverAgentMac).
adapter = AppiumAdapter(
    "desktop-macos", "Desktop macOS (Appium Mac2, thử nghiệm)", ("desktop_macos",)
)
