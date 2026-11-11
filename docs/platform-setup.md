# Connecting social platforms

NEUTX publishes through each platform's official API. Every platform needs a
developer app that **you** create. NEUTX can't ship shared credentials.
Set the app's client id and secret as environment variables (see
[.env.example](../.env.example)), restart NEUTX, then click **Connect** on the
Connections page.

The OAuth redirect URI to register is always:

```
{PUBLIC_BASE_URL}/api/oauth/{platform}/callback
```

for example `https://neutx.example.com/api/oauth/youtube/callback`. Most
platforms require `https` and an exact match, including any trailing slash.

| Platform | Env vars | Scopes NEUTX requests | Media |
| --- | --- | --- | --- |
| TikTok | `TIKTOK_CLIENT_ID` (client key), `TIKTOK_CLIENT_SECRET` | `user.info.basic`, `video.publish` | Video |
| Instagram | `INSTAGRAM_CLIENT_ID` (Instagram app ID), `INSTAGRAM_CLIENT_SECRET` | `instagram_business_basic`, `instagram_business_content_publish` | Reels, images |
| YouTube | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | `youtube.upload`, `youtube.readonly` | Video |
| X | `X_CLIENT_ID`, `X_CLIENT_SECRET` | `tweet.read tweet.write users.read media.write offline.access` | Video, images |

## TikTok

1. Create an app at <https://developers.tiktok.com/>, then add **Login Kit** and
   the **Content Posting API** with **Direct Post** enabled.
2. Add the redirect URI and request the `video.publish` scope.
3. Until TikTok audits your app, every post is restricted to private viewing
   (`SELF_ONLY`). Keep `TIKTOK_PRIVACY_LEVEL=SELF_ONLY` until then. NEUTX
   falls back to `SELF_ONLY` whenever the creator's account doesn't offer the
   configured level.
4. Posts are labelled as AI-generated (`is_aigc`), and the creator's
   comment, duet and stitch settings are respected.

## Instagram

1. Create a Meta app with the **Instagram API with Instagram Login** product.
   The Instagram account must be a professional (Business or Creator) account.
2. Add the redirect URI under *Business login settings*.
3. Instagram downloads the media itself, so `PUBLIC_BASE_URL` must be a
   **public https URL** that Meta's servers can reach. NEUTX serves each file
   through a signed link that expires after one hour.
4. Images are converted to JPEG automatically, since that's the only image
   format Instagram accepts. Videos are posted as Reels.

## YouTube

1. In Google Cloud Console, create a project, enable **YouTube Data API v3**,
   configure the OAuth consent screen and create a **Web application** OAuth
   client with the redirect URI.
2. Uploads are `private` by default (`YOUTUBE_PRIVACY_STATUS`). Uploads are
   marked as containing synthetic media.
3. Each upload costs API quota. Check your project's quota in Cloud Console.

## X

1. In the X developer portal, create an app, enable **OAuth 2.0** as a
   *Web App / confidential client*, and add the redirect URI.
2. Posting requires an API access level that includes media upload and post
   creation. Check X's current pricing and limits.
3. Captions longer than 280 characters are truncated on X.

## Troubleshooting

- **"Not configured on this server"**: the client id or secret env var is
  missing. Restart NEUTX after setting them.
- **Redirect URI mismatch**: `PUBLIC_BASE_URL` must match the URL you
  registered exactly.
- **A post failed**: open it in the Calendar. Each destination shows the
  platform's own error message, and **Retry failed** re-sends only the
  destinations that failed.
- Changing `NEUTX_SECRET_KEY` makes stored tokens unreadable. Reconnect the
  accounts afterwards.
