# Error Codes Reference

When the checker encounters a system or Google Sheets error, the website displays only a generic message with an error code (for example, `Something went wrong. Please try again later. (Error Code: E103)`).

| Code | Meaning | How to Fix |
| :--- | :--- | :--- |
| `E101` | Missing or invalid Spreadsheet ID | Set a valid `SECOND_SPREADSHEET_ID` or `SPREADSHEET_ID` in Render Environment Variables or `config.json`. |
| `E102` | Missing or invalid Google Service Account credentials | Check `GOOGLE_CREDENTIALS_JSON` on Render or `credentials.json` locally. |
| `E103` | Google Sheets access denied (`HTTP 403`) | Share the Google Sheet (Viewer access) with the Service Account email in `credentials.json`. |
| `E104` | Google Sheet not found (`HTTP 404`) | Verify the Sheet ID is correct and that the file is a native Google Sheet (not an `.xlsx` file). |
| `E105` | Invalid sheet tab name (`HTTP 400`) | Check `SECOND_SHEET_NAME` / `SHEET_NAME` or leave it blank to use the first tab automatically. |
| `E106` | Other Google Sheets API error | Temporary Google API issue or quota limit; retry shortly or check Render logs. |
| `E107` | Unexpected server error | Check the server logs on Render for details. |
