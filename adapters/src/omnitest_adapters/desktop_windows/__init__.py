from omnitest_adapters.appium.adapter import AppiumAdapter

# Appium driver Windows (WinAppDriver) trên máy Windows thật.
adapter = AppiumAdapter(
    "desktop-windows", "Desktop Windows (Appium Windows, thử nghiệm)", ("desktop_windows",)
)
