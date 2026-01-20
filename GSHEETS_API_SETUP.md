# Google Sheets API Setup Instructions

This guide continues from the Gmail Service Account setup from lesson 5 and shows how to enable Google Sheets API for the same project.

## Prerequisites

- Completed Gmail Service Account setup (service account JSON file already exists)
- Access to Google Cloud Console
- Access to Google Workspace Admin Console

## Step-by-Step Instructions

### Step 1: Enable Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your existing project (the one with the Gmail service account)
3. Go to **APIs & Services** > **Library**
4. Search for "Google Sheets API"
5. Click on "Google Sheets API" from the results
6. Click **"Enable"**

### Step 2: Add Sheets Scope to Domain-Wide Delegation

Since you already have domain-wide delegation set up for Gmail, you need to add the Sheets scope:

1. Go to [Google Workspace Admin Console](https://admin.google.com/)
2. Navigate to **Security** > **Access and data control** > **API Controls** > **Manage Domain-wide Delegation**
3. Find your existing service account entry (the one you created for Gmail)
4. Click **"Edit"** (pencil icon)
5. In the **OAuth Scopes** field, add the Sheets scope alongside the existing Gmail scope:
   ```
   https://www.googleapis.com/auth/spreadsheets
   ```
   
   > **Note:** Scopes should be comma-separated with no spaces
   
6. Click **"Authorize"**

### Step 3: Share the Spreadsheet with the Service Account

For the service account to access a specific spreadsheet:

1. Open the Google Spreadsheet you want to access
2. Click **"Share"** button (top right)
3. Add the service account email address:
   - Find this in your JSON file under `"client_email"`
   - It looks like: `your-service-account@your-project.iam.gserviceaccount.com`
4. Set permission to **"Editor"** (for read/write access)
5. Uncheck "Notify people" (service accounts can't receive emails)
6. Click **"Share"**

## Important Notes

⚠️ **Sharing Requirements:**
- The spreadsheet must be shared with the service account email
- Without sharing, you'll get a "403 Forbidden" error
- The service account email is found in your JSON file under `client_email`

⚠️ **Scope Differences:**
| Scope | Access Level |
|-------|--------------|
| `https://www.googleapis.com/auth/spreadsheets` | Full read/write access |
| `https://www.googleapis.com/auth/spreadsheets.readonly` | Read-only access |

⚠️ **Domain-Wide Delegation (Optional for Sheets):**
- Unlike Gmail, Sheets API doesn't require domain-wide delegation if the spreadsheet is directly shared with the service account
- Domain-wide delegation is only needed if you want to access spreadsheets as a specific user without explicit sharing

## Troubleshooting

**Error: "403 Forbidden" or "The caller does not have permission"**
- Verify the spreadsheet is shared with the service account email
- Check that the service account email is correct (copy from JSON file)
- Ensure you shared with "Editor" permissions

**Error: "Google Sheets API has not been used in project"**
- Go back to Google Cloud Console and verify the API is enabled
- Wait a few minutes after enabling (can take time to propagate)

**Error: "Invalid credentials"**
- Verify the JSON file path is correct in your code
- Check that the JSON file exists at `../inbound-footing-412823-c2ffc4659d84.json`
- Ensure the JSON file hasn't been corrupted

**Error: "Quota exceeded"**
- Google Sheets API has usage limits:
  - 300 read requests per minute per project
  - 300 write requests per minute per project
- Implement rate limiting (already done in `googlesheets_functions.py` with `TIME_INTERVAL`)

## Additional Resources

- [Google Sheets API Documentation](https://developers.google.com/sheets/api)
- [Google Sheets API Quickstart](https://developers.google.com/sheets/api/quickstart/python)
- [API Scopes Reference](https://developers.google.com/sheets/api/guides/authorizing)

