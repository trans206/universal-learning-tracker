[app]

title = Universal Learning Tracker
package.name = universallearningtracker
package.domain = org.learningtracker

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas
version = 1.0.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

# No special permissions are needed for the current offline app.
# The app stores its database inside its private Android app data folder.

[buildozer]

log_level = 2
warn_on_root = 1
