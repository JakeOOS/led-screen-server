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
`keystore.properties`, Play listing icon and feature graphic in `play/`,
toolchain installed, `/privacy` and `/delete-account` pages plus in-app account
deletion. A debug APK builds clean.

Not done: the signing key, store screenshots, and the Play Console forms.

## exFAT: why build output lives outside the repo

This volume is exFAT, where macOS writes an AppleDouble `._x` sidecar beside any
file carrying extended attributes. Gradle creates those files *during* a build,
and both the Android resource parser and d8 then fail on them:

```
'…/packaged_res/debug/…/._layout' is not a directory
Unexpected class file name: com/capacitorjs/plugins/app/._AppPlugin$1.class
```

Cleaning first does not help — they reappear as the build writes. So
`android/build.gradle` redirects every module's build directory to
`~/.gradle-build-dirs/voxel-android`, on the internal APFS disk. Sources stay in
the repo; only generated output moves. Build artefacts are therefore **not**
under `android/app/build/` — see the paths below.

`git` needs the same treatment: `core.filemode` is set to `false` in this repo,
because exFAT reports every file as executable and otherwise the whole tree
shows as modified.

## 1. Toolchain

Already installed: OpenJDK 21 (`/opt/homebrew/opt/openjdk@21`) and the Android
command-line tools (`/opt/homebrew/share/android-commandlinetools`), with
licences accepted and `android/local.properties` written.

Gradle needs `JAVA_HOME` pointed at the JDK, since the system has no default
Java. Either prefix commands with it, or put this in your shell profile:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
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

Output (note: outside the repo, per the exFAT section above):

```
~/.gradle-build-dirs/voxel-android/app/outputs/bundle/release/app-release.aab
```

That is the file you upload to Play Console. `npm run apk` gives you a signed
APK instead if you want to sideload and test on a handset first, and
`npm run debug` builds an unsigned debug APK.

`npm run bundle` re-runs `build:www` and `cap sync` first, so it always packages
the current `control.html`.

## 4. Play Console

Assets are ready in `play/`: `icon-512.png` and `feature-graphic-1024x500.png`.
You still need at least two phone screenshots — take them from a device or
emulator running the build.

The policy work is done and deployed with the backend:

- **Privacy policy** — `/privacy`, served from `privacy.html`.
- **Account deletion** — `DELETE /api/user/me`, reachable in-app from
  **Account → Delete account** (typed `DELETE` confirmation), plus the public
  `/delete-account` page Play requires as a web route. Deleting removes the
  Supabase auth user and unpairs their screens, resetting each to a fresh pair
  code so the hardware can be set up again.
- **Data safety form** — answers written out in
  [PLAY-DATA-SAFETY.md](PLAY-DATA-SAFETY.md), checked against what the code
  actually sends.

One thing that is easy to forget and does cause rejections: under **App
access**, reviewers need working credentials, or they cannot get past the
sign-in screen. Create a throwaway account and give it to them.

These pages are served by the backend, so **the backend has to be redeployed**
before you submit — the URLs must resolve when the reviewer opens them.

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
