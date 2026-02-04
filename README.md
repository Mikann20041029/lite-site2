# One-Shot RSS → Static Site (Lite)

This is a **trial / one-shot** GitHub template.
It runs **once**, generates a small static site from RSS/Atom, and deploys to **GitHub Pages**.

- No ads
- No affiliates
- No external API keys
- One-run guard (locks after first successful deploy)

## Files in this zip (root)
- README.md
- LICENSE
- requirements.txt
- build.py
- guard.py
- site.config.json
- templates/
- assets/

IMPORTANT:
- This zip intentionally does **NOT** include `.github/` (web upload sometimes drops it).
- You must create the workflow file by copy-pasting the code below.

## Step-by-step (GitHub UI)

1. Create a new GitHub repository.
2. Upload all files from this zip to the repository root.
3. Create a workflow file:

   - In GitHub: **Add file → Create new file**
   - File name: `.github/workflows/one-shot-lite.yml`
   - Paste the YAML below (exactly)
   - Commit changes

```yml
name: Build & Deploy (One-Shot Lite)

on:
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: one-shot-lite
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: One-shot guard
        run: |
          python guard.py --check

      - name: Build
        run: |
          python build.py

      - name: Deploy to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./dist
          publish_branch: gh-pages
          force_orphan: true

      - name: Lock & self-disable workflow (hard to rerun)
        run: |
          python guard.py --lock
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add .lite/lock.json
          # Remove this workflow file from the default branch after first success.
          # This prevents accidental 2nd runs unless the user recreates the workflow manually.
          git rm -f .github/workflows/one-shot-lite.yml || true
          git commit -m "one-shot: lock and disable workflow" || echo "Nothing to commit"
          git push
```

4. Run it:
   - Go to **Actions** tab
   - Select **Build & Deploy (One-Shot Lite)**
   - Click **Run workflow**

5. Enable Pages:
   - Settings → Pages
   - Source: Deploy from a branch
   - Branch: `gh-pages` (created by the workflow)
   - Save

## Customize feeds
Edit `site.config.json`:

- `feeds`: list of RSS/Atom URLs
- `site_title`, `site_description`

## One-shot behavior (how it is enforced)
After the first successful run:
- a lock file is committed to `.lite/lock.json`
- the workflow file is removed from the default branch automatically

If someone tries to run again, the guard stops the build unless they delete the lock and recreate the workflow.
