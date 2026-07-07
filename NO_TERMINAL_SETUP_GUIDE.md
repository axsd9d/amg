# PartFinder Setup Without Terminal

This guide shows how to put the PartFinder / AMG Maintenance Utility System on GitHub and Render using only a web browser. You do not need Terminal, Command Prompt, PowerShell, Git commands, or Docker commands.

## What you need before starting

You need the `partfinder-deploy.zip` file, a GitHub account, and a Render account. You should also have the supplier portal usernames and passwords ready, but do not put those passwords into GitHub. Passwords will be added only inside Render as secret environment variables.

## Part 1 — Prepare the project folder on your computer

First, download or locate `partfinder-deploy.zip` on your computer. Right-click the zip file and choose **Extract All** on Windows, or double-click it on Mac to unzip it. After extracting, you should see a folder named `partfinder-deploy`.

Open that folder and confirm it contains these files and folders: `Dockerfile`, `render.yaml`, `README.md`, `SETUP_GUIDE.md`, `QUICK_CHECKLIST.md`, `.gitignore`, `.env.example`, `backend`, and `frontend`. The `backend` folder should contain files like `serve_all.py`, `scraper.py`, `credentials.py`, and `suppliers.json`. The `frontend` folder should contain `index.html`.

Do not add any real password file to this folder. Do not create a `.env` file for GitHub upload. Passwords are added later in Render.

## Part 2 — Create a GitHub repository in the browser

Go to https://github.com and sign in. In the top-right corner, click the **+** icon and choose **New repository**.

For **Repository name**, enter `partfinder` or `amg-maintenance-utility`. Choose **Private**. This is recommended because this is internal business software. Do not check the boxes for README, `.gitignore`, or license because the project already includes those files.

Click **Create repository**.

GitHub will show a new empty repository page. Stay on this page.

## Part 3 — Upload the project files to GitHub without Terminal

On the empty repository page, click **uploading an existing file**. If you do not see that link, click **Add file** and then choose **Upload files**.

Open the extracted `partfinder-deploy` folder on your computer. Select all files and folders inside it, not the outer folder itself. You need to upload the contents: `Dockerfile`, `render.yaml`, `README.md`, `SETUP_GUIDE.md`, `QUICK_CHECKLIST.md`, `.gitignore`, `.env.example`, the `backend` folder, and the `frontend` folder.

Drag those selected files and folders into the GitHub upload area.

Important: GitHub’s browser uploader may not show hidden files like `.gitignore` or `.env.example` on some computers. That is okay for `.env.example`, but `.gitignore` is strongly recommended. If `.gitignore` does not upload, you can add it manually later by clicking **Add file → Create new file**, naming it `.gitignore`, and pasting the contents from the extracted folder.

Wait for all files to finish uploading. At the bottom, GitHub asks for a commit message. Enter `Initial PartFinder deployment files`. Click **Commit changes**.

After the upload completes, confirm that your repository shows these important files at the top level: `Dockerfile` and `render.yaml`. Render needs those two files.

## Part 4 — Connect Render to GitHub

Go to https://dashboard.render.com and sign in. It is easiest to sign in using your GitHub account.

If Render asks to connect to GitHub, allow it. You may need to choose which repositories Render can access. Select the repository you just created, such as `partfinder` or `amg-maintenance-utility`.

## Part 5 — Deploy using Render Blueprint

In Render, click **New +**. Choose **Blueprint**.

Render will show your GitHub repositories. Select the repository that contains the PartFinder files.

Render should detect the `render.yaml` file. It will create a web service from that file. Click **Apply** or **Create Blueprint**.

Render will start creating the service. The service name will likely be `partfinder` unless you changed it.

Important: This project uses Playwright and Chromium for automatic supplier portal login, plus Tesseract OCR for image reading. Because of that, use a paid Render instance such as **Standard**. Render’s free tier usually does not have enough memory for browser automation.

If Render asks for a plan, choose **Standard** or higher.

## Part 6 — Add supplier passwords securely in Render

Open your Render web service. Click **Environment** in the left menu.

You will add usernames and passwords here as secret environment variables. These values are stored by Render and are not uploaded to GitHub.

Add only the portals you actually want the system to auto-login to. Use these variable names exactly:

AllPoints:
`ALLPOINTS_USER`
`ALLPOINTS_PASS`

Amazon:
`AMAZON_USER`
`AMAZON_PASS`

Ferguson:
`FERGUSON_USER`
`FERGUSON_PASS`

Grainger:
`GRAINGER_USER`
`GRAINGER_PASS`

Johnstone Supply:
`JOHNSTONE_USER`
`JOHNSTONE_PASS`

PartsTown:
`PARTSTOWN_USER`
`PARTSTOWN_PASS`

For each username variable, enter the portal login email or username. For each password variable, enter the real portal password. Mark them as secret if Render gives you that option. Render may show these as hidden/secret automatically when created from the Blueprint.

