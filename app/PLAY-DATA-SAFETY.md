# Play Console — Data safety answers

Copy these into **App content → Data safety**. Every answer below is what the
code actually does, checked against `server.py` and `control.html` — if you
change what the app collects, change this too, because a Data safety form that
contradicts the app is one of the more common review rejections.

Supporting URLs:

- Privacy policy: `https://led-screen-server.onrender.com/privacy`
- Account deletion: `https://led-screen-server.onrender.com/delete-account`

## Overview questions

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Is all of the user data collected by your app encrypted in transit? | **Yes** — everything is HTTPS |
| Do you provide a way for users to request that their data is deleted? | **Yes** — in-app (Account → Delete account) and the web URL above |

## Data types to declare

### Personal info → Email address

| Field | Answer |
|---|---|
| Collected | Yes |
| Shared | No |
| Processed ephemerally | No — it is stored |
| Required or optional | Required |
| Purpose | **Account management** |

Supabase Auth stores it. The password is handled by Supabase and stored only as
a hash, so it is not separately declarable as collected data.

### App activity → Other user-generated content

| Field | Answer |
|---|---|
| Collected | Yes |
| Shared | No |
| Processed ephemerally | No — it is stored |
| Required or optional | Required |
| Purpose | **App functionality** |

Covers the screens, catalogues, schedule, message text, weather location, train
station, and news interests — everything the user configures for the display.

### Nothing else is collected

Do **not** tick these — the code does none of it:

- Location — the weather location is typed by the user, never read from device
  GPS. The app declares no location permission.
- Device or other IDs — no advertising ID, no device fingerprint.
- Photos, videos, audio, files, contacts, calendar, SMS.
- App activity → App interactions, crash logs, diagnostics — there is no
  analytics or crash-reporting SDK.
- Financial info, health, messages.

## Third parties

The weather location, station, and news-interests text are sent to OpenWeather,
Rail Data Marketplace, and the Anthropic API respectively, to render those
screens. None of those calls carry a user identifier, so they are processing on
your behalf rather than "sharing" as Play defines it (transfer to a third party
for their own use) — answer **No** to "Shared" throughout.

If you later add analytics, advertising, or send any user identifier to a third
party, this section changes and the form must be resubmitted.

## Also required in App content

- **Privacy policy** — the `/privacy` URL above.
- **App access** — reviewers need a working account. Create a throwaway login
  and give them the credentials, or they cannot get past the sign-in screen and
  will reject the build.
- **Ads** — declare **No ads**.
- **Content rating** — complete the questionnaire; with no user-to-user content
  or ads this lands at the lowest rating.
- **Target audience** — 13+. The app is not designed for children.
- **Data deletion** — point it at the `/delete-account` URL above.
