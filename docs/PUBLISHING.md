# Publish this project on GitHub

Publish the contents of the folder containing `app.py` and this repository's `README.md`. Do not publish the surrounding workspace or upload a copy of the working Python environment.

The repository includes source, launch scripts, requirements, documentation, MIT licensing, tests, and GitHub configuration. Its `.gitignore` excludes models, `.runtimes`, `.venv`, `runtime.json`, media, and generated subtitles. Keep these local files on your computer; other users install dependencies and download models themselves.

## 1. Prepare Git

Install [Git for Windows](https://git-scm.com/downloads/win), including Git Credential Manager, if Git is not available. Open a new PowerShell window and check:

```powershell
git --version
```

Change to your project folder using its actual path:

```powershell
Set-Location "C:\path\to\video_subtitle"
git init -b main
```

Set your commit identity for this repository. Replace the example values; GitHub's email settings can provide a private `noreply` address:

```powershell
git config user.name "YOUR_NAME"
git config user.email "YOUR_GITHUB_EMAIL"
```

These commands use repository-local settings, not global settings.

## 2. Review and commit the source

```powershell
git status --short --untracked-files=all
git add .
git diff --cached --stat
git diff --cached --name-only
```

The staged list should contain only project source, tests, documentation, and repository configuration. It must not contain `.venv/`, `.runtimes/`, `models/`, `results/`, `runtime.json`, or personal media. Do not use `git add -f` to override the ignore rules.

When the list is correct:

```powershell
git commit -m "Prepare English source release"
```

## 3. Create an empty GitHub repository

Sign in at [github.com/new](https://github.com/new). Choose a repository name such as `video-subtitle` and select Public or Private. A suggested description is:

> Local MP4 transcription with editable subtitles, speaker colors, and MP4/MKV export.

Do **not** initialize the remote with a README, `.gitignore`, or license; this project already includes them. Create the repository and copy its HTTPS URL. This is the empty-repository flow described in the [official GitHub guide](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## 4. Connect and upload

Replace `YOUR_USERNAME` and, if needed, the repository name:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/video-subtitle.git
git remote -v
git push -u origin main
```

Follow the Git Credential Manager sign-in prompt if shown. GitHub account passwords are not accepted for HTTPS Git operations; use an approved authentication method such as the credential manager's browser sign-in. Never put an access token in a repository file or remote URL. See [GitHub authentication documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github).

If `origin` already exists, inspect `git remote -v` before changing it. If the remote contains an initial commit, stop and reconcile that history; do not force-push over it.

## 5. Review the published project

- Confirm that the README renders correctly and the MIT license is visible.
- Check the Actions tab. Fix failed checks before calling the release ready.
- Download a fresh ZIP into a separate folder and follow the README installation steps.
- Use media you can share to manually verify transcription, speaker colors, and all three export modes.
- Add an actual application screenshot to the README if desired. Keep private filenames and transcripts out of public screenshots.
- Add relevant repository topics, such as `subtitles`, `speech-recognition`, `faster-whisper`, `speaker-diarization`, `python`, and `tkinter`.

After these checks, move the changelog's Unreleased notes into a dated `1.0.0` entry, commit them, and create a first release:

```powershell
git add CHANGELOG.md
git commit -m "Document version 1.0.0"
git push
git tag -a v1.0.0 -m "First public release"
git push origin v1.0.0
```

On GitHub, create a release from that tag and summarize the features and known limitations. GitHub provides source archives; there is no standalone executable installer in this project.

## Future updates

From the same project folder, review changes and run the relevant tests before committing:

```powershell
git status
git diff
git add .
git diff --cached --stat
git commit -m "Describe the change"
git push
```

A clear README, a license, reproducible setup instructions, checks, and honest release notes make the project easier to maintain. They do not by themselves establish production readiness; keep validating actual videos and reporting limitations.
