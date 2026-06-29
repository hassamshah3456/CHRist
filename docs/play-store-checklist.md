# Google Play Store — CRIST Tool publishing checklist

Use this when submitting **CRIST Tool** (`com.usmlewise.usmlewise_christ`) to Google Play.

## Before you upload

- [ ] **Privacy policy URL** live and public: `https://api.usmlewise.com/privacy`
- [ ] **Terms URL** live: `https://api.usmlewise.com/terms`
- [ ] **Release AAB** built with HTTPS API:
  ```bash
  flutter build appbundle --release \
    --dart-define=API_BASE_URL=https://api.usmlewise.com \
    --dart-define=PRIVACY_POLICY_URL=https://api.usmlewise.com/privacy \
    --dart-define=TERMS_URL=https://api.usmlewise.com/terms
  ```
- [ ] **Upload keystore** created and stored safely (not in git). Configure GitHub Actions secrets:
  - `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `ANDROID_STORE_PASSWORD`
- [ ] Set repo variable `API_BASE_URL=https://api.usmlewise.com`

## Store listing (Play Console)

| Field | Suggested content | Limit |
|-------|-------------------|-------|
| **App name** | CRIST Tool | 50 chars |
| **Short description** | Field screening tool for authorised CRIST research collectors. | 80 chars |
| **Full description** | See template below | 4000 chars |
| **Category** | Medical (or Health & Fitness if Medical unavailable) | — |
| **Contact email** | admin@usmlewise.com | — |
| **Privacy policy** | https://api.usmlewise.com/privacy | required |

### Full description template

```
CRIST Tool is the official mobile app for authorised field collectors in the UsmleWise CRIST developmental screening study.

Features:
• Secure collector sign-in
• Geo-tagged data collection with offline sync
• Dynamic screening questionnaires
• Optional medical-record photos
• Payment tracking for collectors

Requirements:
• Authorised collector account only
• Location must be enabled while using the app
• Verbal caregiver consent required before each submission

This app supports research data collection. It is not a medical device and does not provide diagnosis or treatment.

Privacy: https://api.usmlewise.com/privacy
```

## App content declarations

- [ ] **Health apps**: declare that the app collects health-related information for research (screening answers, vaccines, medical photos).
- [ ] **Not a medical device**: screening support tool only; no diagnosis/treatment claims in listing or screenshots.
- [ ] **Target audience**: app is for adults (collectors). Data about children is entered by collectors after caregiver consent.
- [ ] **Ads**: No ads.
- [ ] **News app**: No.

## Data safety form (match app behaviour)

Declare **collected** data:

| Data type | Collected | Shared | Purpose | Encrypted in transit |
|-----------|-----------|--------|---------|----------------------|
| Name | Yes | Server only | Account | Yes (HTTPS) |
| Phone number | Yes | Server only | Account + submissions | Yes |
| Precise location | Yes | Server only | Geo-tagging + field monitoring | Yes |
| Photos | Yes (optional) | Server only | Medical record / screening docs | Yes |
| Health info | Yes | Server only | Research screening | Yes |
| Financial info (UPI) | Yes (optional) | Server only | Collector payments | Yes |
| App activity (foreground time) | Yes | Server only | Admin oversight | Yes |

Also declare:
- Data is **not sold**
- Users can **request account deletion** (Profile → Delete account)
- Data is **encrypted in transit** (HTTPS enforced in release builds)
- **No background location** collected

## Permissions justification (Play Console)

| Permission | Justification |
|------------|---------------|
| Location (while in use) | Geo-tag each submission and sign-up; admin field monitoring while app is open |
| Camera | Optional photos of medical records / screening documentation |
| Internet | Sync submissions with research server |

## Content rating

Complete the IARC questionnaire honestly. Expect questions about:
- Collection of user-generated content (photos)
- Location sharing
- Health-related content

## Testing track

1. Upload AAB to **Internal testing**
2. Install on a physical device from Play
3. Verify: register, location gate, collection with consent, sync, profile delete account
4. Promote to **Closed testing** for field collectors, then **Production**

## Common rejection reasons to avoid

- Missing or broken privacy policy URL
- Debug-signed AAB uploaded to production
- HTTP (non-HTTPS) API in release build
- Misleading health claims (“diagnose”, “treat”, “cure”)
- Missing account deletion when app has accounts
- Data safety form contradicts actual app permissions/data

## ASO quick wins

- Use screenshots showing: login, location disclosure, consent step, collection form, payments
- First screenshot: brand + “Authorised collectors only”
- Localise listing later for Hindi/Kannada markets if expanding beyond Karnataka
