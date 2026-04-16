# How to Authenticate CRAVE for Secure YouTube Uploads 🚀

CRAVE is now capable of securely uploading videos directly to your YouTube channel! But to prevent unauthorized access, Google requires you to prove ownership using OAuth2 credentials. 

We will generate a `.json` key that CRAVE stores locally (completely private). CRAVE does not bypass your security; instead, it acts on behalf of your channel exactly as you authorize it.

### Step-by-Step Instructions (Takes 3 Minutes):

1. **Go to Google Cloud Console:**
   Open your browser and navigate to: [https://console.cloud.google.com/](https://console.cloud.google.com/)

2. **Create a New Project:**
   - Click the **Project Dropdown** at the top left (next to the Google Cloud logo).
   - Click **New Project** in the top right of the popup window.
   - Name it `CRAVE-YouTube-Agent` and click **Create**. Let it load for a few seconds.

3. **Enable the YouTube Data API v3:**
   - In the top search bar, search for **"YouTube Data API v3"** and click the first result.
   - Click the big blue **Enable** button.

4. **Configure the OAuth Consent Screen:**
   - On the left sidebar, go to **Credentials** -> **OAuth consent screen**.
   - Select **External** (if you don't have Google Workspace) and click **Create**.
   - **App Name:** `CRAVE AI`
   - **User Support Email:** Select your email address.
   - **Developer Contact Info:** Enter your email address.
   - Click **Save and Continue** all the way to the end (skip adding scopes manually).
   - Under **Test Users**, click **Add Users** and type your own email address (the one associated with your YouTube channel). Click Add, then Save.

5. **Generate the Credentials (.json file):**
   - On the left sidebar, click **Credentials**.
   - Click **+ Create Credentials** at the top, then select **OAuth client ID**.
   - **Application Type:** Select **Desktop App**.
   - **Name:** `CRAVE Desktop Client`
   - Click **Create**.
   - A popup will appear. Click **Download JSON** (it will be named something like `client_secret_xyz.json`).

6. **Place the Secret in the CRAVE Vault:**
   - Move that downloaded `.json` file into your CRAVE configuration folder:
     `D:\CRAVE\config\youtube_client_secret.json`
   - Specifically, rename it to EXACTLY `youtube_client_secret.json`.

---

### What Happens Next?
The very **first time** you ask CRAVE to upload a video, a local browser window will pop up asking you to log into your Google account and verify permissions. 
Once you click "Allow", CRAVE will save a secure token locally and will never ask you again!

> [!TIP]
> Google might flash a warning screen saying "Google hasn’t verified this app." This is completely normal because you just built the app for yourself! Simply click **Advanced** at the bottom, and then click **Go to CRAVE AI (unsafe)** to proceed safely.
