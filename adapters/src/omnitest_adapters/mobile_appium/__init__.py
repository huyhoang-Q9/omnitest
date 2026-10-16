from omnitest_adapters.appium.adapter import AppiumAdapter

# Android (UiAutomator2) và iOS (XCUITest) qua Appium, cần thiết bị hoặc emulator/simulator thật.
adapter = AppiumAdapter(
    "mobile-appium", "Mobile Android/iOS (Appium, thử nghiệm)", ("mobile_android", "mobile_ios")
)
