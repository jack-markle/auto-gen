# Privacy Policy

**Last updated:** September 14, 2026

AutoPost AI Studio ("we", "our", or "the Application") is an automated content creation and management tool designed to assist users in generating and publishing short-form video content to third-party platforms, including TikTok.

This Privacy Policy explains how user data is collected, used, and protected.

---

## 1. Information We Collect

When you use AutoPost AI Studio with the TikTok Content Posting API or AI services, the application accesses and processes:
- **Authentication Credentials:** OAuth access tokens, client keys, and client secrets required to communicate with the TikTok API on your behalf.
- **Account Identifiers:** Basic public profile information (such as your TikTok username) to display account status and target publishing feeds.
- **Content Data:** Prompts, script narration, generated video files, captions, and hashtags created during your session.

---

## 2. How Your Information Is Used

We use your information exclusively to:
- Generate requested video assets and audio voiceover.
- Authenticate and interact with the official TikTok Content Posting API to publish or draft videos.
- Provide local preview playback and video management in your studio dashboard.

**We do not sell, rent, monetize, or share your data or credentials with any unauthorized third parties.**

---

## 3. Data Storage and Security

- All API keys, secrets, and OAuth access tokens are stored locally on your machine in your environment file (`.env`).
- Video files, subtitles, and audio assets are stored locally within your workspace's `output/` directory.
- No personal authentication data is stored on external third-party servers operated by us.

---

## 4. Third-Party Services and Data Sharing

The application communicates with third-party service providers via direct API requests:
- **TikTok API:** To upload and publish video content as authorized by your OAuth permissions.
- **Google Gemini / AI Studio:** To generate scripts and scene descriptions.
- **Edge-TTS:** To generate speech synthesis for voiceover audio.

Your interactions with these services are governed by their respective privacy policies:
- [TikTok Privacy Policy](https://www.tiktok.com/legal/privacy-policy)
- [Google Privacy Policy](https://policies.google.com/privacy)

---

## 5. Data Retention and Deletion

You maintain complete control over your data:
- You can delete generated videos, scene clips, and audio files at any time using the "Delete Files" or "Clean Output Dir" buttons in the studio dashboard.
- You can revoke TikTok API permissions at any time via your TikTok account settings under **Settings & Privacy > Security > Manage App Permissions**.
- Removing the `.env` file permanently deletes all stored access tokens from your machine.

---

## 6. Changes to This Policy

We may update this Privacy Policy from time to time to reflect changes in our practices or applicable platform policies. Any revisions will be posted directly to this repository.

---

## 7. Contact Information

If you have questions or concerns regarding this Privacy Policy, please open an issue in the project repository:
- **Repository:** [https://github.com/jack-markle/auto-gen](https://github.com/jack-markle/auto-gen)