Do not put passwords into `suppliers.json`. Do not upload passwords to GitHub.

After entering the variables, click **Save Changes**. Render will redeploy the service automatically.

## Part 7 — Wait for Render to finish building

Click the **Logs** tab in Render. The first deployment may take several minutes because Render is building the Docker image, installing Python packages, installing Playwright Chromium, and installing Tesseract OCR.

Wait until the logs say the service is live or deployed successfully.

If the build fails because of memory or browser startup errors, switch the service to a larger Render instance type, then redeploy.

## Part 8 — Open the live application

At the top of your Render service page, Render shows a public URL. It will look something like:

`https://partfinder.onrender.com`

Click that URL. The Maintenance Utility System app should open.

Because the frontend is served by the same backend, the app automatically talks to the correct API. You should not need to change the backend settings in the app.

## Part 9 — Confirm the backend sees your credentials

In your browser, open this URL, replacing the domain with your Render URL:

`https://YOUR-RENDER-URL.onrender.com/api/session-status`

You should see supplier names with statuses like `credentials-set` or `no-credentials`.

`credentials-set` means Render has the username/password variables for that supplier.

`no-credentials` means either you did not add that supplier’s username/password, or the variable name is misspelled.

## Part 10 — Test the photo OCR and supplier search

Open the main Render URL again. Tap **Browse** or **Take Photo** and upload a clear nameplate photo.

The backend will receive the raw image data through `/api/extract-base64`, run OCR, and try to extract model number, serial number, brand, and part number. Review the fields. If OCR misreads something, manually correct it.

Tap **Search All Suppliers**. The backend will compose a part number. If a part number was found, it uses that. If not, it combines model and serial as `MODEL-SERIAL`. The backend then attempts to log into each supplier portal using the Render environment variables and search the supplier portal for that part number.

If a live portal search works, results can show live price or stock text. If a portal blocks login, needs MFA, changes its page layout, or the selectors are not correct yet, the system falls back to a supplier search link so the rest of the app still works.

## Part 11 — Adjust portal login selectors if needed

Supplier websites all have different login pages. The backend file `backend/scraper.py` contains a section called `PORTAL_SELECTORS`. This tells the automation which username field, password field, login button, price element, and stock element to use.

You can edit this file directly in GitHub without Terminal.

Go to your GitHub repository. Open `backend/scraper.py`. Click the pencil icon to edit. Find `PORTAL_SELECTORS`.

For each supplier, update selectors like these:

`user`: the username/email field selector
`pass`: the password field selector
`submit`: the login button selector
`logged_in`: text or element that proves login worked
`result_price`: the price element selector
`result_stock`: the stock/availability element selector

To find selectors, open the supplier website in Chrome, right-click the login field, choose **Inspect**, and look for an `id`, `name`, or stable class. For example, if the username input has `id="username"`, the selector is `#username`.

After editing, click **Commit changes** in GitHub. Render will automatically redeploy from GitHub.

## Part 12 — Common problems

If the app opens but search says backend offline, you may be using the old static preview URL instead of the Render backend URL. Use the Render URL.

If `/api/session-status` says `no-credentials`, check the Render environment variable names and save/redeploy.

If OCR is poor, use a clearer nameplate image: bright light, no glare, straight-on, close enough to fill the frame.

If a supplier login fails, the portal may need MFA, may block automation, or the CSS selectors in `scraper.py` may need updating.

If Render crashes, upgrade to a larger instance. Browser automation needs more memory than a simple website.

## Safe password rule

Passwords belong only in Render Environment variables. They should never be typed into GitHub files. They should never be added to `suppliers.json`. They should never be placed in `.env` and uploaded.

## GPT-Vision photo extraction setup in Render

The app now tries GPT-Vision first for uploaded nameplate photos and automatically falls back to Tesseract OCR if GPT-Vision is unavailable. To turn GPT-Vision on, open your Render service, go to **Environment**, add a secret variable named `OPENAI_API_KEY`, paste your OpenAI API key, and save. Keep `OPENAI_VISION_MODEL` set to `gpt-4o-mini` unless you want to use another OpenAI vision-capable model. After saving, click **Manual Deploy → Deploy latest commit** if Render does not restart automatically.

If `OPENAI_API_KEY` is blank or missing, the app still works using the existing OCR fallback, but GPT-Vision will not be used.

## Automatic GitHub to Render updates

Once your GitHub repo is connected to Render, Render can automatically redeploy whenever the GitHub repository changes. In Render, open the PartFinder service, go to **Settings**, and confirm **Auto-Deploy** is turned on for the production branch, usually `main`. From that point forward, any file changes pushed to GitHub will trigger a new Render build and update the live app.

Ninja can only push directly to GitHub when the GitHub integration/tool is available inside the active workspace. If that tool is not available, use the updated zip package from Ninja and upload the changed files to GitHub in the browser; Render will then auto-deploy from GitHub.
