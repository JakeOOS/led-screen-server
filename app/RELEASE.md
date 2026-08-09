# VOXEL Android — release build

The app is a Capacitor shell around `control.html`. There is no separate app
source: `build-www.mjs` copies the same file the server hands out at `/app` into
`www/index.html` and injects `window.VOXEL_API_BASE` so the packaged build
(origin `https://localhost`) talks to the deployed backend. Edit `control.html`;
everything downstream follows.

```
control.html ──build-www.mjs──> app/www/index.html ──cap sync──> android/…/assets/public/
resources/*.png ──capacitor-assets──> android/…/res/mipmap-*, drawable-*
```

| | |
|---|---|
| Package name | `com.residentarchitects.voxel` |
| Backend | `https://led-screen-server.onrender.com` |
| min / target SDK | 23 / 35 |
| Version | `versionCode` + `versionName` in `android/app/build.gradle` |

## State

Done: Capacitor project, Android platform, launcher icons and splash (light and
dark) generated from `resources/`, App Links intent filter, backup disabled so
Supabase tokens cannot leave the device, release signing config wired to
`keystore.properties`, Play listing icon and feature graphic in `play/`.

Not done: the toolchain, the signing key, and the Play Console policy items —
below.

## 1. Toolchain

Neither a JDK nor the Android SDK is installed on this machine. Either install
Android Studio (bundles both, and is the easier route if you want to eyeball the
app in an emulator first), or command-line only:

```bash
brew install openjdk@21 && brew install --cask android-commandlinetools
```

Then point Gradle at the SDK and accept the licences:

```bash
echo "sdk.dir=/opt/homebrew/share/android-commandlinetools" > android/local.properties
sdkmanager --licenses
```

## 2. Signing key

Google never lets you replace this key, and losing it means you cannot ship an
update to the same listing — back up the `.jks` and its passwords somewhere
durable before you upload anything.

Create it yourself (it takes passwords, so run this rather than delegating it):

```bash
keytool -genkeypair -v -keystore android/voxel-upload.jks -alias voxel -keyalg RSA -keysize 2048 -validity 10000
```

Then write `android/keystore.properties` — gitignored, and it must stay that
way:

```properties
storeFile=voxel-upload.jks
storePassword=<the store password you chose>
keyAlias=voxel
keyPassword=<the key password you chose>
```

## 3. Build the bundle

```bash
npm run bundle
```

Output: `android/app/build/outputs/bundle/release/app-release.aab` — that is the
file you upload to Play Console. `npm run apk` gives you a signed APK instead if
you want to sideload and test on a handset first.

`npm run bundle` re-runs `build:www` and `cap sync` first, so it always packages
the current `control.html`.

## 4. Play Console

Assets are ready in `play/`: `icon-512.png` and `feature-graphic-1024x500.png`.
You still need at least two phone screenshots — take them from a device or
emulator running the release build.

Three policy items are **not** satisfied yet and will each block review, because
the app has accounts:

- **Privacy policy URL.** Required in the listing and in the Data safety form.
  Nothing is written or hosted yet.
- **Data safety declaration.** The app collects email addresses (Supabase Auth)
  and stores schedule/screen configuration. Declare that honestly, including
  that data is transmitted off-device and encrypted in transit.
- **Account deletion.** Play requires both an in-app path and a publicly
  reachable web URL to request deletion. Neither exists — `server.py` has no
  delete-account route and `control.html` has no button.

## 5. After the first upload

Play re-signs the bundle with its own key, so the fingerprint that App Links
must trust only exists once Google has it. Copy it from **Test and release → App
integrity → App signing key certificate** (SHA-256, colon-separated hex) and set
it on Render:

```
ANDROID_CERT_SHA256=AA:BB:CC:…
```

`server.py` serves it at `/.well-known/assetlinks.json`. Until then App Links
stay unverified and password-reset mails open in a browser instead of the app —
the flow still completes, it just does not hand off.

## Shipping a new version

Bump `versionCode` (must increase every upload) and `versionName` in
`android/app/build.gradle`, then `npm run bundle`.
