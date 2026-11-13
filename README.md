# Phone Number Lookup (Google Sheet Checker)

A local web app that searches a private Google Sheet for an exact 10-digit phone number across Column D (`Phone (Original)`) and Column E (`Phone (Show)`), and displays every matching row in full.

## Setup (One-Time)

1. **Create a Google Service Account & download `credentials.json`**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/).
   - Create/select a project and enable the **Google Sheets API**.
   - Go to **IAM & Admin → Service Accounts** → **Create Service Account**.
   - Open the created service account → **Keys** tab → **Add Key → Create new key → JSON**.
   - Save the downloaded file as `credentials.json` inside `d:\Duplicate Checker\`.

2. **Share your private Google Sheet**:
   - Open `credentials.json` and copy the `client_email` address (e.g., `...iam.gserviceaccount.com`).
   - Open your Google Sheet → click **Share** → paste that `client_email` → give **Viewer** access.

3. **Configure `config.json`**:
   - Open `config.json` and replace `PASTE_YOUR_GOOGLE_SHEET_ID_HERE` with your Google Sheet ID (the string between `/d/` and `/edit` in your sheet's URL).
   - Set `sheet_name` to the exact tab name in your Google Sheet (default is `Sheet1`).

## Run the Website

Double-click `run.bat` or run:

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open **http://127.0.0.1:5000** in your browser.
